from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import user_crud
from app.crud.candidate_search import PoolQuery
from app.models.invitation import ContactDisclosure
from app.schemas.integration import AtsCandidate
from app.services.contact_access import ContactAccessPolicy
from app.services.matching.candidate_pool import CandidatePoolService, members_by_id


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class CandidateSnapshotBuilder:
    """Кандидат в формате для ATS — одинаково в вебхуке и в экспорте.

    Строится только по раскрытию контактов: что кандидат не открыл компании (канал
    связи, скрытый город), в ATS не попадает. Остальное — то же, что работодатель
    видит в карточке: категория, подтверждённость грейда, индекс и навыки.
    """

    def __init__(
        self, session: AsyncSession, frontend_url: str, clock: Callable[[], datetime] = _now
    ) -> None:
        """Получает сессию БД, адрес фронтенда для ссылки на карточку и источник времени."""
        self._session = session
        self._frontend_url = frontend_url.rstrip("/")
        self._pool = CandidatePoolService(session, clock)

    async def build(self, disclosures: Sequence[ContactDisclosure]) -> list[AtsCandidate]:
        """Кандидаты по раскрытиям в том же порядке; без категории кандидат пропускается."""
        if not disclosures:
            return []
        ids = [item.candidate_id for item in disclosures]
        members = members_by_id(
            await self._pool.load(PoolQuery(candidate_ids=ids, published_only=False))
        )
        emails = await user_crud.emails_by_ids(
            self._session, [member.row.profile.user_id for member in members.values()]
        )
        result: list[AtsCandidate] = []
        for disclosure in disclosures:
            member = members.get(disclosure.candidate_id)
            if member is None:
                continue
            profile = member.row.profile
            contacts = ContactAccessPolicy.contacts(
                disclosure, profile, emails.get(profile.user_id, ""), member.privacy
            )
            assert contacts is not None
            facts = member.facts
            result.append(
                AtsCandidate(
                    candidate_id=profile.id,
                    alias=facts.alias,
                    full_name=contacts.full_name,
                    email=contacts.email,
                    phone=contacts.phone,
                    telegram=contacts.telegram,
                    city=facts.city if facts.city_visible else None,
                    specialization=member.category.specialization.name,
                    grade=member.category.grade.name,
                    category=member.category.title,
                    grade_confirmed=facts.confirmed,
                    verified_score=member.score.total,
                    experience_years=facts.experience_years,
                    skills=[skill.name for _, skill in member.skills],
                    profile_url=f"{self._frontend_url}/e/candidates/{profile.id}",
                    source=disclosure.reason,
                    source_id=disclosure.source_id,
                    disclosed_at=disclosure.disclosed_at,
                )
            )
        return result

    async def one(self, disclosure: ContactDisclosure | None) -> AtsCandidate | None:
        """Один кандидат — для события вебхука."""
        if disclosure is None:
            return None
        built = await self.build([disclosure])
        return built[0] if built else None
