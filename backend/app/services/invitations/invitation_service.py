import logging
import uuid
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, InvitationQuotaExceededError, NotFoundError
from app.crud import (
    candidate_pool_crud,
    company_crud,
    hiring_need_crud,
    invitation_crud,
    invitation_event_crud,
    recruiter_crud,
    user_crud,
)
from app.crud.candidate_search import PoolQuery
from app.integrations.email_templates import render_email
from app.integrations.mailer import MailDeliveryError, Mailer, OutgoingEmail
from app.models.candidate import CandidateProfile
from app.models.employer import Recruiter
from app.models.invitation import (
    DisclosureReason,
    Invitation,
    InvitationEvent,
    InvitationStatus,
)
from app.models.notification import NotificationKind
from app.models.user import User
from app.schemas.cards import DisclosedContacts
from app.schemas.dictionary import CategoryRead
from app.schemas.invitation import (
    CandidateInvitationRead,
    DeclineRequest,
    EmployerInvitationRead,
    EventActor,
    InvitationCandidateRead,
    InvitationCreate,
    InvitationEventRead,
)
from app.services.candidate.profile_service import CandidateProfileService
from app.services.contact_access import ContactAccessPolicy
from app.services.employer.company_service import CompanyService
from app.services.employer.company_views import company_brief
from app.services.employer.company_views import employer_contacts as build_employer_contacts
from app.services.invitations.state_machine import Actor, ensure_transition
from app.services.matching.candidate_pool import CandidatePoolService, members_by_id
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)

WORK_FORMAT_NAMES = {"office": "офис", "hybrid": "гибрид", "remote": "удалённо"}


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def format_salary(salary_from: int, salary_to: int) -> str:
    """Вилка для писем и уведомлений: «250 000 – 320 000 ₽»."""

    def rub(amount: int) -> str:
        """Сумма с разделителем разрядов."""
        return f"{amount:,}".replace(",", " ")

    if salary_from == salary_to:
        return f"{rub(salary_from)} ₽"
    return f"{rub(salary_from)} – {rub(salary_to)} ₽"


class InvitationService:
    """Приглашения: отправка работодателем, ответ кандидата, отзыв и истечение срока.

    Статусы меняются только по автомату `state_machine`, каждый переход пишется в
    журнал. Принятие приглашения и раскрытие контактов происходят в одной транзакции.
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
        self._companies = CompanyService(session, clock)
        self._profiles = CandidateProfileService(session)
        self._contacts = ContactAccessPolicy(session)
        self._notifications = NotificationService(session, clock)
        self._pool = CandidatePoolService(session, clock)

    async def create(self, user: User, payload: InvitationCreate) -> EmployerInvitationRead:
        """Отправляет приглашение кандидату из банка.

        Проверки: кандидат виден в банке (или уже раскрыл контакты компании), у пары нет
        другого активного приглашения, дневная квота компании не исчерпана. Вилку
        проверила схема. Гонку двух одновременных отправок ловит частичный уникальный
        индекс в базе.
        """
        recruiter = await self._companies.require_recruiter(user)
        company_id = recruiter.company_id
        await self._expire_overdue(company_id=company_id)
        rows = await candidate_pool_crud.search(
            self._session, PoolQuery(candidate_ids=[payload.candidate_id])
        )
        disclosure = await self._contacts.disclosure(company_id, payload.candidate_id)
        if not rows and disclosure is None:
            raise NotFoundError("Кандидат не найден или скрыл профиль")
        if payload.need_id is not None and not await hiring_need_crud.get_for_company(
            self._session, payload.need_id, company_id
        ):
            raise NotFoundError("Потребность не найдена")
        active = await invitation_crud.active_for_pair(
            self._session, company_id, payload.candidate_id
        )
        if active is not None:
            raise ConflictError(
                "Кандидату уже отправлено приглашение — дождитесь ответа",
                details={"invitation_id": str(active.id)},
            )
        quota = await self._companies.quota(recruiter)
        if quota.remaining <= 0:
            raise InvitationQuotaExceededError(details={"daily_limit": quota.daily_limit})

        now = self._clock()
        invitation = await invitation_crud.create(
            self._session,
            {
                **payload.model_dump(exclude={"candidate_id"}),
                "candidate_id": payload.candidate_id,
                "company_id": company_id,
                "sender_user_id": user.id,
                "status": InvitationStatus.SENT,
                "expires_at": now + timedelta(days=self._settings.invitation_ttl_days),
            },
        )
        await self._record(invitation, None, InvitationStatus.SENT, user.id)
        candidate_user_id = await self._candidate_user_id(invitation.candidate_id)
        salary = format_salary(invitation.salary_from, invitation.salary_to)
        await self._notifications.notify(
            candidate_user_id,
            NotificationKind.INVITATION_RECEIVED,
            title=f"Приглашение от компании «{recruiter.company.name}»",
            text=f"{invitation.title} · {salary}",
            link=f"/c/invitations/{invitation.id}",
        )
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise ConflictError(
                "Кандидату уже отправлено приглашение — дождитесь ответа"
            ) from error
        await self._email_candidate(invitation, recruiter, candidate_user_id)
        return await self.get_for_company(user, invitation.id)

    async def list_for_company(
        self,
        user: User,
        *,
        statuses: Iterable[InvitationStatus] = (),
        need_id: uuid.UUID | None = None,
    ) -> list[EmployerInvitationRead]:
        """Приглашения компании со статусами и таймлайном."""
        recruiter = await self._companies.require_recruiter(user)
        if await self._expire_overdue(company_id=recruiter.company_id):
            await self._session.commit()
        invitations = await invitation_crud.list_for_company(
            self._session, recruiter.company_id, statuses=statuses, need_id=need_id
        )
        return await self._employer_views(recruiter, invitations)

    async def get_for_company(self, user: User, invitation_id: uuid.UUID) -> EmployerInvitationRead:
        """Приглашение компании."""
        recruiter = await self._companies.require_recruiter(user)
        if await self._expire_overdue(company_id=recruiter.company_id):
            await self._session.commit()
        invitation = await invitation_crud.get_for_company(
            self._session, invitation_id, recruiter.company_id
        )
        if invitation is None:
            raise NotFoundError("Приглашение не найдено")
        return (await self._employer_views(recruiter, [invitation]))[0]

    async def withdraw(self, user: User, invitation_id: uuid.UUID) -> EmployerInvitationRead:
        """Отзывает приглашение, пока кандидат не ответил."""
        recruiter = await self._companies.require_recruiter(user)
        await self._expire_overdue(company_id=recruiter.company_id)
        invitation = await invitation_crud.get_for_company(
            self._session, invitation_id, recruiter.company_id, for_update=True
        )
        if invitation is None:
            raise NotFoundError("Приглашение не найдено")
        await self._move(invitation, InvitationStatus.WITHDRAWN, Actor.EMPLOYER, user.id)
        await self._notifications.notify(
            await self._candidate_user_id(invitation.candidate_id),
            NotificationKind.INVITATION_WITHDRAWN,
            title="Компания отозвала приглашение",
            text=invitation.title,
            link=f"/c/invitations/{invitation.id}",
        )
        await self._session.commit()
        return await self.get_for_company(user, invitation.id)

    async def list_for_candidate(self, user: User) -> list[CandidateInvitationRead]:
        """Входящие приглашения кандидата. Чужие недоступны по построению запроса."""
        profile = await self._profiles.ensure_profile(user)
        await self._expire_overdue(candidate_id=profile.id)
        await self._session.commit()
        invitations = await invitation_crud.list_for_candidate(self._session, profile.id)
        return await self._candidate_views(profile, invitations)

    async def get_for_candidate(
        self, user: User, invitation_id: uuid.UUID
    ) -> CandidateInvitationRead:
        """Приглашение кандидата. Первое открытие переводит его в «просмотрено»."""
        profile = await self._profiles.ensure_profile(user)
        await self._expire_overdue(candidate_id=profile.id)
        invitation = await self._owned_by_candidate(profile, invitation_id)
        if invitation.status is InvitationStatus.SENT:
            await self._move(invitation, InvitationStatus.VIEWED, Actor.CANDIDATE, user.id)
        await self._session.commit()
        return (await self._candidate_views(profile, [invitation]))[0]

    async def accept(self, user: User, invitation_id: uuid.UUID) -> CandidateInvitationRead:
        """Принимает приглашение и раскрывает контакты компании в той же транзакции."""
        profile = await self._profiles.ensure_profile(user)
        await self._expire_overdue(candidate_id=profile.id)
        invitation = await self._owned_by_candidate(profile, invitation_id)
        if invitation.status is InvitationStatus.SENT:
            await self._move(invitation, InvitationStatus.VIEWED, Actor.CANDIDATE, user.id)
        await self._move(invitation, InvitationStatus.ACCEPTED, Actor.CANDIDATE, user.id)
        await self._contacts.disclose(
            company_id=invitation.company_id,
            candidate_id=profile.id,
            reason=DisclosureReason.INVITATION_ACCEPTED,
            source_id=invitation.id,
            actor_user_id=user.id,
        )
        await self._notify_company(
            invitation,
            NotificationKind.INVITATION_ACCEPTED,
            title=f"Кандидат {profile.public_alias} принял приглашение",
            text=f"{invitation.title}. Контакты открыты.",
        )
        await self._session.commit()
        await self._email_company_accepted(invitation, profile)
        return (await self._candidate_views(profile, [invitation]))[0]

    async def decline(
        self, user: User, invitation_id: uuid.UUID, payload: DeclineRequest
    ) -> CandidateInvitationRead:
        """Отклоняет приглашение с причиной. Контакты при этом не раскрываются."""
        profile = await self._profiles.ensure_profile(user)
        await self._expire_overdue(candidate_id=profile.id)
        invitation = await self._owned_by_candidate(profile, invitation_id)
        if invitation.status is InvitationStatus.SENT:
            await self._move(invitation, InvitationStatus.VIEWED, Actor.CANDIDATE, user.id)
        await self._move(
            invitation,
            InvitationStatus.DECLINED,
            Actor.CANDIDATE,
            user.id,
            extra={"decline_reason": payload.reason, "decline_comment": payload.comment.strip()},
        )
        await self._notify_company(
            invitation,
            NotificationKind.INVITATION_DECLINED,
            title=f"Кандидат {profile.public_alias} отклонил приглашение",
            text=invitation.title,
        )
        await self._session.commit()
        return (await self._candidate_views(profile, [invitation]))[0]

    async def _owned_by_candidate(
        self, profile: CandidateProfile, invitation_id: uuid.UUID
    ) -> Invitation:
        """Приглашение кандидата, заблокированное для смены статуса, или 404."""
        invitation = await invitation_crud.get_for_candidate(
            self._session, invitation_id, profile.id, for_update=True
        )
        if invitation is None:
            raise NotFoundError("Приглашение не найдено")
        return invitation

    async def _move(
        self,
        invitation: Invitation,
        target: InvitationStatus,
        actor: Actor,
        actor_user_id: uuid.UUID | None,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Переводит приглашение в новый статус по автомату и пишет событие в журнал."""
        ensure_transition(invitation.status, target, actor)
        now = self._clock()
        changes: dict[str, Any] = {"status": target, **(extra or {})}
        if target is InvitationStatus.VIEWED:
            changes["viewed_at"] = now
        if target in (InvitationStatus.ACCEPTED, InvitationStatus.DECLINED):
            changes["responded_at"] = now
        previous = invitation.status
        await invitation_crud.update(self._session, invitation, changes)
        await self._record(invitation, previous, target, actor_user_id)

    async def _record(
        self,
        invitation: Invitation,
        previous: InvitationStatus | None,
        target: InvitationStatus,
        actor_user_id: uuid.UUID | None,
    ) -> None:
        """Событие таймлайна."""
        await invitation_event_crud.create(
            self._session,
            {
                "invitation_id": invitation.id,
                "from_status": previous,
                "to_status": target,
                "actor_user_id": actor_user_id,
                "created_at": self._clock(),
            },
        )

    async def _expire_overdue(
        self, *, candidate_id: uuid.UUID | None = None, company_id: uuid.UUID | None = None
    ) -> int:
        """Переводит просроченные приглашения в «истекло».

        Отдельный планировщик не нужен: статусы видны только через API, и каждый запрос
        к приглашениям сначала закрывает просроченные. Транзакцию фиксирует вызывающий.
        """
        overdue = await invitation_crud.overdue_for_update(
            self._session, self._clock(), candidate_id=candidate_id, company_id=company_id
        )
        for invitation in overdue:
            await self._move(invitation, InvitationStatus.EXPIRED, Actor.SYSTEM, None)
            await self._notify_company(
                invitation,
                NotificationKind.INVITATION_EXPIRED,
                title="Приглашение истекло без ответа",
                text=invitation.title,
            )
        return len(overdue)

    async def _candidate_user_id(self, candidate_id: uuid.UUID) -> uuid.UUID:
        """Пользователь, которому принадлежит профиль кандидата."""
        rows = await candidate_pool_crud.search(
            self._session, PoolQuery(candidate_ids=[candidate_id], published_only=False)
        )
        if not rows:
            raise NotFoundError("Кандидат не найден")
        return rows[0].profile.user_id

    async def _notify_company(
        self, invitation: Invitation, kind: NotificationKind, *, title: str, text: str
    ) -> None:
        """Уведомление отправителю, а если его аккаунта уже нет — всем рекрутерам компании."""
        recipients = (
            [invitation.sender_user_id]
            if invitation.sender_user_id
            else await recruiter_crud.user_ids_for_company(self._session, invitation.company_id)
        )
        for user_id in recipients:
            await self._notifications.notify(
                user_id, kind, title=title, text=text, link=f"/e/invitations/{invitation.id}"
            )

    async def _send(self, message: OutgoingEmail) -> None:
        """Отправляет письмо. Сбой почты не отменяет уже зафиксированное действие."""
        try:
            await self._mailer.send(message)
        except MailDeliveryError:
            logger.warning("Не удалось отправить письмо «%s»", message.subject)

    async def _email_candidate(
        self, invitation: Invitation, recruiter: Recruiter, user_id: uuid.UUID
    ) -> None:
        """Письмо кандидату о новом приглашении."""
        user = await user_crud.get(self._session, user_id)
        if user is None:
            return
        text_body, html_body = render_email(
            "invitation_received",
            company_name=recruiter.company.name,
            title=invitation.title,
            salary=format_salary(invitation.salary_from, invitation.salary_to),
            salary_basis="до вычета НДФЛ" if invitation.salary_gross else "на руки",
            work_format=WORK_FORMAT_NAMES.get(invitation.work_format.value, ""),
            link=f"{self._settings.frontend_url}/c/invitations/{invitation.id}",
            expires_at=invitation.expires_at.strftime("%d.%m.%Y"),
        )
        await self._send(
            OutgoingEmail(
                to=user.email,
                subject=f"Приглашение от компании «{recruiter.company.name}»",
                text_body=text_body,
                html_body=html_body,
            )
        )

    async def _email_company_accepted(
        self, invitation: Invitation, profile: CandidateProfile
    ) -> None:
        """Письмо отправителю о принятом приглашении."""
        if invitation.sender_user_id is None:
            return
        user = await user_crud.get(self._session, invitation.sender_user_id)
        if user is None:
            return
        text_body, html_body = render_email(
            "invitation_accepted",
            alias=profile.public_alias,
            title=invitation.title,
            link=f"{self._settings.frontend_url}/e/invitations/{invitation.id}",
        )
        await self._send(
            OutgoingEmail(
                to=user.email,
                subject=f"Кандидат {profile.public_alias} принял приглашение",
                text_body=text_body,
                html_body=html_body,
            )
        )

    @staticmethod
    def _events(
        events: Sequence[InvitationEvent], candidate_user_id: uuid.UUID | None
    ) -> list[InvitationEventRead]:
        """Журнал переходов в виде таймлайна с указанием, кто действовал."""
        result = []
        for event in events:
            actor: EventActor
            if event.actor_user_id is None:
                actor = "system"
            elif event.actor_user_id == candidate_user_id:
                actor = "candidate"
            else:
                actor = "employer"
            result.append(
                InvitationEventRead(status=event.to_status, at=event.created_at, actor=actor)
            )
        return result

    async def _employer_views(
        self, recruiter: Recruiter, invitations: Sequence[Invitation]
    ) -> list[EmployerInvitationRead]:
        """Приглашения для работодателя: кандидат обезличен, пока не раскрыл контакты."""
        if not invitations:
            return []
        ids = [invitation.candidate_id for invitation in invitations]
        members = members_by_id(
            await self._pool.load(PoolQuery(candidate_ids=ids, published_only=False))
        )
        disclosures = await self._contacts.disclosures(recruiter.company_id, ids)
        events = await invitation_event_crud.list_for_invitations(
            self._session, [invitation.id for invitation in invitations]
        )
        need_titles: dict[uuid.UUID, str] = {}
        for need_id in {invitation.need_id for invitation in invitations if invitation.need_id}:
            need = await hiring_need_crud.get_for_company(
                self._session, need_id, recruiter.company_id
            )
            if need is not None:
                need_titles[need_id] = need.title
        result = []
        for invitation in invitations:
            member = members.get(invitation.candidate_id)
            contacts: DisclosedContacts | None = None
            if member is not None and invitation.candidate_id in disclosures:
                owner = await user_crud.get(self._session, member.row.profile.user_id)
                contacts = ContactAccessPolicy.contacts(
                    disclosures[invitation.candidate_id],
                    member.row.profile,
                    owner.email if owner else "",
                    member.privacy,
                )
            candidate_user_id = member.row.profile.user_id if member else None
            result.append(
                EmployerInvitationRead(
                    **self._base_fields(invitation),
                    events=self._events(events.get(invitation.id, []), candidate_user_id),
                    need_id=invitation.need_id,
                    need_title=need_titles.get(invitation.need_id) if invitation.need_id else None,
                    candidate=InvitationCandidateRead(
                        candidate_id=invitation.candidate_id,
                        alias=member.facts.alias if member else "—",
                        category=CategoryRead.model_validate(member.category) if member else None,
                        grade_status="confirmed"
                        if member and member.facts.confirmed
                        else "unconfirmed",
                        contacts=contacts,
                    ),
                )
            )
        return result

    async def _candidate_views(
        self, profile: CandidateProfile, invitations: Sequence[Invitation]
    ) -> list[CandidateInvitationRead]:
        """Приглашения для кандидата: компания и вилка видны сразу, контакты — после принятия."""
        if not invitations:
            return []
        events = await invitation_event_crud.list_for_invitations(
            self._session, [invitation.id for invitation in invitations]
        )
        companies = {}
        for company_id in {invitation.company_id for invitation in invitations}:
            company = await company_crud.get_with_industry(self._session, company_id)
            if company is not None:
                companies[company_id] = company
        recruiters: dict[uuid.UUID, Recruiter] = {}
        for sender_id in {
            invitation.sender_user_id for invitation in invitations if invitation.sender_user_id
        }:
            recruiter = await recruiter_crud.get_by_user_id(self._session, sender_id)
            if recruiter is not None:
                recruiters[sender_id] = recruiter
        result = []
        for invitation in invitations:
            company = companies[invitation.company_id]
            recruiter = (
                recruiters.get(invitation.sender_user_id) if invitation.sender_user_id else None
            )
            employer_contacts = None
            if invitation.status is InvitationStatus.ACCEPTED:
                employer_contacts = build_employer_contacts(company, recruiter)
            result.append(
                CandidateInvitationRead(
                    **self._base_fields(invitation),
                    events=self._events(events.get(invitation.id, []), profile.user_id),
                    company=company_brief(company),
                    recruiter_name=recruiter.full_name if recruiter else None,
                    employer_contacts=employer_contacts,
                )
            )
        return result

    @staticmethod
    def _base_fields(invitation: Invitation) -> dict[str, Any]:
        """Общие поля приглашения для обеих сторон."""
        return {
            "id": invitation.id,
            "status": invitation.status,
            "title": invitation.title,
            "offer_description": invitation.offer_description,
            "salary_from": invitation.salary_from,
            "salary_to": invitation.salary_to,
            "salary_gross": invitation.salary_gross,
            "work_format": invitation.work_format,
            "contact_method": invitation.contact_method,
            "decline_reason": invitation.decline_reason,
            "decline_comment": invitation.decline_comment,
            "created_at": invitation.created_at,
            "viewed_at": invitation.viewed_at,
            "responded_at": invitation.responded_at,
            "expires_at": invitation.expires_at,
        }
