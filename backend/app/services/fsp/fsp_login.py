from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AccountDisabledError, FspNotLinkedError
from app.crud import audit_log_crud, fsp_link_crud, user_crud
from app.integrations.fsp_gateway import FspGateway
from app.models.fsp import OidcFlowPurpose
from app.schemas.fsp import FspAuthorizationRead, FspCallback
from app.services.auth.auth_service import AuthenticatedSession
from app.services.auth.tokens import ClientContext, issue_session_tokens
from app.services.fsp.oidc_flow import OidcFlow


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class FspLoginService:
    """Вход в «Скаут» через ФСП ID для аккаунтов, к которым ФСП ID уже привязан.

    Аккаунт по ФСП ID не создаётся: у участника в реестре нет подтверждённого email,
    а без него не работают уведомления и раскрытие контактов. Поэтому сначала
    регистрация по email, затем привязка ФСП ID в кабинете — и дальше вход в один клик.
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
        self._clock = clock
        self._flow = OidcFlow(session, settings, gateway, clock)

    async def start(self) -> FspAuthorizationRead:
        """Начинает вход: адрес страницы ФСП ID."""
        authorization = await self._flow.begin(OidcFlowPurpose.LOGIN, None)
        await self._session.commit()
        return authorization

    async def complete(self, payload: FspCallback, client: ClientContext) -> AuthenticatedSession:
        """Завершает вход: находит аккаунт по привязанному участнику и открывает сессию."""
        identity, _ = await self._flow.finish(OidcFlowPurpose.LOGIN, payload, None)
        user_id = await fsp_link_crud.user_id_by_participant(self._session, identity.participant_id)
        user = await user_crud.get(self._session, user_id) if user_id else None
        if user is None:
            raise FspNotLinkedError(
                "Этот ФСП ID не привязан к аккаунту «Скаута». Войдите по email "
                "и привяжите ФСП ID в разделе «Достижения ФСП» кабинета кандидата"
            )
        if not user.is_active:
            raise AccountDisabledError()
        now = self._clock()
        await user_crud.register_login(self._session, user, now)
        tokens, _ = await issue_session_tokens(
            self._session, user, self._settings, client=client, now=now
        )
        await audit_log_crud.record(
            self._session,
            actor_user_id=user.id,
            action="login_fsp_id",
            entity_type="user",
            entity_id=user.id,
            meta={"participant_id": identity.participant_id},
        )
        await self._session.commit()
        return AuthenticatedSession(user=user, tokens=tokens)
