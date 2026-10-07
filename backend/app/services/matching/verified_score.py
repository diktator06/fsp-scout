import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.services.matching.facts import AssessmentFact, CandidateFacts

VPS_WEIGHTS = {"test": 0.55, "micro_tasks": 0.20, "fsp": 0.15, "profile": 0.10}
VPS_LABELS = {
    "test": "Адаптивный тест",
    "micro_tasks": "Микрозадачи",
    "fsp": "Достижения ФСП",
    "profile": "Подтверждённость профиля",
}
TEST_HALF_LIFE_DAYS = 365
EXPRESS_RELIABILITY = 0.85
MIN_PEERS_FOR_PERCENTILE = 8
TOP_BAND_WIDTH = 1.0


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    """Один фактор индекса: значение от 0 до 1 и его вес."""

    key: str
    label: str
    value: float
    weight: float


@dataclass(frozen=True, slots=True)
class VerifiedScore:
    """Индекс подтверждённого профиля (0–100) с разложением по факторам."""

    total: float
    components: tuple[ScoreComponent, ...]
    test_percentile: float | None


def _normal_cdf(value: float) -> float:
    """Функция распределения стандартного нормального закона."""
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def peer_percentile(
    theta: float, peers: Sequence[float], band: tuple[float, float | None]
) -> float:
    """Положение θ кандидата среди подтверждённых коллег по категории (0..1).

    Пока в категории мало людей, эмпирический перцентиль слишком шумный. Тогда θ
    сравнивается с полосой категории на шкале: середина полосы — 50-й перцентиль,
    её края — примерно 16-й и 84-й.
    """
    if len(peers) >= MIN_PEERS_FOR_PERCENTILE:
        below = sum(1 for value in peers if value < theta)
        equal = sum(1 for value in peers if value == theta)
        return (below + 0.5 * equal) / len(peers)
    low, high = band
    upper = high if high is not None else low + TOP_BAND_WIDTH
    center = (low + upper) / 2
    scale = max(0.2, (upper - low) / 2)
    return _normal_cdf((theta - center) / scale)


def assessment_component(
    test: AssessmentFact | None,
    peers: Sequence[float],
    band: tuple[float, float | None],
    now: datetime,
) -> tuple[float, float | None]:
    """Вклад теста: перцентиль × поправка на точность × затухание давности.

    Поправка 1 − SE²/2 снижает вклад неточной оценки. Давность затухает с периодом
    полураспада в год: тест двухлетней давности весит вчетверо меньше свежего.
    Экспресс-тест короче, поэтому ему доверяем меньше.
    """
    if test is None:
        return 0.0, None
    percentile = peer_percentile(test.theta, peers, band)
    precision = min(1.0, max(0.5, 1.0 - test.se**2 / 2))
    age_days = max(0.0, (now - test.finished_at).total_seconds() / 86400)
    recency = 0.5 ** (age_days / TEST_HALF_LIFE_DAYS)
    reliability = EXPRESS_RELIABILITY if test.express else 1.0
    return percentile * precision * recency * reliability, percentile


def profile_component(facts: CandidateFacts) -> float:
    """Подтверждённость профиля: email, заполненность, навыки, подтверждённые тестом."""
    verified_skills = sum(1 for skill in facts.skills.values() if skill.verified)
    return (
        0.3 * (1.0 if facts.email_verified else 0.0)
        + 0.4 * facts.completeness / 100
        + 0.3 * min(1.0, verified_skills / 3)
    )


def compute_verified_score(
    facts: CandidateFacts,
    peers: Sequence[float],
    band: tuple[float, float | None],
    now: datetime,
    *,
    micro_tasks: float = 0.0,
    fsp: float = 0.0,
) -> VerifiedScore:
    """Индекс подтверждённого профиля: VPS = 100 · (0,55·T + 0,20·M + 0,15·F + 0,10·P).

    Он ранжирует кандидатов внутри категории. Профиль без микрозадач и без ФСП не
    штрафуется: эти факторы просто не добавляют баллов (см. ARCHITECTURE_AND_PLAN.md §3.6.1).
    """
    test_value, percentile = assessment_component(facts.test, peers, band, now)
    values = {
        "test": test_value,
        "micro_tasks": micro_tasks,
        "fsp": fsp,
        "profile": profile_component(facts),
    }
    components = tuple(
        ScoreComponent(key=key, label=VPS_LABELS[key], value=round(values[key], 4), weight=weight)
        for key, weight in VPS_WEIGHTS.items()
    )
    total = 100 * sum(component.value * component.weight for component in components)
    return VerifiedScore(total=round(total, 1), components=components, test_percentile=percentile)
