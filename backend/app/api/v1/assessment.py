import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import AssessmentServiceDep, CandidateUser
from app.api.errors import error_responses
from app.schemas.assessment import (
    AnswerSubmit,
    AssessmentHistoryRead,
    BlueprintRead,
    EligibilityRead,
    IntegrityEventCreate,
    SessionRead,
    SessionStart,
    SurveyCreate,
    SurveyRead,
)

router = APIRouter(prefix="/assessment", tags=["assessment"])

_errors = error_responses(401, 403, 404, 409, 422)


@router.post(
    "/surveys",
    status_code=status.HTTP_201_CREATED,
    response_model=SurveyRead,
    responses=_errors,
    summary="Пройти опрос",
)
async def submit_survey(
    payload: SurveyCreate, user: CandidateUser, service: AssessmentServiceDep
) -> SurveyRead:
    """Сохраняет опрос: специализацию, стек, опыт и заявленный грейд.

    Опрос задаёт состав теста (blueprint), но категорию не присваивает.
    """
    return await service.submit_survey(user, payload)


@router.get(
    "/surveys/latest",
    response_model=SurveyRead | None,
    responses=_errors,
    summary="Последний опрос",
)
async def latest_survey(user: CandidateUser, service: AssessmentServiceDep) -> SurveyRead | None:
    """Последний пройденный опрос или null."""
    return await service.latest_survey(user)


@router.get(
    "/blueprint",
    response_model=BlueprintRead,
    responses=_errors,
    summary="Состав теста для специализации и стека",
)
async def preview_blueprint(
    user: CandidateUser,
    service: AssessmentServiceDep,
    specialization_id: Annotated[int, Query(description="Специализация из справочника")],
    skill_ids: Annotated[list[int] | None, Query(description="Навыки из опроса")] = None,
) -> BlueprintRead:
    """Какие компетенции и с какими весами войдут в тест.

    Языково-зависимые компетенции включаются, только если в стеке есть
    соответствующий язык.
    """
    return await service.preview_blueprint(specialization_id, skill_ids or [])


@router.get(
    "/eligibility",
    response_model=EligibilityRead,
    responses=_errors,
    summary="Доступные тесты",
)
async def eligibility(user: CandidateUser, service: AssessmentServiceDep) -> EligibilityRead:
    """Для каждого грейда: можно ли сейчас пройти тест, а если нет — почему и когда."""
    return await service.eligibility(user)


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionRead,
    responses=_errors,
    summary="Начать тест на грейд",
)
async def start_session(
    payload: SessionStart, user: CandidateUser, service: AssessmentServiceDep
) -> SessionRead:
    """Начинает адаптивный тест на выбранный грейд и возвращает первое задание."""
    return await service.start_session(user, payload.target_grade_id)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionRead,
    responses=_errors,
    summary="Состояние теста",
)
async def read_session(
    session_id: uuid.UUID, user: CandidateUser, service: AssessmentServiceDep
) -> SessionRead:
    """Текущее задание или итог. Просроченное задание засчитывается как неотвеченное."""
    return await service.get_session(user, session_id)


@router.post(
    "/sessions/{session_id}/answers",
    response_model=SessionRead,
    responses=_errors,
    summary="Ответить на текущее задание",
)
async def submit_answer(
    session_id: uuid.UUID,
    payload: AnswerSubmit,
    user: CandidateUser,
    service: AssessmentServiceDep,
) -> SessionRead:
    """Принимает ответ и возвращает следующее задание или итог теста.

    Верно ли отвечено, до конца теста не сообщается.
    """
    return await service.submit_answer(user, session_id, payload.item_id, payload.answer)


@router.post(
    "/sessions/{session_id}/abandon",
    response_model=SessionRead,
    responses=_errors,
    summary="Прервать тест",
)
async def abandon_session(
    session_id: uuid.UUID, user: CandidateUser, service: AssessmentServiceDep
) -> SessionRead:
    """Прерывает тест. Попытка учитывается в дневном лимите."""
    return await service.abandon(user, session_id)


@router.post(
    "/sessions/{session_id}/integrity-events",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_errors,
    summary="Сигнал целостности",
)
async def integrity_event(
    session_id: uuid.UUID,
    payload: IntegrityEventCreate,
    user: CandidateUser,
    service: AssessmentServiceDep,
) -> Response:
    """Фиксирует уход со вкладки или вставку текста. Тест не прерывается."""
    await service.record_integrity_event(user, session_id, payload.event)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/{session_id}/accept-suggested-grade",
    response_model=SessionRead,
    responses=_errors,
    summary="Принять предложенный грейд",
)
async def accept_suggested_grade(
    session_id: uuid.UUID, user: CandidateUser, service: AssessmentServiceDep
) -> SessionRead:
    """Присваивает нижний грейд, который тест уверенно подтвердил, без пересдачи."""
    return await service.accept_suggested_grade(user, session_id)


@router.get(
    "/history",
    response_model=AssessmentHistoryRead,
    responses=_errors,
    summary="История тестов и грейдов",
)
async def history(user: CandidateUser, service: AssessmentServiceDep) -> AssessmentHistoryRead:
    """Все попытки тестов и смены категории."""
    return await service.history(user)
