import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.candidate import CandidateProfile
from app.models.fsp import FspAchievement, FspLink, FspSyncLog, OidcFlowState


class FspLinkCRUD(CRUDBase[FspLink]):
    """Доступ к привязкам профилей к ФСП ID."""

    async def get_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID, *, for_update: bool = False
    ) -> FspLink | None:
        """Привязка профиля, если есть."""
        statement = select(FspLink).where(FspLink.candidate_id == candidate_id)
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def get_by_participant(
        self, session: AsyncSession, participant_id: str
    ) -> FspLink | None:
        """Привязка по идентификатору участника ФСП."""
        return await session.scalar(select(FspLink).where(FspLink.participant_id == participant_id))

    async def user_id_by_participant(
        self, session: AsyncSession, participant_id: str
    ) -> uuid.UUID | None:
        """Пользователь, чей профиль привязан к участнику ФСП: нужен для входа через ФСП ID."""
        return await session.scalar(
            select(CandidateProfile.user_id)
            .join(FspLink, FspLink.candidate_id == CandidateProfile.id)
            .where(FspLink.participant_id == participant_id)
        )

    async def for_candidates(
        self, session: AsyncSession, candidate_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, FspLink]:
        """Привязки пачки профилей."""
        ids = list(set(candidate_ids))
        if not ids:
            return {}
        result = await session.scalars(select(FspLink).where(FspLink.candidate_id.in_(ids)))
        return {item.candidate_id: item for item in result.all()}

    async def linked_participant_ids(self, session: AsyncSession) -> set[str]:
        """Все уже привязанные участники ФСП."""
        result = await session.scalars(select(FspLink.participant_id))
        return set(result.all())

    async def remove(self, session: AsyncSession, link: FspLink) -> None:
        """Удаляет привязку."""
        await session.delete(link)
        await session.flush()


class FspAchievementCRUD(CRUDBase[FspAchievement]):
    """Доступ к копии достижений из реестра ФСП."""

    async def list_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> Sequence[FspAchievement]:
        """Участия кандидата, от свежих к старым."""
        result = await session.scalars(
            select(FspAchievement)
            .where(FspAchievement.candidate_id == candidate_id)
            .order_by(FspAchievement.event_date.desc(), FspAchievement.event_name)
        )
        return result.all()

    async def for_candidates(
        self, session: AsyncSession, candidate_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, list[FspAchievement]]:
        """Участия пачки кандидатов одним запросом."""
        ids = list(set(candidate_ids))
        if not ids:
            return {}
        result = await session.scalars(
            select(FspAchievement)
            .where(FspAchievement.candidate_id.in_(ids))
            .order_by(FspAchievement.event_date.desc(), FspAchievement.event_name)
        )
        grouped: dict[uuid.UUID, list[FspAchievement]] = {}
        for item in result.all():
            grouped.setdefault(item.candidate_id, []).append(item)
        return grouped

    async def replace_for_candidate(
        self,
        session: AsyncSession,
        candidate_id: uuid.UUID,
        rows: Sequence[dict[str, Any]],
        synced_at: datetime,
    ) -> None:
        """Заменяет участия кандидата снимком реестра.

        Реестр — источник истины: если он исправил или удалил запись, у нас она тоже
        меняется. Поэтому снимок заменяется целиком, а не дописывается.
        """
        await session.execute(
            delete(FspAchievement).where(FspAchievement.candidate_id == candidate_id)
        )
        session.add_all(
            FspAchievement(candidate_id=candidate_id, synced_at=synced_at, **row) for row in rows
        )
        await session.flush()

    async def delete_for_candidate(self, session: AsyncSession, candidate_id: uuid.UUID) -> int:
        """Удаляет все участия кандидата; возвращает, сколько удалено."""
        result = await session.execute(
            delete(FspAchievement).where(FspAchievement.candidate_id == candidate_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)


class FspSyncLogCRUD(CRUDBase[FspSyncLog]):
    """Доступ к журналу синхронизаций с реестром."""

    async def latest_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> FspSyncLog | None:
        """Последняя синхронизация кандидата."""
        return await session.scalar(
            select(FspSyncLog)
            .where(FspSyncLog.candidate_id == candidate_id)
            .order_by(FspSyncLog.synced_at.desc())
            .limit(1)
        )


class OidcFlowStateCRUD(CRUDBase[OidcFlowState]):
    """Доступ к незавершённым входам через ФСП ID."""

    async def pop(self, session: AsyncSession, state: str) -> OidcFlowState | None:
        """Забирает запись по state и сразу удаляет её: state одноразовый."""
        entity = await session.scalar(
            select(OidcFlowState).where(OidcFlowState.state == state).with_for_update()
        )
        if entity is not None:
            await session.delete(entity)
            await session.flush()
        return entity

    async def purge_expired(self, session: AsyncSession, now: datetime) -> None:
        """Удаляет просроченные незавершённые входы."""
        await session.execute(delete(OidcFlowState).where(OidcFlowState.expires_at < now))


fsp_link_crud = FspLinkCRUD(FspLink)
fsp_achievement_crud = FspAchievementCRUD(FspAchievement)
fsp_sync_log_crud = FspSyncLogCRUD(FspSyncLog)
oidc_flow_state_crud = OidcFlowStateCRUD(OidcFlowState)
