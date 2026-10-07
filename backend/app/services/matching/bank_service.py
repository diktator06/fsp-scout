import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.crud import (
    candidate_pool_crud,
    hiring_need_crud,
    invitation_crud,
    shortlist_crud,
    shortlist_entry_crud,
    user_crud,
)
from app.crud.candidate_search import PoolQuery
from app.models.user import User
from app.schemas.cards import InvitationBrief
from app.schemas.matching import (
    BankCandidateRead,
    BankFilters,
    BankPage,
    BankSort,
    CandidateCardRead,
    MatchRead,
)
from app.services.contact_access import ContactAccessPolicy
from app.services.employer.company_service import CompanyService
from app.services.matching.candidate_pool import CandidatePoolService, PoolMember
from app.services.matching.cards import build_card
from app.services.matching.engine import MatchingEngine
from app.services.matching.views import match_read, match_snapshot


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def _sort_key(sort: BankSort) -> Callable[[PoolMember], tuple[float, ...]]:
    """Ключ сортировки банка.

    По умолчанию подтверждённые тестом идут раньше заявленных (так просили менторы),
    внутри — по индексу подтверждённого профиля.
    """
    if sort is BankSort.RECENT:
        return lambda member: (-member.row.profile.updated_at.timestamp(),)
    if sort is BankSort.EXPERIENCE:
        return lambda member: (-(member.facts.experience_years or 0.0), -member.score.total)
    return lambda member: (0 if member.facts.confirmed else 1, -member.score.total)


class BankService:
    """Банк кандидатов: поиск по фильтрам и карточка кандидата."""

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени."""
        self._session = session
        self._companies = CompanyService(session, clock)
        self._pool = CandidatePoolService(session, clock)
        self._engine = MatchingEngine(session)
        self._contacts = ContactAccessPolicy(session)

    async def search(
        self, user: User, filters: BankFilters, *, limit: int, offset: int
    ) -> BankPage:
        """Кандидаты из банка по фильтрам. В банке только те, кто дал согласие на публикацию."""
        recruiter = await self._companies.require_recruiter(user)
        members = await self._pool.load(
            PoolQuery(
                specialization_ids=[filters.specialization_id] if filters.specialization_id else (),
                grade_ids=[filters.grade_id] if filters.grade_id else (),
                category_ids=[filters.category_id] if filters.category_id else (),
                skill_ids=filters.skill_ids,
                verified_skills_only=filters.verified_skills_only,
                confirmed_only=filters.confirmed_only,
                work_formats=[filters.work_format.value] if filters.work_format else (),
                city=filters.city,
                fsp_only=filters.has_fsp,
            )
        )
        members.sort(key=_sort_key(filters.sort))
        page = members[offset : offset + limit]
        ids = [member.candidate_id for member in page]
        outcomes = await candidate_pool_crud.competency_outcomes(
            self._session, [member.session.id for member in page if member.session is not None]
        )
        disclosures = await self._contacts.disclosures(recruiter.company_id, ids)
        invitations = await invitation_crud.latest_by_candidate(
            self._session, recruiter.company_id, ids
        )
        confirmed = sum(1 for member in members if member.facts.confirmed)
        return BankPage(
            items=[
                BankCandidateRead(
                    card=build_card(
                        member, outcomes.get(member.session.id) if member.session else None
                    ),
                    contacts_disclosed=member.candidate_id in disclosures,
                    invitation=_brief(invitations.get(member.candidate_id)),
                )
                for member in page
            ],
            total=len(members),
            confirmed=confirmed,
            unconfirmed=len(members) - confirmed,
            limit=limit,
            offset=offset,
        )

    async def card(
        self, user: User, candidate_id: uuid.UUID, need_id: uuid.UUID | None = None
    ) -> CandidateCardRead:
        """Карточка кандидата. С потребностью — ещё и балл соответствия с объяснением.

        Карточку видно, пока кандидат в банке. Если он скрыл профиль, но уже раскрыл
        контакты компании или получил от неё приглашение, карточка остаётся доступной
        этой компании: переписка не должна обрываться.
        """
        recruiter = await self._companies.require_recruiter(user)
        members = await self._pool.load(PoolQuery(candidate_ids=[candidate_id]))
        disclosure = await self._contacts.disclosure(recruiter.company_id, candidate_id)
        invitation = (
            await invitation_crud.latest_by_candidate(
                self._session, recruiter.company_id, [candidate_id]
            )
        ).get(candidate_id)
        if not members and (disclosure is not None or invitation is not None):
            members = await self._pool.load(
                PoolQuery(candidate_ids=[candidate_id], published_only=False)
            )
        if not members:
            raise NotFoundError("Кандидат не найден или скрыл профиль")
        member = members[0]
        outcomes = await candidate_pool_crud.competency_outcomes(
            self._session, [member.session.id] if member.session else []
        )
        contacts = None
        if disclosure is not None:
            owner = await user_crud.get(self._session, member.row.profile.user_id)
            contacts = ContactAccessPolicy.contacts(
                disclosure, member.row.profile, owner.email if owner else "", member.privacy
            )
        match = await self._match(recruiter.company_id, member, need_id) if need_id else None
        return CandidateCardRead(
            card=build_card(member, outcomes.get(member.session.id) if member.session else None),
            contacts=contacts,
            match=match,
            invitation=_brief(invitation),
        )

    async def _match(
        self, company_id: uuid.UUID, member: PoolMember, need_id: uuid.UUID
    ) -> MatchRead:
        """Балл кандидата по потребности: из последней версии подборки или заново."""
        need = await hiring_need_crud.get_for_company(self._session, need_id, company_id)
        if need is None:
            raise NotFoundError("Потребность не найдена")
        catalog = await self._engine.catalog()
        latest = await shortlist_crud.latest_version(self._session, need.id)
        shortlist = (
            await shortlist_crud.get_version(self._session, need.id, latest) if latest else None
        )
        if shortlist is not None:
            entry = await shortlist_entry_crud.get(
                self._session, (shortlist.id, member.candidate_id)
            )
            if entry is not None:
                return match_read(
                    {**entry.breakdown, "explanation": entry.explanation.get("items", [])},
                    catalog.names,
                )
        context = await self._engine.context(need)
        scored = (await self._engine.score(context, [member]))[0]
        return match_read(match_snapshot(scored.result, scored.explanation), catalog.names)


def _brief(invitation: object) -> InvitationBrief | None:
    """Краткие сведения о приглашении для метки в выдаче."""
    if invitation is None:
        return None
    return InvitationBrief.model_validate(invitation, from_attributes=True)
