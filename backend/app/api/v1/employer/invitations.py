import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import EmployerUser, InvitationServiceDep
from app.api.errors import error_responses
from app.models.invitation import InvitationStatus
from app.schemas.invitation import EmployerInvitationRead, InvitationCreate

router = APIRouter(prefix="/employer/invitations", tags=["employer: invitations"])

_errors = error_responses(401, 403, 404, 409, 422, 429)


@router.post(
    "",
    response_model=EmployerInvitationRead,
    status_code=status.HTTP_201_CREATED,
    responses=_errors,
    summary="Пригласить кандидата",
)
async def create_invitation(
    payload: InvitationCreate, user: EmployerUser, service: InvitationServiceDep
) -> EmployerInvitationRead:
    """Приглашение с описанием, вилкой «от–до» и способом связи (все поля обязательны).

    Одно активное приглашение на пару «компания — кандидат», дневная квота по уровню
    доверия компании, срок ответа — 14 дней.
    """
    return await service.create(user, payload)


@router.get(
    "",
    response_model=list[EmployerInvitationRead],
    responses=_errors,
    summary="Приглашения компании",
)
async def list_invitations(
    user: EmployerUser,
    service: InvitationServiceDep,
    statuses: Annotated[list[InvitationStatus] | None, Query(alias="status")] = None,
    need_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[EmployerInvitationRead]:
    """Приглашения со статусами и таймлайном, с фильтром по статусу и потребности."""
    return await service.list_for_company(user, statuses=statuses or [], need_id=need_id)


@router.get(
    "/{invitation_id}",
    response_model=EmployerInvitationRead,
    responses=_errors,
    summary="Приглашение",
)
async def read_invitation(
    invitation_id: uuid.UUID, user: EmployerUser, service: InvitationServiceDep
) -> EmployerInvitationRead:
    """Приглашение компании. Чужое — 404."""
    return await service.get_for_company(user, invitation_id)


@router.post(
    "/{invitation_id}/withdraw",
    response_model=EmployerInvitationRead,
    responses=_errors,
    summary="Отозвать приглашение",
)
async def withdraw_invitation(
    invitation_id: uuid.UUID, user: EmployerUser, service: InvitationServiceDep
) -> EmployerInvitationRead:
    """Отзывает приглашение, пока кандидат не ответил."""
    return await service.withdraw(user, invitation_id)
