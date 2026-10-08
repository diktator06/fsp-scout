import enum
import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.config import Settings
from app.core.exceptions import DomainValidationError
from app.crud import audit_log_crud, personal_data_crud, recruiter_crud
from app.db.base import Base
from app.integrations.email_templates import render_email
from app.integrations.mailer import MailDeliveryError, Mailer, OutgoingEmail
from app.models.assessment import AssessmentItem, AssessmentSession, GradeHistory, SurveyResponse
from app.models.audit import AuditLog
from app.models.auth_session import RefreshSession
from app.models.candidate import (
    CandidateProfile,
    CandidateSkill,
    Education,
    PrivacySettings,
    WorkExperience,
)
from app.models.consent import Consent
from app.models.employer import Company, Recruiter
from app.models.fsp import FspAchievement, FspLink, FspSyncLog
from app.models.invitation import ContactDisclosure, Invitation, InvitationEvent
from app.models.microtask import MicroTaskAssignment
from app.models.notification import Notification
from app.models.trust import Complaint
from app.models.user import User, UserRole
from app.models.vacancy import Application, ApplicationEvent
from app.schemas.personal_data import AccountDeletionRequest, PersonalDataExport

logger = logging.getLogger(__name__)

OPERATOR = "«Скаут» — платформа подбора ИТ-специалистов (демонстрационный стенд)"
PURPOSES = [
    "Учётная запись и вход",
    "Профиль кандидата, опрос и тест для присвоения категории",
    "Подбор: показ обезличенной карточки работодателям при согласии на публикацию",
    "Приглашения, отклики и раскрытие контактов только с согласия кандидата",
    "Привязка ФСП ID и достижения — по отдельному согласию",
]
SECRET_COLUMNS = frozenset(
    {"password_hash", "token_hash", "answer_key", "instance_seed", "seed_salt", "secret"}
)


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def _plain(value: Any) -> Any:
    """Значение колонки в виде, пригодном для JSON."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    return value


def serialize(row: Base) -> dict[str, Any]:
    """Запись таблицы целиком, кроме секретов. Новая колонка попадёт в выгрузку сама."""
    mapper = inspect(type(row))
    return {
        column.key: _plain(getattr(row, column.key))
        for column in mapper.column_attrs
        if column.key not in SECRET_COLUMNS
    }


@dataclass(frozen=True, slots=True)
class Section:
    """Раздел выгрузки: таблица и колонка, по которой строки принадлежат человеку."""

    name: str
    model: type[Base]
    owner: InstrumentedAttribute[Any]
    key: str


USER_SECTIONS = (
    Section("account", User, User.id, "user"),
    Section("consents", Consent, Consent.user_id, "user"),
    Section("sessions", RefreshSession, RefreshSession.user_id, "user"),
    Section("notifications", Notification, Notification.user_id, "user"),
    Section("complaints", Complaint, Complaint.author_user_id, "user"),
    Section("actions", AuditLog, AuditLog.actor_user_id, "user"),
)
CANDIDATE_SECTIONS = (
    Section("skills", CandidateSkill, CandidateSkill.candidate_id, "candidate"),
    Section("work_experience", WorkExperience, WorkExperience.candidate_id, "candidate"),
    Section("education", Education, Education.candidate_id, "candidate"),
    Section("privacy_settings", PrivacySettings, PrivacySettings.candidate_id, "candidate"),
    Section("surveys", SurveyResponse, SurveyResponse.candidate_id, "candidate"),
    Section("assessment_sessions", AssessmentSession, AssessmentSession.candidate_id, "candidate"),
    Section("assessment_items", AssessmentItem, AssessmentItem.session_id, "session"),
    Section("grade_history", GradeHistory, GradeHistory.candidate_id, "candidate"),
    Section("fsp_link", FspLink, FspLink.candidate_id, "candidate"),
    Section("fsp_achievements", FspAchievement, FspAchievement.candidate_id, "candidate"),
    Section("fsp_sync_log", FspSyncLog, FspSyncLog.candidate_id, "candidate"),
    Section("invitations", Invitation, Invitation.candidate_id, "candidate"),
    Section("invitation_events", InvitationEvent, InvitationEvent.invitation_id, "invitation"),
    Section("contact_disclosures", ContactDisclosure, ContactDisclosure.candidate_id, "candidate"),
    Section("applications", Application, Application.candidate_id, "candidate"),
    Section("application_events", ApplicationEvent, ApplicationEvent.application_id, "application"),
    Section(
        "microtask_assignments", MicroTaskAssignment, MicroTaskAssignment.candidate_id, "candidate"
    ),
)
EMPLOYER_SECTIONS = (
    Section("recruiter", Recruiter, Recruiter.user_id, "user"),
    Section("company", Company, Company.id, "company"),
)


class PersonalDataService:
    """Права субъекта ПДн: выгрузка всех данных и удаление аккаунта с уничтожением данных.

    Удаление необратимо: профиль, тесты, приглашения, отклики, достижения ФСП и
    раскрытия контактов удаляются каскадом в БД, копии событий в журнале вебхуков
    ATS — отдельно. В аудите остаётся только факт удаления, роль и сколько записей
    было уничтожено — без самих данных.
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        mailer: Mailer,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        """Получает сессию БД, настройки, почту и источник времени."""
        self._session = session
        self._settings = settings
        self._mailer = mailer
        self._clock = clock

    async def export(self, user: User) -> PersonalDataExport:
        """Все записи о человеке по разделам."""
        sections = await self._collect(user)
        counters: dict[str, int] = {}
        profile = sections.get("profile")
        if profile:
            counters["shortlist_appearances"] = await personal_data_crud.shortlist_appearances(
                self._session, uuid.UUID(profile[0]["id"])
            )
        return PersonalDataExport(
            generated_at=self._clock(),
            operator=OPERATOR,
            purposes=PURPOSES,
            user_id=user.id,
            role=user.role,
            sections=sections,
            counters=counters,
        )

    async def delete_account(self, user: User, payload: AccountDeletionRequest) -> None:
        """Удаляет аккаунт и все связанные данные; подтверждение — email владельца.

        У работодателя вместе с последним рекрутером удаляется и компания: иначе её
        вакансии и приглашения остались бы без ответственного. Если в компании есть
        другие рекрутеры, она остаётся им.
        """
        if payload.confirm_email.strip().lower() != user.email:
            raise DomainValidationError(
                "Введите email этого аккаунта, чтобы подтвердить удаление",
                details={"field": "confirm_email"},
            )
        sections = await self._collect(user)
        removed = {name: len(rows) for name, rows in sections.items() if rows}
        consents = [
            {key: row[key] for key in ("consent_type", "granted_at", "revoked_at")}
            for row in sections.get("consents", [])
        ]
        company_removed = False
        profile = sections.get("profile")
        if profile:
            removed["ats_event_copies"] = await personal_data_crud.delete_webhook_copies(
                self._session, uuid.UUID(profile[0]["id"])
            )
            await personal_data_crud.delete_candidate_profile(self._session, user.id)
        if user.role is UserRole.EMPLOYER:
            company_removed = await self._remove_company_if_last(user)
        email = user.email
        user_id = user.id
        role = user.role
        await personal_data_crud.delete_user(self._session, user_id)
        await audit_log_crud.record(
            self._session,
            actor_user_id=None,
            action="account_deleted",
            entity_type="user",
            entity_id=user_id,
            meta={
                "role": role,
                "removed": removed,
                "company_removed": company_removed,
                "consents": consents,
            },
        )
        await self._session.commit()
        await self._notify(email)

    async def _collect(self, user: User) -> dict[str, list[dict[str, Any]]]:
        """Строки всех разделов, в которых есть данные этого человека."""
        owners: dict[str, list[uuid.UUID]] = {"user": [user.id]}
        result: dict[str, list[dict[str, Any]]] = {}
        await self._fill(result, USER_SECTIONS, owners)
        if user.role is UserRole.CANDIDATE:
            profiles = await personal_data_crud.rows(
                self._session, CandidateProfile, CandidateProfile.user_id, [user.id]
            )
            result["profile"] = [serialize(row) for row in profiles]
            owners["candidate"] = [row.id for row in profiles if isinstance(row, CandidateProfile)]
            await self._fill(result, CANDIDATE_SECTIONS, owners)
        if user.role is UserRole.EMPLOYER:
            recruiter = await recruiter_crud.get_by_user_id(self._session, user.id)
            owners["company"] = [recruiter.company_id] if recruiter else []
            await self._fill(result, EMPLOYER_SECTIONS, owners)
        return result

    async def _fill(
        self,
        result: dict[str, list[dict[str, Any]]],
        sections: Sequence[Section],
        owners: dict[str, list[uuid.UUID]],
    ) -> None:
        """Заполняет разделы по порядку: ключи сессий, приглашений и откликов берутся из уже
        загруженных разделов."""
        derived: Mapping[str, str] = {
            "session": "assessment_sessions",
            "invitation": "invitations",
            "application": "applications",
        }
        for section in sections:
            if section.key in derived:
                owners[section.key] = [
                    uuid.UUID(row["id"]) for row in result.get(derived[section.key], [])
                ]
            rows = await personal_data_crud.rows(
                self._session, section.model, section.owner, owners.get(section.key, [])
            )
            result[section.name] = [serialize(row) for row in rows]

    async def _remove_company_if_last(self, user: User) -> bool:
        """Удаляет компанию, если пользователь — её единственный рекрутер."""
        recruiter = await recruiter_crud.get_by_user_id(self._session, user.id)
        if recruiter is None:
            return False
        colleagues = await recruiter_crud.user_ids_for_company(self._session, recruiter.company_id)
        if any(colleague != user.id for colleague in colleagues):
            return False
        await personal_data_crud.delete_company(self._session, recruiter.company_id)
        return True

    async def _notify(self, email: str) -> None:
        """Письмо-подтверждение: данные удалены. Сбой почты удаление не отменяет."""
        text_body, html_body = render_email("account_deleted", email=email)
        try:
            await self._mailer.send(
                OutgoingEmail(
                    to=email,
                    subject="Аккаунт в «Скауте» удалён",
                    text_body=text_body,
                    html_body=html_body,
                )
            )
        except MailDeliveryError:
            logger.warning("Не удалось отправить письмо об удалении аккаунта")
