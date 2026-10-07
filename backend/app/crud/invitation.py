import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.invitation import (
    ACTIVE_INVITATION_STATUSES,
    ContactDisclosure,
    Invitation,
    InvitationEvent,
    InvitationStatus,
)


class InvitationCRUD(CRUDBase[Invitation]):
    """Доступ к приглашениям."""

    async def get_for_company(
        self,
        session: AsyncSession,
        invitation_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Invitation | None:
        """Приглашение компании. Чужое не найти даже по точному id."""
        statement = select(Invitation).where(
            Invitation.id == invitation_id, Invitation.company_id == company_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def get_for_candidate(
        self,
        session: AsyncSession,
        invitation_id: uuid.UUID,
        candidate_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Invitation | None:
        """Приглашение кандидата. Чужое не найти даже по точному id."""
        statement = select(Invitation).where(
            Invitation.id == invitation_id, Invitation.candidate_id == candidate_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def list_for_company(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        *,
        statuses: Iterable[InvitationStatus] = (),
        need_id: uuid.UUID | None = None,
    ) -> Sequence[Invitation]:
        """Приглашения компании, от новых к старым, с фильтром по статусам и потребности."""
        statement = (
            select(Invitation)
            .where(Invitation.company_id == company_id)
            .order_by(Invitation.created_at.desc())
        )
        status_list = list(statuses)
        if status_list:
            statement = statement.where(Invitation.status.in_(status_list))
        if need_id is not None:
            statement = statement.where(Invitation.need_id == need_id)
        result = await session.scalars(statement)
        return result.all()

    async def list_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> Sequence[Invitation]:
        """Приглашения кандидата, от новых к старым."""
        result = await session.scalars(
            select(Invitation)
            .where(Invitation.candidate_id == candidate_id)
            .order_by(Invitation.created_at.desc())
        )
        return result.all()

    async def active_for_pair(
        self, session: AsyncSession, company_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> Invitation | None:
        """Активное (отправленное или просмотренное) приглашение пары, если есть."""
        return await session.scalar(
            select(Invitation).where(
                Invitation.company_id == company_id,
                Invitation.candidate_id == candidate_id,
                Invitation.status.in_(ACTIVE_INVITATION_STATUSES),
            )
        )

    async def latest_by_candidate(
        self, session: AsyncSession, company_id: uuid.UUID, candidate_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, Invitation]:
        """Последнее приглашение компании каждому из кандидатов (для меток в выдаче)."""
        ids = list(candidate_ids)
        if not ids:
            return {}
        result = await session.scalars(
            select(Invitation)
            .where(Invitation.company_id == company_id, Invitation.candidate_id.in_(ids))
            .order_by(Invitation.candidate_id, Invitation.created_at.desc())
            .ext(distinct_on(Invitation.candidate_id))
        )
        return {invitation.candidate_id: invitation for invitation in result.all()}

    async def count_created_since(
        self, session: AsyncSession, company_id: uuid.UUID, since: datetime
    ) -> int:
        """Сколько приглашений компания отправила начиная с момента (для дневной квоты)."""
        total = await session.scalar(
            select(func.count())
            .select_from(Invitation)
            .where(Invitation.company_id == company_id, Invitation.created_at >= since)
        )
        return int(total or 0)

    async def status_counts(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> dict[InvitationStatus, int]:
        """Сколько приглашений компании в каждом статусе: воронка на главной кабинета."""
        result = await session.execute(
            select(Invitation.status, func.count())
            .where(Invitation.company_id == company_id)
            .group_by(Invitation.status)
        )
        return {status: int(count) for status, count in result.all()}

    async def overdue_for_update(
        self,
        session: AsyncSession,
        now: datetime,
        *,
        candidate_id: uuid.UUID | None = None,
        company_id: uuid.UUID | None = None,
    ) -> Sequence[Invitation]:
        """Активные приглашения с истёкшим сроком, заблокированные для смены статуса.

        `SKIP LOCKED` позволяет двум параллельным запросам не ждать друг друга: каждое
        приглашение переведёт в «истекло» тот, кто первым его заблокировал.
        """
        statement = (
            select(Invitation)
            .where(
                Invitation.status.in_(ACTIVE_INVITATION_STATUSES),
                Invitation.expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        if candidate_id is not None:
            statement = statement.where(Invitation.candidate_id == candidate_id)
        if company_id is not None:
            statement = statement.where(Invitation.company_id == company_id)
        result = await session.scalars(statement)
        return result.all()


class InvitationEventCRUD(CRUDBase[InvitationEvent]):
    """Доступ к журналу переходов приглашений."""

    async def list_for_invitations(
        self, session: AsyncSession, invitation_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, list[InvitationEvent]]:
        """События приглашений в хронологическом порядке, сгруппированные по приглашению."""
        ids = list(invitation_ids)
        if not ids:
            return {}
        result = await session.scalars(
            select(InvitationEvent)
            .where(InvitationEvent.invitation_id.in_(ids))
            .order_by(InvitationEvent.created_at, InvitationEvent.id)
        )
        grouped: dict[uuid.UUID, list[InvitationEvent]] = {}
        for event in result.all():
            grouped.setdefault(event.invitation_id, []).append(event)
        return grouped


class ContactDisclosureCRUD(CRUDBase[ContactDisclosure]):
    """Доступ к раскрытиям контактов. Это единственный источник права видеть контакты."""

    async def get_for_pair(
        self, session: AsyncSession, company_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> ContactDisclosure | None:
        """Раскрытие контактов кандидата компании, если оно было."""
        return await session.scalar(
            select(ContactDisclosure).where(
                ContactDisclosure.company_id == company_id,
                ContactDisclosure.candidate_id == candidate_id,
            )
        )

    async def disclosed_candidates(
        self, session: AsyncSession, company_id: uuid.UUID, candidate_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, ContactDisclosure]:
        """Какие из кандидатов уже раскрыли компании контакты."""
        ids = list(candidate_ids)
        if not ids:
            return {}
        result = await session.scalars(
            select(ContactDisclosure).where(
                ContactDisclosure.company_id == company_id,
                ContactDisclosure.candidate_id.in_(ids),
            )
        )
        return {item.candidate_id: item for item in result.all()}


invitation_crud = InvitationCRUD(Invitation)
invitation_event_crud = InvitationEventCRUD(InvitationEvent)
contact_disclosure_crud = ContactDisclosureCRUD(ContactDisclosure)
