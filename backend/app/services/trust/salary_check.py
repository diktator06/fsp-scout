from dataclasses import dataclass
from typing import Literal

from app.services.matching.match_scoring import to_gross

SalaryStatus = Literal["ok", "below_market", "suspicious", "unknown"]

MIN_SAMPLE = 3
LOW_FACTOR = 0.6
HIGH_FACTOR = 2.0


@dataclass(frozen=True, slots=True)
class SalaryCheck:
    """Вилка вакансии относительно ожиданий кандидатов категории."""

    status: SalaryStatus
    median: int | None
    message: str


def check_salary(
    salary_from: int,
    salary_to: int,
    gross: bool,
    expectations_gross: list[float],
) -> SalaryCheck:
    """Сравнивает вилку с медианой открытых ожиданий кандидатов той же категории.

    Заметно ниже рынка — предупреждение работодателю: откликов и принятий будет мало.
    В разы выше рынка — частый признак фиктивной вакансии («зарплата мечты» ради
    сбора контактов): работодатель видит предупреждение, а модератор — отметку.
    Медиана считается только по трём и более открытым ожиданиям, как в рыночном срезе.
    """
    if len(expectations_gross) < MIN_SAMPLE:
        return SalaryCheck("unknown", None, "Мало открытых ожиданий в категории для сравнения")
    ordered = sorted(expectations_gross)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) // 2
    low = to_gross(salary_from, gross)
    high = to_gross(salary_to, gross)
    rounded = round(median / 1000) * 1000
    if high < LOW_FACTOR * median:
        return SalaryCheck(
            "below_market",
            rounded,
            "Вилка заметно ниже ожиданий кандидатов категории — откликов будет мало",
        )
    if low > HIGH_FACTOR * median:
        return SalaryCheck(
            "suspicious",
            rounded,
            "Вилка в разы выше рынка: так часто выглядят фиктивные вакансии, модератор проверит",
        )
    return SalaryCheck("ok", rounded, "Вилка в рынке категории")
