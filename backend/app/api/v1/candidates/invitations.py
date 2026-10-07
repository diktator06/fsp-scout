import uuid

from fastapi import APIRouter

from app.api.deps import CandidateUser, InvitationServiceDep
from app.api.errors import error_responses
from app.schemas.invitation import CandidateInvitationRead, DeclineRequest

router = APIRouter(prefix="/candidates/me/invitations", tags=["candidate: invitations"])

_errors = error_responses(401, 403, 404, 409, 422)


@router.get(
    "", response_model=list[CandidateInvitationRead], responses=_errors, summary="Мои приглашения"
)
async def list_invitations(
    user: CandidateUser, service: InvitationServiceDep
) -> list[CandidateInvitationRead]:
    """Входящие приглашения: компания и вилка видны сразу."""
    return await service.list_for_candidate(user)


@router.get(
    "/{invitation_id}",
    response_model=CandidateInvitationRead,
    responses=_errors,
    summary="Приглашение (отмечается просмотренным)",
)
async def read_invitation(
    invitation_id: uuid.UUID, user: CandidateUser, service: InvitationServiceDep
) -> CandidateInvitationRead:
    """Первое открытие переводит приглашение в «просмотрено» — это видит работодатель."""
    return await service.get_for_candidate(user, invitation_id)


@router.post(
    "/{invitation_id}/accept",
    response_model=CandidateInvitationRead,
    responses=_errors,
    summary="Принять приглашение",
)
async def accept_invitation(
    invitation_id: uuid.UUID, user: CandidateUser, service: InvitationServiceDep
) -> CandidateInvitationRead:
    """Принимает приглашение: компании открываются разрешённые контакты, кандидату — её."""
    return await service.accept(user, invitation_id)


@router.post(
    "/{invitation_id}/decline",
    response_model=CandidateInvitationRead,
    responses=_errors,
    summary="Отклонить приглашение",
)
async def decline_invitation(
    invitation_id: uuid.UUID,
    payload: DeclineRequest,
    user: CandidateUser,
    service: InvitationServiceDep,
) -> CandidateInvitationRead:
    """Отклоняет приглашение с причиной. Контакты не раскрываются."""
    return await service.decline(user, invitation_id, payload)
