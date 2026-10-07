from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.rate_limit import client_ip
from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError
from app.db.session import get_session
from app.integrations.mailer import Mailer, build_mailer
from app.models.user import User, UserRole
from app.services.assessment.assessment_service import AssessmentService
from app.services.auth.access import ensure_role, resolve_user_by_access_token
from app.services.auth.auth_service import AuthService
from app.services.auth.tokens import ClientContext
from app.services.candidate.profile_service import CandidateProfileService
from app.services.dictionary_service import DictionaryService
from app.services.employer.company_service import CompanyService
from app.services.invitations.invitation_service import InvitationService
from app.services.matching.bank_service import BankService
from app.services.matching.need_service import NeedService
from app.services.matching.shortlist_service import ShortlistService
from app.services.notifications import NotificationService

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AccessToken",
    description="Access-токен из ответа `/auth/login`, `/auth/refresh` или `/auth/verify-email`",
)


def get_mailer(settings: SettingsDep) -> Mailer:
    """Способ отправки писем. В тестах подменяется заглушкой, которая складывает письма в список."""
    return build_mailer(settings)


def get_client_context(request: Request) -> ClientContext:
    """IP и User-Agent клиента для журнала сессий и согласий."""
    return ClientContext(
        ip_address=client_ip(request), user_agent=request.headers.get("user-agent")
    )


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> User:
    """Текущий пользователь по заголовку `Authorization: Bearer …`."""
    if credentials is None:
        raise AuthenticationError()
    return await resolve_user_by_access_token(session, credentials.credentials, settings)


CurrentUser = Annotated[User, Depends(get_current_user)]
ClientContextDep = Annotated[ClientContext, Depends(get_client_context)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]


def require_roles(*roles: UserRole) -> Callable[..., Awaitable[User]]:
    """Зависимость, пропускающая только пользователей с одной из перечисленных ролей."""
    allowed = frozenset(roles)

    async def dependency(user: CurrentUser) -> User:
        """Проверяет роль текущего пользователя."""
        return ensure_role(user, allowed)

    return dependency


MethodistUser = Annotated[User, Depends(require_roles(UserRole.METHODIST))]
CandidateUser = Annotated[User, Depends(require_roles(UserRole.CANDIDATE))]
EmployerUser = Annotated[User, Depends(require_roles(UserRole.EMPLOYER))]


def get_auth_service(session: SessionDep, settings: SettingsDep, mailer: MailerDep) -> AuthService:
    """Сервис сценариев аутентификации на время запроса."""
    return AuthService(session, settings, mailer)


def get_dictionary_service(session: SessionDep) -> DictionaryService:
    """Сервис изменения справочников на время запроса."""
    return DictionaryService(session)


def get_profile_service(session: SessionDep) -> CandidateProfileService:
    """Сервис профиля кандидата на время запроса."""
    return CandidateProfileService(session)


def get_assessment_service(session: SessionDep, settings: SettingsDep) -> AssessmentService:
    """Сервис опроса и тестирования на время запроса."""
    return AssessmentService(session, settings)


def get_company_service(session: SessionDep) -> CompanyService:
    """Сервис профиля компании на время запроса."""
    return CompanyService(session)


def get_need_service(session: SessionDep) -> NeedService:
    """Сервис потребностей работодателя на время запроса."""
    return NeedService(session)


def get_shortlist_service(session: SessionDep) -> ShortlistService:
    """Сервис подборок на время запроса."""
    return ShortlistService(session)


def get_bank_service(session: SessionDep) -> BankService:
    """Сервис банка кандидатов на время запроса."""
    return BankService(session)


def get_invitation_service(
    session: SessionDep, settings: SettingsDep, mailer: MailerDep
) -> InvitationService:
    """Сервис приглашений на время запроса."""
    return InvitationService(session, settings, mailer)


def get_notification_service(session: SessionDep) -> NotificationService:
    """Сервис уведомлений на время запроса."""
    return NotificationService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CompanyServiceDep = Annotated[CompanyService, Depends(get_company_service)]
NeedServiceDep = Annotated[NeedService, Depends(get_need_service)]
ShortlistServiceDep = Annotated[ShortlistService, Depends(get_shortlist_service)]
BankServiceDep = Annotated[BankService, Depends(get_bank_service)]
InvitationServiceDep = Annotated[InvitationService, Depends(get_invitation_service)]
NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
ProfileServiceDep = Annotated[CandidateProfileService, Depends(get_profile_service)]
AssessmentServiceDep = Annotated[AssessmentService, Depends(get_assessment_service)]
DictionaryServiceDep = Annotated[DictionaryService, Depends(get_dictionary_service)]


@dataclass(frozen=True, slots=True)
class Pagination:
    """Параметры постраничной выдачи."""

    limit: int
    offset: int


def get_pagination(
    limit: Annotated[int, Query(ge=1, le=100, description="Размер страницы")] = 20,
    offset: Annotated[int, Query(ge=0, description="Смещение от начала списка")] = 0,
) -> Pagination:
    """Разбирает параметры пагинации из query-строки."""
    return Pagination(limit=limit, offset=offset)


PaginationDep = Annotated[Pagination, Depends(get_pagination)]
