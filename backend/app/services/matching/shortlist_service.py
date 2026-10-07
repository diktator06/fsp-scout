import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.crud import (
    candidate_pool_crud,
    candidate_profile_crud,
    hiring_need_crud,
    invitation_crud,
    shortlist_crud,
    shortlist_entry_crud,
    shortlist_mark_crud,
    user_crud,
)
from app.crud.candidate_search import PoolQuery
from app.models.employer import Recruiter
from app.models.matching import HiringNeed, Shortlist, ShortlistMarkKind
from app.models.user import User
from app.schemas.cards import InvitationBrief
from app.schemas.matching import (
    MarkUpdate,
    ShortlistEntryRead,
    ShortlistFilters,
    ShortlistRead,
    ShortlistStats,
)
from app.services.contact_access import ContactAccessPolicy
from app.services.employer.company_service import CompanyService
from app.services.matching.candidate_pool import CandidatePoolService, members_by_id
from app.services.matching.cards import build_card
from app.services.matching.engine import MatchingEngine, ScoredMember
from app.services.matching.match_scoring import MATCH_ALGORITHM_VERSION
from app.services.matching.views import match_read, match_snapshot


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def passes_filters(filters: ShortlistFilters, item: ScoredMember) -> bool:
    """Проходит ли кандидат уточняющие фильтры подборки."""
    facts = item.member.facts
    if filters.confirmed_only and not facts.confirmed:
        return False
    for skill_id in filters.verified_skill_ids:
        skill = facts.skills.get(skill_id)
        if skill is None or not skill.verified:
            return False
    if any(skill_id not in facts.skills for skill_id in filters.required_skill_ids):
        return False
    if (
        filters.work_formats
        and not {fmt.value for fmt in filters.work_formats} & facts.work_formats
    ):
        return False
    if filters.city and not (
        facts.city_visible
        and facts.city
        and facts.city.strip().lower() == filters.city.strip().lower()
    ):
        return False
    if filters.within_budget:
        salary = next(check for check in item.result.conditions if check.key == "salary")
        if salary.status != "ok":
            return False
    return item.result.score >= filters.min_score


class ShortlistService:
    """Подборка по потребности: версии, уточнения и отметки «закреплён / скрыт».

    Уточнение фильтров создаёт новую версию, старые остаются. Закреплённые кандидаты
    переносятся в каждую новую версию, даже если не проходят новые фильтры: ТЗ требует
    уточнять выдачу без потери уже найденного.
    """

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени."""
        self._session = session
        self._clock = clock
        self._companies = CompanyService(session, clock)
        self._engine = MatchingEngine(session)
        self._pool = CandidatePoolService(session, clock)
        self._contacts = ContactAccessPolicy(session)

    async def build(
        self, user: User, need_id: uuid.UUID, filters: ShortlistFilters
    ) -> ShortlistRead:
        """Строит новую версию подборки.

        Порядок: жёсткие фильтры (специализация, грейды, согласие на публикацию, статус
        поиска) → балл соответствия → уточняющие фильтры → закреплённые сверху.
        Строка потребности блокируется, чтобы номера версий не совпали при двух
        одновременных уточнениях.
        """
        recruiter, need = await self._owned(user, need_id, for_update=True)
        context = await self._engine.context(need)
        grade_ids = await self._engine.allowed_grade_ids(need, expand=filters.expand_grades)
        members = await self._pool.load(
            PoolQuery(specialization_ids=[need.specialization_id], grade_ids=grade_ids)
        )
        scored = await self._engine.score(context, members)
        marks = await shortlist_mark_crud.list_for_need(self._session, need.id)
        pinned_ids = {
            candidate_id
            for candidate_id, mark in marks.items()
            if mark.mark is ShortlistMarkKind.PINNED
        }
        passed: list[ScoredMember] = []
        pinned_outside: list[ScoredMember] = []
        for item in scored:
            mark = marks.get(item.member.candidate_id)
            if mark is not None and mark.mark is ShortlistMarkKind.HIDDEN:
                continue
            if passes_filters(filters, item):
                passed.append(item)
            elif item.member.candidate_id in pinned_ids:
                pinned_outside.append(item)
        pinned = [item for item in passed if item.member.candidate_id in pinned_ids]
        rest = [item for item in passed if item.member.candidate_id not in pinned_ids]
        ordered = pinned + pinned_outside + rest[: filters.limit]
        outside = {item.member.candidate_id for item in pinned_outside}

        shortlist = await shortlist_crud.create(
            self._session,
            {
                "need_id": need.id,
                "version": await shortlist_crud.latest_version(self._session, need.id) + 1,
                "filters": filters.model_dump(mode="json"),
                "stats": {
                    "pool": len(members),
                    "after_filters": len(passed),
                    "shown": len(ordered),
                },
                "algorithm_version": MATCH_ALGORITHM_VERSION,
                "created_by": user.id,
            },
        )
        entries = []
        for rank, item in enumerate(ordered, start=1):
            snapshot = match_snapshot(item.result, item.explanation)
            explanation = snapshot.pop("explanation")
            entries.append(
                {
                    "candidate_id": item.member.candidate_id,
                    "rank": rank,
                    "match_score": item.result.score,
                    "breakdown": snapshot,
                    "explanation": {"items": explanation},
                    "outside_filters": item.member.candidate_id in outside,
                }
            )
        await shortlist_entry_crud.create_many(self._session, shortlist.id, entries)
        await self._session.commit()
        return await self._view(recruiter, need, shortlist)

    async def get(
        self, user: User, need_id: uuid.UUID, version: int | None = None
    ) -> ShortlistRead:
        """Версия подборки; без номера — последняя. Первая версия строится при первом открытии."""
        recruiter, need = await self._owned(user, need_id)
        latest = await shortlist_crud.latest_version(self._session, need.id)
        if latest == 0:
            return await self.build(user, need_id, ShortlistFilters())
        shortlist = await shortlist_crud.get_version(self._session, need.id, version or latest)
        if shortlist is None:
            raise NotFoundError("Такой версии подборки нет")
        return await self._view(recruiter, need, shortlist)

    async def set_mark(
        self, user: User, need_id: uuid.UUID, candidate_id: uuid.UUID, payload: MarkUpdate
    ) -> None:
        """Закрепляет или скрывает кандидата в потребности."""
        _, need = await self._owned(user, need_id)
        if await candidate_profile_crud.get(self._session, candidate_id) is None:
            raise NotFoundError("Кандидат не найден")
        await shortlist_mark_crud.upsert(
            self._session,
            need_id=need.id,
            candidate_id=candidate_id,
            mark=payload.mark,
            note=payload.note.strip(),
        )
        await self._session.commit()

    async def remove_mark(self, user: User, need_id: uuid.UUID, candidate_id: uuid.UUID) -> None:
        """Снимает отметку."""
        _, need = await self._owned(user, need_id)
        await shortlist_mark_crud.remove(self._session, need.id, candidate_id)
        await self._session.commit()

    async def _owned(
        self, user: User, need_id: uuid.UUID, *, for_update: bool = False
    ) -> tuple[Recruiter, HiringNeed]:
        """Рекрутер и потребность его компании или 404."""
        recruiter = await self._companies.require_recruiter(user)
        need = await hiring_need_crud.get_for_company(
            self._session, need_id, recruiter.company_id, for_update=for_update
        )
        if need is None:
            raise NotFoundError("Потребность не найдена")
        return recruiter, need

    async def _view(
        self, recruiter: Recruiter, need: HiringNeed, shortlist: Shortlist
    ) -> ShortlistRead:
        """Версия подборки для ответа API.

        Балл и объяснение берутся из снимка версии, а карточка — актуальная. Кандидат,
        который с тех пор скрыл профиль или отозвал согласие, из выдачи пропадает.
        """
        entries = await shortlist_entry_crud.list_for_shortlist(self._session, shortlist.id)
        ids = [entry.candidate_id for entry in entries]
        members = members_by_id(await self._pool.load(PoolQuery(candidate_ids=ids)))
        outcomes = await candidate_pool_crud.competency_outcomes(
            self._session,
            [member.session.id for member in members.values() if member.session is not None],
        )
        marks = await shortlist_mark_crud.list_for_need(self._session, need.id)
        disclosures = await self._contacts.disclosures(recruiter.company_id, ids)
        invitations = await invitation_crud.latest_by_candidate(
            self._session, recruiter.company_id, ids
        )
        catalog = await self._engine.catalog()
        versions = [
            item.version for item in await shortlist_crud.list_for_need(self._session, need.id)
        ]
        result = []
        for entry in entries:
            member = members.get(entry.candidate_id)
            if member is None:
                continue
            mark = marks.get(entry.candidate_id)
            contacts = None
            if entry.candidate_id in disclosures:
                owner = await user_crud.get(self._session, member.row.profile.user_id)
                contacts = ContactAccessPolicy.contacts(
                    disclosures[entry.candidate_id],
                    member.row.profile,
                    owner.email if owner else "",
                    member.privacy,
                )
            invitation = invitations.get(entry.candidate_id)
            result.append(
                ShortlistEntryRead(
                    rank=entry.rank,
                    card=build_card(
                        member, outcomes.get(member.session.id) if member.session else None
                    ),
                    match=match_read(
                        {**entry.breakdown, "explanation": entry.explanation.get("items", [])},
                        catalog.names,
                    ),
                    mark=mark.mark if mark else None,
                    note=mark.note if mark else "",
                    outside_filters=entry.outside_filters,
                    contacts=contacts,
                    invitation=InvitationBrief(
                        id=invitation.id, status=invitation.status, created_at=invitation.created_at
                    )
                    if invitation
                    else None,
                )
            )
        return ShortlistRead(
            version=shortlist.version,
            versions=versions,
            created_at=shortlist.created_at,
            algorithm_version=shortlist.algorithm_version,
            filters=ShortlistFilters.model_validate(shortlist.filters),
            stats=ShortlistStats.model_validate(shortlist.stats),
            entries=result,
        )
