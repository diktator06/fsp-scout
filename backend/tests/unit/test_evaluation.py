import uuid
from random import Random

import pytest

from app.services.assessment.irt import ItemParameters, simulate_response
from evaluation.assessment_validation import auc
from evaluation.bm25 import Bm25Index
from evaluation.integrity import person_fit, preknowledge
from evaluation.metrics import (
    bootstrap_interval,
    ideal_precision_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from evaluation.relevance import CandidateTruth, VacancyTruth, relevance, to_gross
from evaluation.simulate_assessment import cohen_kappa, weighted_kappa

RELEVANCE = {"a": 3, "b": 2, "c": 1, "d": 0, "e": 2}
VACANCY = VacancyTruth(
    vacancy_id="backend-1",
    specialization="backend",
    grade_ranks=frozenset({3}),
    must=frozenset({"python", "postgresql"}),
    nice=frozenset({"kafka"}),
    salary_to_gross=300_000,
    work_formats=frozenset({"remote"}),
    city=None,
)


def _candidate(**changes: object) -> CandidateTruth:
    """Кандидат, полностью подходящий вакансии; поля можно переопределить."""
    base: dict[str, object] = {
        "candidate_id": uuid.uuid4(),
        "specialization": "backend",
        "grade_rank": 3,
        "skills": frozenset({"python", "postgresql", "docker"}),
        "salary_gross": 280_000,
        "work_formats": frozenset({"remote", "office"}),
        "city": "Казань",
        "relocation_ready": False,
        "band_position": 0.2,
    }
    base.update(changes)
    return CandidateTruth(**base)  # type: ignore[arg-type]


def test_precision_counts_only_relevant_and_respects_ceiling() -> None:
    """P@k считает пары с оценкой не ниже порога; потолок — при нехватке релевантных."""
    ranking = ["d", "a", "c", "b"]
    assert precision_at_k(ranking, RELEVANCE, 4) == pytest.approx(0.5)
    assert precision_at_k(ranking, RELEVANCE, 4, threshold=1) == pytest.approx(0.75)
    assert ideal_precision_at_k(RELEVANCE, 10) == pytest.approx(0.3)
    assert precision_at_k(ranking, RELEVANCE, 0) == 0.0


def test_ndcg_is_one_for_ideal_order_and_lower_for_reversed() -> None:
    """Идеальный порядок даёт nDCG = 1, обратный — меньше; без релевантных — 0."""
    ideal = sorted(RELEVANCE, key=lambda key: -RELEVANCE[key])
    assert ndcg_at_k(ideal, RELEVANCE, 5) == pytest.approx(1.0)
    assert ndcg_at_k(list(reversed(ideal)), RELEVANCE, 5) < 0.8
    assert ndcg_at_k(["x"], {"x": 0}, 5) == 0.0


def test_reciprocal_rank_and_recall() -> None:
    """MRR — по первому релевантному; полнота — доля найденных релевантных."""
    assert reciprocal_rank(["d", "c", "b"], RELEVANCE) == pytest.approx(1 / 3)
    assert reciprocal_rank(["d", "c"], RELEVANCE) == 0.0
    assert recall_at_k(["a", "d", "b", "c"], RELEVANCE, 2) == pytest.approx(1 / 3)


def test_bootstrap_interval_covers_mean() -> None:
    """Бутстреп-интервал содержит среднее и сужается до точки на константе."""
    values = [0.2, 0.4, 0.6, 0.3, 0.5]
    low, high = bootstrap_interval(values, samples=500)
    assert low <= sum(values) / len(values) <= high
    assert bootstrap_interval([0.5] * 4, samples=200) == (0.5, 0.5)


def test_relevance_levels() -> None:
    """Разметка: 3 — подходит и силён, 2 — подходит, 1 — частично, 0 — мимо."""
    assert relevance(VACANCY, _candidate(band_position=0.7)) == 3
    assert relevance(VACANCY, _candidate()) == 2
    assert relevance(VACANCY, _candidate(grade_rank=4)) == 1
    assert relevance(VACANCY, _candidate(skills=frozenset({"python"}))) == 1
    assert relevance(VACANCY, _candidate(salary_gross=360_000)) == 1
    assert relevance(VACANCY, _candidate(salary_gross=400_000)) == 0
    assert relevance(VACANCY, _candidate(specialization="frontend")) == 0
    assert relevance(VACANCY, _candidate(work_formats=frozenset({"office"}))) == 0
    assert to_gross(87_000, gross=False) == pytest.approx(100_000)


def test_office_vacancy_needs_same_city_or_relocation() -> None:
    """Офис в другом городе подходит только готовому к переезду."""
    office = VacancyTruth(
        vacancy_id="backend-2",
        specialization="backend",
        grade_ranks=frozenset({3}),
        must=frozenset({"python"}),
        nice=frozenset(),
        salary_to_gross=300_000,
        work_formats=frozenset({"office"}),
        city="Москва",
    )
    assert relevance(office, _candidate()) == 0
    assert relevance(office, _candidate(relocation_ready=True)) == 2
    assert relevance(office, _candidate(city=" москва ")) == 2


def test_bm25_prefers_documents_with_rare_query_terms() -> None:
    """BM25 поднимает документ с редким термином запроса выше общего."""
    index = Bm25Index(
        {
            "kafka": "Python разработчик, Kafka и PostgreSQL",
            "plain": "Python разработчик, Django",
            "front": "React и TypeScript",
        }
    )
    ranking = index.rank("Python Kafka")
    assert ranking[0] == "kafka"
    assert ranking[-1] == "front"
    assert index.rank("Python", keys=["front", "plain"])[0] == "plain"


def test_kappas_reward_agreement_and_weight_distance() -> None:
    """Полное согласие — 1; взвешенная каппа мягче к расхождению на соседний грейд."""
    grades = [1, 2, 3, 4, 2, 3]
    assert weighted_kappa(grades, grades, 4) == pytest.approx(1.0)
    assert cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == pytest.approx(1.0)
    near = [2, 3, 4, 4, 3, 4]
    far = [3, 4, 1, 2, 4, 1]
    assert weighted_kappa(grades, near, 4) > weighted_kappa(grades, far, 4)
    assert weighted_kappa(grades, near, 4) > cohen_kappa(
        [str(g) for g in grades], [str(g) for g in near]
    )


def test_auc_bounds() -> None:
    """AUC = 1 при полном разделении, 0,5 при совпадении, 0 без одной из групп."""
    assert auc([2.0, 3.0], [0.0, 1.0]) == pytest.approx(1.0)
    assert auc([1.0, 1.0], [1.0, 1.0]) == pytest.approx(0.5)
    assert auc([], [1.0]) == 0.0


def test_preknowledge_flags_suspicious_success_on_exposed_items() -> None:
    """Решены все «популярные» трудные задания при средних ответах на остальные — сигнал."""
    rng = Random(5)
    rest = [ItemParameters(a=1.4, b=rng.uniform(-1.0, 1.0)) for _ in range(10)]
    hot = [ItemParameters(a=1.4, b=2.0) for _ in range(4)]
    honest = [(item, simulate_response(0.0, item, rng.random())) for item in rest]
    codes = [f"r{index}" for index in range(10)] + [f"h{index}" for index in range(4)]
    exposed = {f"h{index}" for index in range(4)}
    cheating = preknowledge(codes, honest + [(item, 1.0) for item in hot], exposed)
    fair = preknowledge(codes, honest + [(item, 0.0) for item in hot], exposed)
    assert cheating is not None and fair is not None and cheating > 1.5 > fair
    assert preknowledge(codes[:3], honest[:3], exposed) is None


def test_person_fit_is_negative_for_inverted_pattern() -> None:
    """Трудные решены, лёгкие провалены — l_z сильно отрицателен; мало ответов — нет оценки."""
    easy = [ItemParameters(a=1.5, b=-1.5)] * 4
    hard = [ItemParameters(a=1.5, b=1.5)] * 4
    typical = [(item, 1.0) for item in easy] + [(item, 0.0) for item in hard]
    inverted = [(item, 0.0) for item in easy] + [(item, 1.0) for item in hard]
    fit_typical, fit_inverted = person_fit(typical, 0.0), person_fit(inverted, 0.0)
    assert fit_typical is not None and fit_inverted is not None
    assert fit_inverted < -2.0 < fit_typical
    assert person_fit(typical[:3], 0.0) is None
