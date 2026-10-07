from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

HALF_LIFE_DAYS = 60.0
PRIOR_WEIGHT = 0.5


@dataclass(frozen=True, slots=True)
class GradedResult:
    """Оценённая микрозадача: балл 0..1 и момент оценки."""

    score: float
    graded_at: datetime
    title: str = ""
    kind: str = "solve"


@dataclass(frozen=True, slots=True)
class Freshness:
    """Фактор M индекса профиля — актуальность по свежим микрозадачам."""

    value: float
    count: int
    last: GradedResult | None


NO_FRESHNESS = Freshness(value=0.0, count=0, last=None)


def recency_weight(graded_at: datetime, now: datetime) -> float:
    """Вес результата по давности: полураспад 60 дней."""
    days = max(0.0, (now - graded_at).total_seconds() / 86400)
    return float(0.5 ** (days / HALF_LIFE_DAYS))


def freshness(results: Sequence[GradedResult], now: datetime) -> Freshness:
    """M = Σ w·s / (Σ w + 0,5), где w — вес давности, s — балл задачи.

    Это сглаженное среднее с затуханием. Одна свежая задача на отлично даёт 0,67,
    три — 0,86. Без новых задач M постепенно падает: через два месяца вес
    результата вдвое меньше, поэтому фактор и называется актуальностью профиля.
    Априорный вес 0,5 не даёт одной удачной задаче сразу поднять фактор до максимума.
    """
    if not results:
        return NO_FRESHNESS
    weighted = 0.0
    total = 0.0
    for item in results:
        weight = recency_weight(item.graded_at, now)
        weighted += weight * max(0.0, min(1.0, item.score))
        total += weight
    last = max(results, key=lambda item: item.graded_at)
    return Freshness(
        value=round(weighted / (total + PRIOR_WEIGHT), 4), count=len(results), last=last
    )
