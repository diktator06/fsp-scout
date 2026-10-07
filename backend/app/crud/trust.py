import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.invitation import Invitation, InvitationStatus
from app.models.trust import Complaint, ComplaintStatus, ComplaintTarget
from app.models.vacancy import Application, ApplicationStatus

_ANSWERED_INVITATIONS = (InvitationStatus.ACCEPTED, InvitationStatus.DECLINED)
_ANSWERED_APPLICATIONS = (ApplicationStatus.INTERVIEW, ApplicationStatus.REJECTED)


@dataclass(frozen=True, slots=True)
class ReputationCounts:
    """Сырые счётчики поведения компании на платформе."""

    invitations_sent: int = 0
    invitations_answered: int = 0
    invitations_accepted: int = 0
    applications_received: int = 0
    applications_answered: int = 0
    complaints_confirmed: int = 0


class ComplaintCRUD(CRUDBase[Complaint]):
    """Доступ к жалобам."""

    async def get_by_target(
        self,
        session: AsyncSession,
        author_user_id: uuid.UUID,
        target_type: ComplaintTarget,
        target_id: uuid.UUID,
    ) -> Complaint | None:
        """Жалоба автора на объект — повторно жаловаться на тот же объект нельзя."""
        return await session.scalar(
            select(Complaint).where(
                Complaint.author_user_id == author_user_id,
                Complaint.target_type == target_type,
                Complaint.target_id == target_id,
            )
        )

    async def distinct_open_authors(
        self, session: AsyncSession, company_id: uuid.UUID, since: datetime
    ) -> int:
        """Сколько разных кандидатов пожаловались на компанию за период и ждут решения."""
        total = await session.scalar(
            select(func.count(func.distinct(Complaint.author_user_id))).where(
                Complaint.company_id == company_id,
                Complaint.status == ComplaintStatus.OPEN,
                Complaint.created_at >= since,
            )
        )
        return int(total or 0)

    async def list_for_moderation(
        self, session: AsyncSession, status: ComplaintStatus | None
    ) -> Sequence[Complaint]:
        """Жалобы для модератора: открытые выше, новые выше старых."""
        statement = select(Complaint)
        if status is not None:
            statement = statement.where(Complaint.status == status)
        result = await session.scalars(
            statement.order_by(Complaint.status, Complaint.created_at.desc())
        )
        return result.all()

    async def counts_by_company(
        self, session: AsyncSession, company_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, dict[ComplaintStatus, int]]:
        """Жалобы по компаниям в разрезе статусов."""
        ids = list(set(company_ids))
        if not ids:
            return {}
        result = await session.execute(
            select(Complaint.company_id, Complaint.status, func.count())
            .where(Complaint.company_id.in_(ids))
            .group_by(Complaint.company_id, Complaint.status)
        )
        counts: dict[uuid.UUID, dict[ComplaintStatus, int]] = {}
        for company_id, status, total in result.all():
            counts.setdefault(company_id, {})[status] = int(total)
        return counts


class ReputationCRUD:
    """Счётчики поведения компаний для репутации — одним запросом на вид данных."""

    async def counts(
        self, session: AsyncSession, company_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, ReputationCounts]:
        """Приглашения, отклики и подтверждённые жалобы по каждой компании."""
        ids = list(set(company_ids))
        if not ids:
            return {}
        invitations = await session.execute(
            select(Invitation.company_id, Invitation.status, func.count())
            .where(Invitation.company_id.in_(ids))
            .group_by(Invitation.company_id, Invitation.status)
        )
        applications = await session.execute(
            select(Application.company_id, Application.status, func.count())
            .where(Application.company_id.in_(ids))
            .group_by(Application.company_id, Application.status)
        )
        complaints = await session.execute(
            select(Complaint.company_id, func.count())
            .where(Complaint.company_id.in_(ids), Complaint.status == ComplaintStatus.CONFIRMED)
            .group_by(Complaint.company_id)
        )
        raw: dict[uuid.UUID, dict[str, int]] = {company_id: {} for company_id in ids}
        for company_id, status, total in invitations.all():
            row = raw[company_id]
            row["sent"] = row.get("sent", 0) + int(total)
            if status in _ANSWERED_INVITATIONS:
                row["answered"] = row.get("answered", 0) + int(total)
            if status is InvitationStatus.ACCEPTED:
                row["accepted"] = row.get("accepted", 0) + int(total)
        for company_id, application_status, total in applications.all():
            row = raw[company_id]
            if application_status is not ApplicationStatus.WITHDRAWN:
                row["applications"] = row.get("applications", 0) + int(total)
            if application_status in _ANSWERED_APPLICATIONS:
                row["applications_answered"] = row.get("applications_answered", 0) + int(total)
        for company_id, total in complaints.all():
            raw[company_id]["complaints"] = int(total)
        return {
            company_id: ReputationCounts(
                invitations_sent=row.get("sent", 0),
                invitations_answered=row.get("answered", 0),
                invitations_accepted=row.get("accepted", 0),
                applications_received=row.get("applications", 0),
                applications_answered=row.get("applications_answered", 0),
                complaints_confirmed=row.get("complaints", 0),
            )
            for company_id, row in raw.items()
        }


complaint_crud = ComplaintCRUD(Complaint)
reputation_crud = ReputationCRUD()
