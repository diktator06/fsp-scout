from collections.abc import Sequence

from app.crud.candidate_search import PoolQuery
from app.models.vacancy import Vacancy
from app.schemas.trust import SalaryCheckRead
from app.services.matching.candidate_pool import CandidatePoolService
from app.services.matching.match_scoring import to_gross
from app.services.trust.salary_check import check_salary


class MarketSalaryChecker:
    """Сверка вилок с открытыми ожиданиями кандидатов с кешем на время запроса."""

    def __init__(self, pool: CandidatePoolService) -> None:
        """Получает сервис пула кандидатов."""
        self._pool = pool
        self._cache: dict[tuple[int, tuple[int, ...]], list[float]] = {}

    async def expectations(self, specialization_id: int, grade_ids: Sequence[int]) -> list[float]:
        """Открытые ожидания кандидатов категории в базе «до вычета НДФЛ»."""
        key = (specialization_id, tuple(sorted(grade_ids)))
        if key not in self._cache:
            members = await self._pool.load(
                PoolQuery(specialization_ids=[specialization_id], grade_ids=list(grade_ids))
            )
            self._cache[key] = [
                to_gross(member.facts.salary_expectation, member.facts.salary_gross)
                for member in members
                if member.facts.salary_expectation is not None and member.facts.salary_visible
            ]
        return self._cache[key]

    async def check(self, vacancy: Vacancy) -> SalaryCheckRead:
        """Вилка вакансии относительно рынка категории."""
        result = check_salary(
            vacancy.salary_from,
            vacancy.salary_to,
            vacancy.salary_gross,
            await self.expectations(vacancy.specialization_id, vacancy.grade_ids),
        )
        return SalaryCheckRead(status=result.status, median=result.median, message=result.message)
