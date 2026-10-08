from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.rate_limit import client_ip
from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError
from app.db.session import get_session
from app.integrations.fsp_gateway import FspGateway, build_fsp_gateway
from app.integrations.mailer import Mailer, build_mailer
from app.models.user import User, UserRole
from app.services.account.personal_data_service import PersonalDataService
from app.services.assessment.assessment_service import AssessmentService
from app.services.assessment.methodist_service import MethodistService
from app.services.auth.access import ensure_role, resolve_user_by_access_token
from app.services.auth.auth_service import AuthService
from app.services.auth.tokens import ClientContext
from app.services.candidate.profile_service import CandidateProfileService
from app.services.candidate.resume_import import ResumeImportService
from app.services.dictionary_service import DictionaryService
from app.services.employer.company_service import CompanyService
from app.services.fsp.fsp_login import FspLoginService
from app.services.fsp.fsp_service import FspService
from app.services.integrations.integration_service import IntegrationService
from app.services.integrations.sandbox import SandboxReceiver
from app.services.invitations.invitation_service import InvitationService
from app.services.matching.bank_service import BankService
from app.services.matching.need_service import NeedService
from app.services.matching.shortlist_service import ShortlistService
from app.services.microtasks.candidate_service import CandidateTaskService
from app.services.microtasks.employer_service import EmployerTaskService
from app.services.notifications import NotificationService
from app.services.trust.complaint_service import ComplaintService
from app.services.trust.moderation_service import ModerationService
from app.services.vacancies.board_service import VacancyBoardService
from app.services.vacancies.vacancy_service import VacancyService

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


@lru_cache
def get_fsp_gateway() -> FspGateway:
    """Шлюз ФСП, один на процесс: в нём кешируются метаданные, ключи и сервисный токен.

    В тестах подменяется шлюзом с поддельным транспортом HTTP.
    """
    return build_fsp_gateway(get_settings())


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
FspGatewayDep = Annotated[FspGateway, Depends(get_fsp_gateway)]


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


def get_resume_import_service(session: SessionDep) -> ResumeImportService:
    """Сервис автораспознавания резюме на время запроса."""
    return ResumeImportService(session)


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


def get_fsp_service(
    session: SessionDep, settings: SettingsDep, gateway: FspGatewayDep
) -> FspService:
    """Сервис ФСП кандидата на время запроса."""
    return FspService(session, settings, gateway)


def get_fsp_login_service(
    session: SessionDep, settings: SettingsDep, gateway: FspGatewayDep
) -> FspLoginService:
    """Сервис входа через ФСП ID на время запроса."""
    return FspLoginService(session, settings, gateway)


def get_vacancy_service(session: SessionDep) -> VacancyService:
    """Сервис вакансий работодателя на время запроса."""
    return VacancyService(session)


def get_integration_service(session: SessionDep, settings: SettingsDep) -> IntegrationService:
    """Сервис интеграции с ATS на время запроса."""
    return IntegrationService(session, settings)


def get_sandbox_receiver(session: SessionDep, settings: SettingsDep) -> SandboxReceiver:
    """Песочница ATS на время запроса."""
    return SandboxReceiver(session, settings)


def get_vacancy_board_service(session: SessionDep, settings: SettingsDep) -> VacancyBoardService:
    """Сервис вакансий для кандидата на время запроса."""
    return VacancyBoardService(session, settings)


def get_candidate_task_service(session: SessionDep, settings: SettingsDep) -> CandidateTaskService:
    """Сервис микрозадач кандидата на время запроса."""
    return CandidateTaskService(session, settings)


def get_employer_task_service(session: SessionDep) -> EmployerTaskService:
    """Сервис микрозадач работодателя на время запроса."""
    return EmployerTaskService(session)


def get_complaint_service(session: SessionDep) -> ComplaintService:
    """Сервис жалоб на время запроса."""
    return ComplaintService(session)


def get_moderation_service(session: SessionDep) -> ModerationService:
    """Сервис модерации на время запроса."""
    return ModerationService(session)


def get_personal_data_service(
    session: SessionDep, settings: SettingsDep, mailer: MailerDep
) -> PersonalDataService:
    """Сервис прав субъекта ПДн: выгрузка и удаление аккаунта."""
    return PersonalDataService(session, settings, mailer)


def get_methodist_service(session: SessionDep, settings: SettingsDep) -> MethodistService:
    """Сервис кабинета методиста."""
    return MethodistService(session, settings)


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
FspServiceDep = Annotated[FspService, Depends(get_fsp_service)]
VacancyServiceDep = Annotated[VacancyService, Depends(get_vacancy_service)]
ComplaintServiceDep = Annotated[ComplaintService, Depends(get_complaint_service)]
ModerationServiceDep = Annotated[ModerationService, Depends(get_moderation_service)]
MethodistServiceDep = Annotated[MethodistService, Depends(get_methodist_service)]
PersonalDataServiceDep = Annotated[PersonalDataService, Depends(get_personal_data_service)]
CandidateTaskServiceDep = Annotated[CandidateTaskService, Depends(get_candidate_task_service)]
EmployerTaskServiceDep = Annotated[EmployerTaskService, Depends(get_employer_task_service)]
VacancyBoardServiceDep = Annotated[VacancyBoardService, Depends(get_vacancy_board_service)]
IntegrationServiceDep = Annotated[IntegrationService, Depends(get_integration_service)]
SandboxReceiverDep = Annotated[SandboxReceiver, Depends(get_sandbox_receiver)]
FspLoginServiceDep = Annotated[FspLoginService, Depends(get_fsp_login_service)]
ProfileServiceDep = Annotated[CandidateProfileService, Depends(get_profile_service)]
ResumeImportServiceDep = Annotated[ResumeImportService, Depends(get_resume_import_service)]
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
