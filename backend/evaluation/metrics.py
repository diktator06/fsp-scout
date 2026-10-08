import math
from collections.abc import Callable, Mapping, Sequence
from random import Random

RELEVANT = 2
PARTIAL = 1
BOOTSTRAP_SAMPLES = 2000


def precision_at_k(
    ranking: Sequence[str], relevance: Mapping[str, int], k: int, threshold: int = RELEVANT
) -> float:
    """Доля релевантных (оценка не ниже порога) среди первых k позиций выдачи."""
    if k <= 0:
        return 0.0
    hits = sum(1 for item in ranking[:k] if relevance.get(item, 0) >= threshold)
    return hits / k


def ideal_precision_at_k(relevance: Mapping[str, int], k: int, threshold: int = RELEVANT) -> float:
    """Потолок P@k: если релевантных меньше k, даже идеальная выдача не наберёт 1,0."""
    relevant = sum(1 for grade in relevance.values() if grade >= threshold)
    return min(relevant, k) / k if k > 0 else 0.0


def dcg_at_k(gains: Sequence[int], k: int) -> float:
    """Дисконтированная полезность: выигрыш 2^rel − 1, дисконт log2(позиция + 1)."""
    return float(
        sum((2**gain - 1) / math.log2(position + 2) for position, gain in enumerate(gains[:k]))
    )


def ndcg_at_k(ranking: Sequence[str], relevance: Mapping[str, int], k: int) -> float:
    """nDCG@k со ступенчатой релевантностью; без релевантных кандидатов — 0."""
    ideal = dcg_at_k(sorted(relevance.values(), reverse=True), k)
    if ideal == 0:
        return 0.0
    return dcg_at_k([relevance.get(item, 0) for item in ranking], k) / ideal


def reciprocal_rank(
    ranking: Sequence[str], relevance: Mapping[str, int], threshold: int = RELEVANT
) -> float:
    """1 / позиция первого релевантного кандидата; если его нет в выдаче — 0."""
    for position, item in enumerate(ranking, start=1):
        if relevance.get(item, 0) >= threshold:
            return 1.0 / position
    return 0.0


def recall_at_k(
    ranking: Sequence[str], relevance: Mapping[str, int], k: int, threshold: int = RELEVANT
) -> float:
    """Доля всех релевантных кандидатов, попавших в первые k позиций."""
    relevant = {item for item, grade in relevance.items() if grade >= threshold}
    if not relevant:
        return 0.0
    return len(relevant & set(ranking[:k])) / len(relevant)


def bootstrap_interval(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float] | None = None,
    *,
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = 7,
) -> tuple[float, float]:
    """95-процентный бутстреп-интервал среднего по вакансиям.

    Вакансий немного, поэтому точечная оценка без интервала вводила бы в заблуждение:
    интервал показывает, насколько метрика зависит от состава набора.
    """
    if not values:
        return (0.0, 0.0)
    measure = statistic or (lambda sample: sum(sample) / len(sample))
    rng = Random(seed)
    estimates = sorted(
        measure([values[rng.randrange(len(values))] for _ in values]) for _ in range(samples)
    )
    low = estimates[int(0.025 * samples)]
    high = estimates[min(samples - 1, int(0.975 * samples))]
    return (round(low, 4), round(high, 4))
