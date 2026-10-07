import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from app.crud import (
    candidate_profile_crud,
    microtask_assignment_crud,
    microtask_crud,
    specialization_crud,
)
from app.crud.candidate_search import PoolQuery
from app.crud.microtask import TaskStats
from app.models.microtask import AssignmentStatus, MicroTask, MicroTaskKind, MicroTaskStatus
from app.models.notification import NotificationKind
from app.models.user import User
from app.schemas.microtask import (
    GradeRequest,
    MicroTaskCreate,
    MicroTaskRead,
    SubmissionCandidateRead,
    SubmissionRead,
    TaskStatsRead,
)
from app.services.employer.company_service import CompanyService
from app.services.matching.candidate_pool import CandidatePoolService, members_by_id
from app.services.microtasks.grading import ANSWER_CHOICE, ANSWER_NUMBER, rating_to_score
from app.services.notifications import NotificationService


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def answer_key(payload: MicroTaskCreate) -> dict[str, Any]:
    """Эталон задачи «решить»: номер верного варианта или число с допуском."""
    if payload.kind is not MicroTaskKind.SOLVE:
        return {}
    if payload.options:
        return {"kind": ANSWER_CHOICE, "correct": payload.correct_option}
    return {
        "kind": ANSWER_NUMBER,
        "value": payload.answer_value,
        "tolerance": payload.answer_tolerance,
    }


class EmployerTaskService:
    """Микрозадачи компании: создание, архив, ответы кандидатов и оценка подходов.

    Автор ответа виден обезличенно, как в банке: задача — повод заметить человека и
    пригласить его, а не способ получить контакты в обход согласия.
    """

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени."""
        self._session = session
        self._clock = clock
        self._companies = CompanyService(session, clock)
        self._pool = CandidatePoolService(session, clock)
        self._notifications = NotificationService(session, clock)

    async def list_for_company(self, user: User) -> list[MicroTaskRead]:
        """Задачи компании со статистикой ответов."""
        recruiter = await self._companies.require_recruiter(user)
        tasks = list(await microtask_crud.list_for_company(self._session, recruiter.company_id))
        return await self._views(tasks)

    async def create(self, user: User, payload: MicroTaskCreate) -> MicroTaskRead:
        """Создаёт задачу; она сразу попадает в выдачу кандидатам специализации."""
        recruiter = await self._companies.require_recruiter(user)
        await self._validate(payload)
        task = await microtask_crud.create(
            self._session,
            {
                "company_id": recruiter.company_id,
                "author_user_id": user.id,
                "specialization_id": payload.specialization_id,
                "kind": payload.kind,
                "title": payload.title,
                "statement": payload.statement,
                "options": payload.options if payload.kind is MicroTaskKind.SOLVE else [],
                "answer_key": answer_key(payload),
                "rubric": payload.rubric,
                "time_limit_minutes": payload.time_limit_minutes,
            },
        )
        await self._session.commit()
        return (await self._views([task]))[0]

    async def archive(self, user: User, task_id: uuid.UUID) -> MicroTaskRead:
        """Убирает задачу из выдачи. Уже выданные кандидаты дорешивают её."""
        task = await self._own(user, task_id)
        task.status = MicroTaskStatus.ARCHIVED
        await self._session.commit()
        return (await self._views([task]))[0]

    async def submissions(self, user: User, task_id: uuid.UUID) -> list[SubmissionRead]:
        """Ответы кандидатов на задачу — обезличенно."""
        task = await self._own(user, task_id)
        assignments = list(await microtask_assignment_crud.list_for_task(self._session, task.id))
        members = members_by_id(
            await self._pool.load(
                PoolQuery(
                    candidate_ids=[item.candidate_id for item in assignments],
                    published_only=False,
                )
            )
        )
        result = []
        for assignment in assignments:
            member = members.get(assignment.candidate_id)
            profile = (
                member.row.profile
                if member
                else await candidate_profile_crud.get(self._session, assignment.candidate_id)
            )
            result.append(
                SubmissionRead(
                    id=assignment.id,
                    status=assignment.status,
                    submitted_at=assignment.submitted_at,
                    answer=assignment.answer,
                    score=assignment.score,
                    rating=assignment.rating,
                    feedback=assignment.feedback,
                    graded_at=assignment.graded_at,
                    candidate=SubmissionCandidateRead(
                        candidate_id=assignment.candidate_id,
                        alias=profile.public_alias if profile else "—",
                        category_title=member.category.title if member else None,
                        grade_status=("confirmed" if member.facts.confirmed else "unconfirmed")
                        if member
                        else None,
                    ),
                )
            )
        return result

    async def grade(
        self, user: User, assignment_id: uuid.UUID, payload: GradeRequest
    ) -> SubmissionRead:
        """Оценка подхода 1–5 с комментарием; кандидат получает уведомление."""
        recruiter = await self._companies.require_recruiter(user)
        found = await microtask_assignment_crud.get_for_company(
            self._session, assignment_id, recruiter.company_id, for_update=True
        )
        if found is None:
            raise NotFoundError("Ответ не найден")
        assignment, task = found
        if task.kind is not MicroTaskKind.APPROACH:
            raise ConflictError("Задачи «решить» проверяет система по эталону")
        if assignment.status is not AssignmentStatus.SUBMITTED:
            raise ConflictError("Этот ответ уже оценён или ещё не отправлен")
        now = self._clock()
        assignment.rating = payload.rating
        assignment.score = rating_to_score(payload.rating)
        assignment.feedback = payload.feedback.strip()
        assignment.status = AssignmentStatus.GRADED
        assignment.graded_at = now
        assignment.graded_by = user.id
        profile = await candidate_profile_crud.get(self._session, assignment.candidate_id)
        if profile is not None:
            await self._notifications.notify(
                profile.user_id,
                NotificationKind.MICROTASK_GRADED,
                title="Подход оценён",
                text=f"«{task.title}»: {payload.rating} из 5",
                link="/c/tasks",
            )
        await self._session.commit()
        submissions = await self.submissions(user, task.id)
        return next(item for item in submissions if item.id == assignment.id)

    async def _own(self, user: User, task_id: uuid.UUID) -> MicroTask:
        """Задача своей компании или 404."""
        recruiter = await self._companies.require_recruiter(user)
        task = await microtask_crud.get_for_company(self._session, task_id, recruiter.company_id)
        if task is None:
            raise NotFoundError("Задача не найдена")
        return task

    async def _validate(self, payload: MicroTaskCreate) -> None:
        """Специализация задачи существует."""
        if await specialization_crud.get(self._session, payload.specialization_id) is None:
            raise DomainValidationError(
                "Специализация не найдена", details={"field": "specialization_id"}
            )

    async def _views(self, tasks: list[MicroTask]) -> list[MicroTaskRead]:
        """Задачи для ответа API вместе с эталоном и статистикой."""
        specializations = {
            item.id: item.name for item in await specialization_crud.list_all(self._session)
        }
        stats = await microtask_crud.stats(self._session, [task.id for task in tasks])
        result = []
        for task in tasks:
            key = task.answer_key or {}
            task_stats = stats.get(task.id, TaskStats())
            result.append(
                MicroTaskRead(
                    id=task.id,
                    kind=task.kind,
                    title=task.title,
                    statement=task.statement,
                    specialization_id=task.specialization_id,
                    specialization_name=specializations.get(task.specialization_id, ""),
                    options=task.options,
                    answer_value=key.get("value") if key.get("kind") == ANSWER_NUMBER else None,
                    answer_tolerance=float(key.get("tolerance", 0.0)),
                    correct_option=key.get("correct") if key.get("kind") == ANSWER_CHOICE else None,
                    rubric=task.rubric,
                    time_limit_minutes=task.time_limit_minutes,
                    status=task.status,
                    created_at=task.created_at,
                    stats=TaskStatsRead(
                        assigned=task_stats.assigned,
                        answered=task_stats.answered,
                        graded=task_stats.graded,
                        awaiting_review=task_stats.awaiting_review,
                        average_score=task_stats.average_score,
                    ),
                )
            )
        return result
