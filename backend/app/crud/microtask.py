import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.microtask import (
    AssignmentStatus,
    MicroTask,
    MicroTaskAssignment,
    MicroTaskStatus,
)


@dataclass(frozen=True, slots=True)
class TaskStats:
    """Сколько раз задачу выдали, сколько ответов и средний балл оценённых."""

    assigned: int = 0
    answered: int = 0
    graded: int = 0
    awaiting_review: int = 0
    average_score: float | None = None


class MicroTaskCRUD(CRUDBase[MicroTask]):
    """Доступ к микрозадачам."""

    async def get_for_company(
        self, session: AsyncSession, task_id: uuid.UUID, company_id: uuid.UUID
    ) -> MicroTask | None:
        """Задача компании. Чужую не найти даже по точному id."""
        return await session.scalar(
            select(MicroTask).where(MicroTask.id == task_id, MicroTask.company_id == company_id)
        )

    async def list_for_company(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> Sequence[MicroTask]:
        """Задачи компании: активные выше архивных, новые выше старых."""
        result = await session.scalars(
            select(MicroTask)
            .where(MicroTask.company_id == company_id)
            .order_by(MicroTask.status, MicroTask.created_at.desc())
        )
        return result.all()

    async def active_for_company(
        self, session: AsyncSession, company_id: uuid.UUID, specialization_id: int
    ) -> Sequence[MicroTask]:
        """Активные задачи компании по специализации — блок вакансии у методиста."""
        result = await session.scalars(
            select(MicroTask)
            .where(
                MicroTask.company_id == company_id,
                MicroTask.specialization_id == specialization_id,
                MicroTask.status == MicroTaskStatus.ACTIVE,
            )
            .order_by(MicroTask.created_at.desc())
        )
        return result.all()

    async def offerable(
        self,
        session: AsyncSession,
        specialization_id: int,
        exclude_task_ids: Iterable[uuid.UUID],
    ) -> Sequence[MicroTask]:
        """Активные задачи специализации, которые кандидат ещё не получал."""
        statement = select(MicroTask).where(
            MicroTask.specialization_id == specialization_id,
            MicroTask.status == MicroTaskStatus.ACTIVE,
        )
        excluded = list(exclude_task_ids)
        if excluded:
            statement = statement.where(MicroTask.id.not_in(excluded))
        result = await session.scalars(statement.order_by(MicroTask.created_at))
        return result.all()

    async def stats(
        self, session: AsyncSession, task_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, TaskStats]:
        """Статистика выдачи и ответов по задачам."""
        ids = list(set(task_ids))
        if not ids:
            return {}
        result = await session.execute(
            select(
                MicroTaskAssignment.task_id,
                MicroTaskAssignment.status,
                func.count(),
                func.avg(MicroTaskAssignment.score),
            )
            .where(MicroTaskAssignment.task_id.in_(ids))
            .group_by(MicroTaskAssignment.task_id, MicroTaskAssignment.status)
        )
        raw: dict[uuid.UUID, dict[AssignmentStatus, tuple[int, float | None]]] = {}
        for task_id, status, total, average in result.all():
            raw.setdefault(task_id, {})[status] = (int(total), average)
        stats = {}
        for task_id, by_status in raw.items():
            graded, average = by_status.get(AssignmentStatus.GRADED, (0, None))
            submitted = by_status.get(AssignmentStatus.SUBMITTED, (0, None))[0]
            stats[task_id] = TaskStats(
                assigned=sum(total for total, _ in by_status.values()),
                answered=graded + submitted,
                graded=graded,
                awaiting_review=submitted,
                average_score=round(float(average), 3) if average is not None else None,
            )
        return stats


class MicroTaskAssignmentCRUD(CRUDBase[MicroTaskAssignment]):
    """Доступ к выдаче микрозадач кандидатам."""

    async def get_for_candidate(
        self,
        session: AsyncSession,
        assignment_id: uuid.UUID,
        candidate_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> MicroTaskAssignment | None:
        """Задача кандидата. Чужую не найти даже по точному id."""
        statement = select(MicroTaskAssignment).where(
            MicroTaskAssignment.id == assignment_id,
            MicroTaskAssignment.candidate_id == candidate_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def get_for_company(
        self,
        session: AsyncSession,
        assignment_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> tuple[MicroTaskAssignment, MicroTask] | None:
        """Ответ на задачу компании вместе с самой задачей."""
        statement = (
            select(MicroTaskAssignment, MicroTask)
            .join(MicroTask, MicroTask.id == MicroTaskAssignment.task_id)
            .where(MicroTaskAssignment.id == assignment_id, MicroTask.company_id == company_id)
        )
        if for_update:
            statement = statement.with_for_update(of=MicroTaskAssignment)
        row = (await session.execute(statement)).first()
        return (row[0], row[1]) if row else None

    async def list_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> Sequence[tuple[MicroTaskAssignment, MicroTask]]:
        """Задачи кандидата с самими задачами, новые выше."""
        result = await session.execute(
            select(MicroTaskAssignment, MicroTask)
            .join(MicroTask, MicroTask.id == MicroTaskAssignment.task_id)
            .where(MicroTaskAssignment.candidate_id == candidate_id)
            .order_by(MicroTaskAssignment.assigned_at.desc())
        )
        return [(row[0], row[1]) for row in result.all()]

    async def count_since(
        self, session: AsyncSession, candidate_id: uuid.UUID, since: datetime
    ) -> int:
        """Сколько задач кандидат получил с момента — для недельного лимита."""
        total = await session.scalar(
            select(func.count())
            .select_from(MicroTaskAssignment)
            .where(
                MicroTaskAssignment.candidate_id == candidate_id,
                MicroTaskAssignment.assigned_at >= since,
            )
        )
        return int(total or 0)

    async def expire_overdue(
        self, session: AsyncSession, candidate_id: uuid.UUID, now: datetime
    ) -> None:
        """Ленивое истечение: задачи без ответа после срока помечаются просроченными."""
        await session.execute(
            update(MicroTaskAssignment)
            .where(
                MicroTaskAssignment.candidate_id == candidate_id,
                MicroTaskAssignment.status == AssignmentStatus.ASSIGNED,
                MicroTaskAssignment.due_at < now,
            )
            .values(status=AssignmentStatus.EXPIRED)
        )

    async def list_for_task(
        self, session: AsyncSession, task_id: uuid.UUID
    ) -> Sequence[MicroTaskAssignment]:
        """Ответы на задачу: ждущие оценки выше остальных."""
        result = await session.scalars(
            select(MicroTaskAssignment)
            .where(
                MicroTaskAssignment.task_id == task_id,
                MicroTaskAssignment.status.in_(
                    [AssignmentStatus.SUBMITTED, AssignmentStatus.GRADED]
                ),
            )
            .order_by(MicroTaskAssignment.status, MicroTaskAssignment.submitted_at.desc())
        )
        return result.all()

    async def graded_for_candidates(
        self, session: AsyncSession, candidate_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[MicroTaskAssignment, MicroTask]]]:
        """Оценённые задачи пачки кандидатов — для фактора M в индексе профиля."""
        ids = list(set(candidate_ids))
        if not ids:
            return {}
        result = await session.execute(
            select(MicroTaskAssignment, MicroTask)
            .join(MicroTask, MicroTask.id == MicroTaskAssignment.task_id)
            .where(
                MicroTaskAssignment.candidate_id.in_(ids),
                MicroTaskAssignment.status == AssignmentStatus.GRADED,
            )
            .order_by(MicroTaskAssignment.graded_at.desc())
        )
        grouped: dict[uuid.UUID, list[tuple[MicroTaskAssignment, MicroTask]]] = {}
        for assignment, task in result.all():
            grouped.setdefault(assignment.candidate_id, []).append((assignment, task))
        return grouped


microtask_crud = MicroTaskCRUD(MicroTask)
microtask_assignment_crud = MicroTaskAssignmentCRUD(MicroTaskAssignment)
