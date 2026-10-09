import random
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError
from app.crud import (
    company_lookup_crud,
    microtask_assignment_crud,
    microtask_crud,
    recruiter_crud,
)
from app.crud.candidate_search import PoolQuery
from app.models.microtask import (
    AssignmentStatus,
    MicroTask,
    MicroTaskAssignment,
    MicroTaskKind,
)
from app.models.notification import NotificationKind
from app.models.user import User
from app.schemas.microtask import (
    AnswerFormat,
    AssignedTaskRead,
    AssignmentRead,
    FreshnessRead,
    TasksOverviewRead,
)
from app.services.candidate.profile_service import CandidateProfileService
from app.services.matching.candidate_pool import CandidatePoolService
from app.services.matching.verified_score import VPS_WEIGHTS
from app.services.microtasks.freshness import HALF_LIFE_DAYS, GradedResult, freshness
from app.services.microtasks.grading import auto_grade
from app.services.notifications import NotificationService


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def answer_format(task: MicroTask) -> AnswerFormat:
    """Как отвечать на задачу: числом, номером варианта или текстом подхода."""
    if task.kind is MicroTaskKind.APPROACH:
        return "text"
    return "choice" if task.options else "number"


def assignment_read(
    assignment: MicroTaskAssignment, task: MicroTask, company_name: str
) -> AssignmentRead:
    """Задача кандидата для ответа API. Эталона в ней нет."""
    return AssignmentRead(
        id=assignment.id,
        status=assignment.status,
        assigned_at=assignment.assigned_at,
        due_at=assignment.due_at,
        submitted_at=assignment.submitted_at,
        answer=assignment.answer,
        score=assignment.score,
        rating=assignment.rating,
        feedback=assignment.feedback,
        graded_at=assignment.graded_at,
        task=AssignedTaskRead(
            id=task.id,
            kind=task.kind,
            title=task.title,
            statement=task.statement,
            options=task.options,
            rubric=task.rubric,
            answer_format=answer_format(task),
            time_limit_minutes=task.time_limit_minutes,
            company_name=company_name,
        ),
    )


class CandidateTaskService:
    """Регулярные короткие задачи от работодателей глазами кандидата (ТЗ §2).

    Система сама предлагает задачу не чаще раза в неделю (интервал настраивается),
    по специализации кандидата и из тех, что он ещё не решал. Можно попросить
    задачу и раньше, но не больше недельного лимита: иначе фактор актуальности
    можно было бы набить. Результат входит в индекс профиля как фактор M.
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        clock: Callable[[], datetime] = _now,
        rng: random.Random | None = None,
    ) -> None:
        """Получает сессию БД, настройки, источник времени и генератор выбора задачи."""
        self._session = session
        self._settings = settings
        self._clock = clock
        self._rng = rng or random.Random()
        self._profiles = CandidateProfileService(session)
        self._pool = CandidatePoolService(session, clock)
        self._notifications = NotificationService(session, clock)

    async def overview(self, user: User) -> TasksOverviewRead:
        """Текущая задача, история и фактор M. Если пора, система предлагает новую задачу."""
        profile = await self._profiles.ensure_profile(user)
        now = self._clock()
        await microtask_assignment_crud.expire_overdue(self._session, profile.id, now)
        specialization_id = await self._specialization(profile.id)
        rows = await microtask_assignment_crud.list_for_candidate(self._session, profile.id)
        if specialization_id is not None and self._due_for_offer(rows, now):
            await self._offer(profile.id, specialization_id, [task.id for _, task in rows])
            rows = await microtask_assignment_crud.list_for_candidate(self._session, profile.id)
        await self._session.commit()
        return await self._overview(profile.id, rows, specialization_id)

    async def request(self, user: User) -> TasksOverviewRead:
        """Задача по просьбе кандидата — в пределах недельного лимита."""
        profile = await self._profiles.ensure_profile(user)
        now = self._clock()
        await microtask_assignment_crud.expire_overdue(self._session, profile.id, now)
        specialization_id = await self._specialization(profile.id)
        if specialization_id is None:
            raise ConflictError("Сначала пройдите опрос: задачи подбираются по специализации")
        rows = await microtask_assignment_crud.list_for_candidate(self._session, profile.id)
        if any(item.status is AssignmentStatus.ASSIGNED for item, _ in rows):
            raise ConflictError("Сначала ответьте на текущую задачу или пропустите её")
        if await self._requests_left(profile.id, now) <= 0:
            raise ConflictError("Недельный лимит задач исчерпан — новая появится позже")
        offered = await self._offer(profile.id, specialization_id, [task.id for _, task in rows])
        if not offered:
            raise ConflictError("Новых задач по вашей специализации пока нет")
        await self._session.commit()
        rows = await microtask_assignment_crud.list_for_candidate(self._session, profile.id)
        return await self._overview(profile.id, rows, specialization_id)

    async def submit(self, user: User, assignment_id: uuid.UUID, answer: str) -> AssignmentRead:
        """Ответ на задачу. «Решить» проверяется сразу, «подход» уходит работодателю."""
        profile = await self._profiles.ensure_profile(user)
        now = self._clock()
        assignment = await microtask_assignment_crud.get_for_candidate(
            self._session, assignment_id, profile.id, for_update=True
        )
        if assignment is None:
            raise NotFoundError("Задача не найдена")
        if assignment.status is not AssignmentStatus.ASSIGNED:
            raise ConflictError("Ответ на эту задачу уже отправлен или срок истёк")
        if assignment.due_at < now:
            await microtask_assignment_crud.update(
                self._session, assignment, {"status": AssignmentStatus.EXPIRED}
            )
            await self._session.commit()
            raise ConflictError("Срок ответа на задачу истёк")
        task = await microtask_crud.get(self._session, assignment.task_id)
        assert task is not None
        cleaned = answer.strip()
        changes: dict[str, Any] = {"answer": cleaned, "submitted_at": now}
        if task.kind is MicroTaskKind.SOLVE:
            changes |= {
                "score": auto_grade(task.answer_key, cleaned),
                "status": AssignmentStatus.GRADED,
                "graded_at": now,
            }
        else:
            changes["status"] = AssignmentStatus.SUBMITTED
        await microtask_assignment_crud.update(self._session, assignment, changes)
        if task.kind is not MicroTaskKind.SOLVE:
            for recruiter_user_id in await recruiter_crud.user_ids_for_company(
                self._session, task.company_id
            ):
                await self._notifications.notify(
                    recruiter_user_id,
                    NotificationKind.MICROTASK_SUBMITTED,
                    title="Ответ на задачу ждёт оценки",
                    text=f"Кандидат {profile.public_alias} предложил подход к «{task.title}»",
                    link=f"/e/tasks/{task.id}",
                )
        await self._session.commit()
        companies = await company_lookup_crud.with_industry(self._session, [task.company_id])
        return assignment_read(assignment, task, companies[task.company_id].name)

    async def skip(self, user: User, assignment_id: uuid.UUID) -> AssignmentRead:
        """Пропуск задачи: на индекс не влияет, но расходует недельный лимит."""
        profile = await self._profiles.ensure_profile(user)
        assignment = await microtask_assignment_crud.get_for_candidate(
            self._session, assignment_id, profile.id, for_update=True
        )
        if assignment is None:
            raise NotFoundError("Задача не найдена")
        if assignment.status is not AssignmentStatus.ASSIGNED:
            raise ConflictError("Эту задачу уже нельзя пропустить")
        await microtask_assignment_crud.update(
            self._session, assignment, {"status": AssignmentStatus.SKIPPED}
        )
        await self._session.commit()
        task = await microtask_crud.get(self._session, assignment.task_id)
        assert task is not None
        companies = await company_lookup_crud.with_industry(self._session, [task.company_id])
        return assignment_read(assignment, task, companies[task.company_id].name)

    async def assign(
        self, candidate_id: uuid.UUID, task: MicroTask, *, assigned_at: datetime | None = None
    ) -> MicroTaskAssignment:
        """Выдаёт конкретную задачу кандидату. Транзакцию фиксирует вызывающий сценарий."""
        start = assigned_at or self._clock()
        return await microtask_assignment_crud.create(
            self._session,
            {
                "task_id": task.id,
                "candidate_id": candidate_id,
                "assigned_at": start,
                "due_at": start + timedelta(days=self._settings.microtask_due_days),
            },
        )

    def _due_for_offer(
        self, rows: Sequence[tuple[MicroTaskAssignment, MicroTask]], now: datetime
    ) -> bool:
        """Пора ли предложить задачу: нет активной и прошло больше интервала с прошлой."""
        if any(item.status is AssignmentStatus.ASSIGNED for item, _ in rows):
            return False
        if not rows:
            return True
        last = max(item.assigned_at for item, _ in rows)
        return now - last >= timedelta(days=self._settings.microtask_interval_days)

    async def _offer(
        self, candidate_id: uuid.UUID, specialization_id: int, seen: Sequence[uuid.UUID]
    ) -> MicroTaskAssignment | None:
        """Выдаёт случайную ещё не решённую задачу специализации."""
        tasks = list(await microtask_crud.offerable(self._session, specialization_id, seen))
        if not tasks:
            return None
        return await self.assign(candidate_id, self._rng.choice(tasks))

    async def _requests_left(self, candidate_id: uuid.UUID, now: datetime) -> int:
        """Сколько задач ещё можно получить на этой неделе."""
        used = await microtask_assignment_crud.count_since(
            self._session, candidate_id, now - timedelta(days=7)
        )
        return max(0, self._settings.microtask_weekly_limit - used)

    async def _specialization(self, candidate_id: uuid.UUID) -> int | None:
        """Специализация кандидата: из категории или, пока её нет, из опроса."""
        members = await self._pool.load(
            PoolQuery(candidate_ids=[candidate_id], published_only=False)
        )
        return members[0].facts.specialization_id if members else None

    async def _overview(
        self,
        candidate_id: uuid.UUID,
        rows: Sequence[tuple[MicroTaskAssignment, MicroTask]],
        specialization_id: int | None,
    ) -> TasksOverviewRead:
        """Сводка раздела задач."""
        now = self._clock()
        companies = await company_lookup_crud.with_industry(
            self._session, [task.company_id for _, task in rows]
        )
        reads = [
            assignment_read(assignment, task, companies[task.company_id].name)
            for assignment, task in rows
        ]
        current = next((item for item in reads if item.status is AssignmentStatus.ASSIGNED), None)
        graded = [
            GradedResult(score=item.score or 0.0, graded_at=item.graded_at)
            for item, _ in rows
            if item.status is AssignmentStatus.GRADED and item.graded_at is not None
        ]
        fresh = freshness(graded, now)
        left = await self._requests_left(candidate_id, now)
        available = specialization_id is not None
        has_new = specialization_id is not None and bool(
            await microtask_crud.offerable(
                self._session, specialization_id, [task.id for _, task in rows]
            )
        )
        last_assigned = max((item.assigned_at for item, _ in rows), default=None)
        next_offer = (
            last_assigned + timedelta(days=self._settings.microtask_interval_days)
            if last_assigned and current is None and has_new
            else None
        )
        return TasksOverviewRead(
            available=available,
            current=current,
            history=[item for item in reads if item is not current],
            freshness=FreshnessRead(
                value=fresh.value,
                vps_points=round(100 * VPS_WEIGHTS["micro_tasks"] * fresh.value, 1),
                count=fresh.count,
                last_graded_at=fresh.last.graded_at if fresh.last else None,
                half_life_days=int(HALF_LIFE_DAYS),
            ),
            can_request=has_new and current is None and left > 0,
            requests_left=left,
            next_offer_at=next_offer if next_offer and next_offer > now else None,
        )
