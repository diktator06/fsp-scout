import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    ConsentRequiredError,
    FspAlreadyLinkedError,
    FspNotLinkedError,
    FspUnavailableError,
)
from app.crud import (
    audit_log_crud,
    consent_crud,
    fsp_achievement_crud,
    fsp_link_crud,
    fsp_sync_log_crud,
    privacy_settings_crud,
)
from app.crud.candidate_search import PoolQuery
from app.integrations.fsp_gateway import FspGateway
from app.integrations.fsp_registry import RegistryAchievement
from app.models.candidate import CandidateProfile
from app.models.consent import ConsentType
from app.models.fsp import (
    FspLink,
    FspResultStatus,
    FspState,
    FspSyncLog,
    FspSyncStatus,
    OidcFlowPurpose,
)
from app.models.user import User
from app.schemas.cards import FspAchievementRead
from app.schemas.fsp import (
    FspAuthorizationRead,
    FspCallback,
    FspLinkStart,
    FspProfileRead,
    FspScoreRead,
    FspSyncRead,
)
from app.services.auth.tokens import ClientContext
from app.services.candidate.profile_service import CandidateProfileService
from app.services.consents import FSP_DATA_POLICY_VERSION
from app.services.fsp.achievements_scoring import FspScore, describe_result, summarize
from app.services.fsp.oidc_flow import OidcFlow
from app.services.fsp.standing import fsp_standing
from app.services.matching.candidate_pool import CandidatePoolService
from app.services.matching.cards import verified_score_read
from app.services.matching.verified_score import VPS_WEIGHTS

logger = logging.getLogger(__name__)

NOT_LINKED_HINT = (
    "Привяжите ФСП ID: подтверждённые участия в соревнованиях повысят индекс профиля. "
    "Без привязки оценка основана на тесте и профиле, это не штраф"
)


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def _registry_rows(achievements: Sequence[RegistryAchievement]) -> list[dict[str, object]]:
    """Записи реестра в поля таблицы; повтор одного события в ответе отбрасывается."""
    rows: dict[str, dict[str, object]] = {}
    for item in achievements:
        values = item.model_dump(exclude={"event_id"})
        rows.setdefault(item.event_id, {"external_event_id": item.event_id, **values})
    return list(rows.values())


def score_read(score: FspScore) -> FspScoreRead:
    """Балл ФСП для ответа API вместе с вкладом в индекс подтверждённого профиля."""
    best = score.best
    return FspScoreRead(
        value=score.value,
        results=score.results,
        activity=score.activity,
        effective_events=score.effective_events,
        events=score.events,
        wins=score.wins,
        prizes=score.prizes,
        finals=score.finals,
        online_attendance=score.online_attendance,
        best_result=describe_result(best)
        if best is not None and best.result_status is not FspResultStatus.PARTICIPANT
        else None,
        summary=summarize(score),
        vps_points=round(100 * VPS_WEIGHTS["fsp"] * score.value, 1),
    )


class FspService:
    """ФСП в кабинете кандидата: привязка ФСП ID, синхронизация с реестром, отвязка.

    Каждый публичный сценарий — одна транзакция. Если реестр недоступен, данные
    прошлой синхронизации сохраняются, а ошибка пишется в журнал синхронизаций.
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        gateway: FspGateway,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        """Получает сессию БД, настройки, шлюз ФСП и источник времени."""
        self._session = session
        self._settings = settings
        self._gateway = gateway
        self._clock = clock
        self._profiles = CandidateProfileService(session)
        self._flow = OidcFlow(session, settings, gateway, clock)

    async def start_link(self, user: User, payload: FspLinkStart) -> FspAuthorizationRead:
        """Начинает привязку: проверяет согласие и возвращает адрес входа ФСП ID."""
        self._flow.require_enabled()
        if not payload.consent:
            raise ConsentRequiredError(
                "Чтобы привязать ФСП ID, разрешите получать ваши данные из реестра ФСП"
            )
        profile = await self._profiles.ensure_profile(user)
        if await fsp_link_crud.get_for_candidate(self._session, profile.id) is not None:
            raise ConflictError("ФСП ID уже привязан. Чтобы сменить его, сначала отвяжите текущий")
        authorization = await self._flow.begin(OidcFlowPurpose.LINK, user.id)
        await self._session.commit()
        return authorization

    async def complete_link(
        self, user: User, payload: FspCallback, client: ClientContext
    ) -> FspProfileRead:
        """Завершает привязку: проверяет вход, сохраняет участника и загружает его участия.

        Сразу после входа реестр читается токеном самого участника: платформа
        получает ровно то, что участник разрешил на странице ФСП ID.
        """
        identity, tokens = await self._flow.finish(OidcFlowPurpose.LINK, payload, user.id)
        profile = await self._profiles.ensure_profile(user, for_update=True)
        owner = await fsp_link_crud.get_by_participant(self._session, identity.participant_id)
        if owner is not None and owner.candidate_id != profile.id:
            raise FspAlreadyLinkedError()
        link = await fsp_link_crud.get_for_candidate(self._session, profile.id)
        if link is not None and link.participant_id != identity.participant_id:
            raise ConflictError("Профиль уже привязан к другому ФСП ID")
        if link is None:
            try:
                link = await fsp_link_crud.create(
                    self._session,
                    {
                        "candidate_id": profile.id,
                        "participant_id": identity.participant_id,
                        "region": identity.region,
                    },
                )
            except IntegrityError as error:
                await self._session.rollback()
                raise FspAlreadyLinkedError() from error
        await self._grant_consent(user, client.ip_address)
        await audit_log_crud.record(
            self._session,
            actor_user_id=user.id,
            action="fsp_linked",
            entity_type="candidate_profile",
            entity_id=profile.id,
            meta={"participant_id": identity.participant_id},
        )
        await self._sync(profile, link, access_token=tokens.access_token)
        await self._session.commit()
        return await self._overview(profile)

    async def overview(self, user: User) -> FspProfileRead:
        """Состояние ФСП кандидата, участия, балл и вклад в индекс профиля."""
        profile = await self._profiles.ensure_profile(user)
        await self._session.commit()
        return await self._overview(profile)

    async def sync(self, user: User) -> FspProfileRead:
        """Повторная синхронизация с реестром сервисным токеном платформы."""
        self._flow.require_enabled()
        profile = await self._profiles.ensure_profile(user)
        link = await fsp_link_crud.get_for_candidate(self._session, profile.id, for_update=True)
        if link is None:
            raise FspNotLinkedError()
        if await consent_crud.active(self._session, user.id, ConsentType.FSP_DATA_ACCESS) is None:
            raise ConsentRequiredError("Согласие на получение данных ФСП отозвано")
        await self._sync(profile, link)
        await self._session.commit()
        return await self._overview(profile)

    async def unlink(self, user: User) -> None:
        """Отвязывает ФСП ID: удаляет участия и привязку, отзывает согласие на данные ФСП."""
        profile = await self._profiles.ensure_profile(user)
        link = await fsp_link_crud.get_for_candidate(self._session, profile.id, for_update=True)
        if link is None:
            raise FspNotLinkedError()
        removed = await fsp_achievement_crud.delete_for_candidate(self._session, profile.id)
        participant_id = link.participant_id
        await fsp_link_crud.remove(self._session, link)
        await consent_crud.revoke_active(
            self._session, user.id, ConsentType.FSP_DATA_ACCESS, self._clock()
        )
        await audit_log_crud.record(
            self._session,
            actor_user_id=user.id,
            action="fsp_unlinked",
            entity_type="candidate_profile",
            entity_id=profile.id,
            meta={"participant_id": participant_id, "removed_achievements": removed},
        )
        await self._session.commit()

    async def link_participant(
        self, user: User, profile: CandidateProfile, participant_id: str
    ) -> FspSyncLog:
        """Привязывает участника без входа через ФСП ID и сразу синхронизирует.

        Нужен только демо-сиду: так выглядят кандидаты, которые привязали ФСП ID
        раньше. Согласие записывается так же, как при обычной привязке.
        """
        link = await fsp_link_crud.create(
            self._session, {"candidate_id": profile.id, "participant_id": participant_id}
        )
        await self._grant_consent(user, None)
        log = await self._sync(profile, link)
        await self._session.commit()
        return log

    async def _grant_consent(self, user: User, ip_address: str | None) -> None:
        """Записывает согласие на получение данных ФСП, если действующего ещё нет."""
        if await consent_crud.active(self._session, user.id, ConsentType.FSP_DATA_ACCESS) is None:
            await consent_crud.grant(
                self._session,
                user_id=user.id,
                consent_type=ConsentType.FSP_DATA_ACCESS,
                document_version=FSP_DATA_POLICY_VERSION,
                ip_address=ip_address,
            )

    async def _sync(
        self, profile: CandidateProfile, link: FspLink, *, access_token: str | None = None
    ) -> FspSyncLog:
        """Заменяет участия снимком реестра и пишет итог в журнал.

        Недоступность реестра — штатная ситуация: прошлые данные остаются, в журнал
        пишется ошибка, а кандидат видит дату последней удачной синхронизации.
        """
        now = self._clock()
        try:
            record = await self._gateway.registry.achievements(
                link.participant_id, access_token=access_token
            )
        except FspUnavailableError as error:
            logger.warning("Реестр ФСП недоступен для %s: %s", link.participant_id, error.message)
            return await fsp_sync_log_crud.create(
                self._session,
                {
                    "candidate_id": profile.id,
                    "status": FspSyncStatus.ERROR,
                    "error": error.message,
                    "synced_at": now,
                },
            )
        rows = _registry_rows(record.achievements)
        await fsp_achievement_crud.replace_for_candidate(self._session, profile.id, rows, now)
        link.synced_at = now
        link.region = record.region
        link.sport_rank = record.sport_rank
        return await fsp_sync_log_crud.create(
            self._session,
            {
                "candidate_id": profile.id,
                "status": FspSyncStatus.OK if rows else FspSyncStatus.EMPTY,
                "achievements_count": len(rows),
                "synced_at": now,
            },
        )

    async def _overview(self, profile: CandidateProfile) -> FspProfileRead:
        """Собирает состояние ФСП и собственный индекс профиля кандидата."""
        link = await fsp_link_crud.get_for_candidate(self._session, profile.id)
        achievements = await fsp_achievement_crud.list_for_candidate(self._session, profile.id)
        privacy = await privacy_settings_crud.get_or_create(self._session, profile.id)
        last_sync = await fsp_sync_log_crud.latest_for_candidate(self._session, profile.id)
        consent = await consent_crud.active(
            self._session, profile.user_id, ConsentType.FSP_DATA_ACCESS
        )
        standing = fsp_standing(link, achievements, visible=True, today=self._clock().date())
        members = await CandidatePoolService(self._session, self._clock).load(
            PoolQuery(candidate_ids=[profile.id], published_only=False)
        )
        return FspProfileRead(
            enabled=self._settings.fsp_enabled,
            state=standing.state,
            message=NOT_LINKED_HINT if standing.state is FspState.NOT_LINKED else standing.message,
            participant_id=link.participant_id if link else None,
            linked_at=link.linked_at if link else None,
            synced_at=link.synced_at if link else None,
            region=link.region if link else None,
            sport_rank=link.sport_rank if link else None,
            consent_active=consent is not None,
            visible_to_employers=privacy.show_fsp_achievements,
            last_sync=FspSyncRead.model_validate(last_sync) if last_sync else None,
            score=score_read(standing.score),
            achievements=[FspAchievementRead.model_validate(item) for item in achievements],
            verified_score=verified_score_read(members[0].score) if members else None,
        )
