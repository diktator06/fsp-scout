import uuid

from fastapi import APIRouter

from app.api.deps import CandidateTaskServiceDep, CandidateUser
from app.api.errors import error_responses
from app.schemas.microtask import AnswerSubmit, AssignmentRead, TasksOverviewRead

router = APIRouter(prefix="/candidates/me/tasks", tags=["candidate: tasks"])

_errors = error_responses(401, 403, 404, 409, 422)


@router.get("", response_model=TasksOverviewRead, responses=_errors, summary="Мои микрозадачи")
async def overview(user: CandidateUser, service: CandidateTaskServiceDep) -> TasksOverviewRead:
    """Текущая задача, история и фактор актуальности профиля.

    Если активной задачи нет и с прошлой прошла неделя, система предлагает новую
    задачу по специализации кандидата — это и есть «регулярные задания» из ТЗ.
    """
    return await service.overview(user)


@router.post(
    "/request", response_model=TasksOverviewRead, responses=_errors, summary="Попросить задачу"
)
async def request_task(user: CandidateUser, service: CandidateTaskServiceDep) -> TasksOverviewRead:
    """Задача раньше срока — в пределах недельного лимита."""
    return await service.request(user)


@router.post(
    "/{assignment_id}/submit",
    response_model=AssignmentRead,
    responses=_errors,
    summary="Ответить на задачу",
)
async def submit(
    assignment_id: uuid.UUID,
    payload: AnswerSubmit,
    user: CandidateUser,
    service: CandidateTaskServiceDep,
) -> AssignmentRead:
    """«Решить» проверяется сразу по эталону, «подход» оценивает работодатель."""
    return await service.submit(user, assignment_id, payload.answer)


@router.post(
    "/{assignment_id}/skip",
    response_model=AssignmentRead,
    responses=_errors,
    summary="Пропустить задачу",
)
async def skip(
    assignment_id: uuid.UUID, user: CandidateUser, service: CandidateTaskServiceDep
) -> AssignmentRead:
    """На индекс не влияет, но расходует недельный лимит."""
    return await service.skip(user, assignment_id)
