import uuid

from fastapi import APIRouter, status

from app.api.deps import EmployerTaskServiceDep, EmployerUser
from app.api.errors import error_responses
from app.schemas.microtask import GradeRequest, MicroTaskCreate, MicroTaskRead, SubmissionRead

router = APIRouter(prefix="/employer", tags=["employer: tasks"])

_errors = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/tasks", response_model=list[MicroTaskRead], responses=_errors, summary="Микрозадачи компании"
)
async def list_tasks(user: EmployerUser, service: EmployerTaskServiceDep) -> list[MicroTaskRead]:
    """Задачи с эталоном и статистикой ответов."""
    return await service.list_for_company(user)


@router.post(
    "/tasks",
    status_code=status.HTTP_201_CREATED,
    response_model=MicroTaskRead,
    responses=_errors,
    summary="Создать микрозадачу",
)
async def create_task(
    payload: MicroTaskCreate, user: EmployerUser, service: EmployerTaskServiceDep
) -> MicroTaskRead:
    """«Решить» — с эталоном для автопроверки, «предложить подход» — с рубрикой оценки."""
    return await service.create(user, payload)


@router.post(
    "/tasks/{task_id}/archive",
    response_model=MicroTaskRead,
    responses=_errors,
    summary="Убрать задачу из выдачи",
)
async def archive_task(
    task_id: uuid.UUID, user: EmployerUser, service: EmployerTaskServiceDep
) -> MicroTaskRead:
    """Уже выданные кандидаты дорешивают задачу."""
    return await service.archive(user, task_id)


@router.get(
    "/tasks/{task_id}/submissions",
    response_model=list[SubmissionRead],
    responses=_errors,
    summary="Ответы кандидатов",
)
async def task_submissions(
    task_id: uuid.UUID, user: EmployerUser, service: EmployerTaskServiceDep
) -> list[SubmissionRead]:
    """Ответы обезличены, как карточки в банке: автора можно пригласить по псевдониму."""
    return await service.submissions(user, task_id)


@router.post(
    "/task-submissions/{assignment_id}/grade",
    response_model=SubmissionRead,
    responses=_errors,
    summary="Оценить подход",
)
async def grade_submission(
    assignment_id: uuid.UUID,
    payload: GradeRequest,
    user: EmployerUser,
    service: EmployerTaskServiceDep,
) -> SubmissionRead:
    """Оценка 1–5 по рубрике; кандидат получает уведомление и балл в индекс."""
    return await service.grade(user, assignment_id, payload)
