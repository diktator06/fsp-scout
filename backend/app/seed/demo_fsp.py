import asyncio
import logging
import uuid
from random import Random

from app.core.config import Settings
from app.core.exceptions import FspUnavailableError
from app.crud import candidate_profile_crud, fsp_link_crud, user_crud
from app.integrations.fsp_gateway import FspGateway, build_fsp_gateway
from app.integrations.fsp_registry import RegistryParticipant
from app.models.fsp import FspSyncStatus
from app.seed.demo_population import CONCURRENCY, SessionFactory
from app.services.fsp.fsp_service import FspService

logger = logging.getLogger(__name__)

FSP_SEED = 2027
SYNTHETIC_EMAIL_PREFIX = "demo."
THETA_NOISE = 0.6
STRENGTH_NOISE = 0.8


def participant_strength(participant: RegistryParticipant, rng: Random) -> float:
    """Сила истории участника для подбора пары: результаты важнее числа стартов."""
    return (
        2.0 * participant.results
        + participant.finals
        + 0.3 * participant.events
        + rng.gauss(0, STRENGTH_NOISE)
    )


def spread(items: list[RegistryParticipant], count: int) -> list[RegistryParticipant]:
    """Равномерная выборка из отсортированного списка: от слабых историй до сильных."""
    if count <= 0 or not items:
        return []
    if count >= len(items):
        return list(items)
    step = (len(items) - 1) / max(1, count - 1)
    return [items[round(index * step)] for index in range(count)]


async def seed_demo_fsp_links(
    session_factory: SessionFactory, settings: Settings, gateway: FspGateway | None = None
) -> str:
    """Привязывает часть синтетических кандидатов к участникам эмулятора ФСП ID.

    Пары подбираются так, чтобы история ФСП коррелировала со способностью: сильные
    по тесту чаще оказываются призёрами, но с шумом, как в жизни. Среди привязанных
    есть и участники без истории — состояние «привязан без участий». Демо-персоны
    эмулятора не занимаются: их привязывают к демо-аккаунту на показе.

    Повторный запуск ничего не меняет. Если эмулятор недоступен, шаг пропускается:
    стенд работает и без ФСП, это штатное состояние.
    """
    if not settings.fsp_enabled or settings.demo_fsp_link_share <= 0:
        return "привязка ФСП в демо-данных отключена"
    gateway = gateway or build_fsp_gateway(settings)
    async with session_factory() as session:
        candidates = await candidate_profile_crud.list_with_theta_by_email_prefix(
            session, SYNTHETIC_EMAIL_PREFIX
        )
        linked = await fsp_link_crud.linked_participant_ids(session)
        already = await fsp_link_crud.for_candidates(
            session, [profile.id for profile, _, _ in candidates]
        )
    if already:
        return f"привязки ФСП уже есть у {len(already)} кандидатов"
    try:
        participants = await gateway.registry.participants(limit=500)
    except FspUnavailableError as error:
        logger.warning("Эмулятор ФСП недоступен, привязки пропущены: %s", error.message)
        return "эмулятор ФСП недоступен — привязки пропущены"

    rng = Random(FSP_SEED)
    tested = [item for item in candidates if item[2] is not None]
    chosen = rng.sample(tested, k=round(len(tested) * settings.demo_fsp_link_share))
    chosen.sort(key=lambda item: (item[2] or 0.0) + rng.gauss(0, THETA_NOISE))
    pool = sorted(
        (item for item in participants if not item.demo_persona and item.id not in linked),
        key=lambda item: participant_strength(item, rng),
    )
    pairs = list(zip(chosen, spread(pool, len(chosen)), strict=False))
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def attach(user_id: uuid.UUID, participant_id: str) -> FspSyncStatus | None:
        """Привязывает одного кандидата в отдельной сессии."""
        async with semaphore, session_factory() as pair_session:
            user = await user_crud.get(pair_session, user_id)
            profile = await candidate_profile_crud.get_by_user_id(pair_session, user_id)
            if user is None or profile is None:
                return None
            service = FspService(pair_session, settings, gateway)
            log = await service.link_participant(user, profile, participant_id)
            return log.status

    statuses = await asyncio.gather(
        *(attach(user.id, participant.id) for (_, user, _), participant in pairs)
    )
    empty = sum(1 for status in statuses if status is FspSyncStatus.EMPTY)
    failed = sum(1 for status in statuses if status is FspSyncStatus.ERROR)
    return f"привязано к ФСП ID: {len(pairs)}, без участий: {empty}, ошибок реестра: {failed}"
