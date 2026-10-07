from fastapi import APIRouter, Depends, status

from app.api.deps import CandidateUser, ComplaintServiceDep
from app.api.errors import error_responses
from app.api.rate_limit import RateLimiter
from app.schemas.trust import ComplaintCreate, ComplaintRead

router = APIRouter(prefix="/complaints", tags=["trust"])
complaint_limiter = RateLimiter(limit=20, window_seconds=3600)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ComplaintRead,
    responses=error_responses(401, 403, 404, 409, 422, 429),
    dependencies=[Depends(complaint_limiter)],
    summary="Пожаловаться на работодателя",
)
async def file_complaint(
    payload: ComplaintCreate, user: CandidateUser, service: ComplaintServiceDep
) -> ComplaintRead:
    """Жалоба на приглашение, вакансию или компанию.

    Три жалобы разных кандидатов за 30 дней автоматически ставят компанию на проверку:
    приглашения, вакансии и задачи приостанавливаются до решения модератора.
    """
    return await service.file(user, payload)
