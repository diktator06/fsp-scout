from app.services.assessment.adaptive_engine import EXPRESS_CONFIG
from evaluation.simulate_assessment import simulate_specialization


def test_full_test_recovers_ability_and_separates_grades() -> None:
    """Полный тест на синтетической популяции: θ восстанавливается, грейды различимы.

    Пороги ниже фактических значений отчёта (r ≈ 0,9, ±1 ступень ≈ 99 %), чтобы тест
    ловил регрессии движка, но не падал от случайности выборки.
    """
    report = simulate_specialization("backend", candidates=120, seed=11)
    assert report.theta_correlation > 0.85
    assert report.grade_within_one > 0.95
    assert report.decision_accuracy > 0.75
    assert 12 <= report.mean_items <= 20


def test_express_mode_is_shorter_and_still_informative() -> None:
    """Экспресс-режим короче полного и всё ещё заметно лучше случайного угадывания."""
    report = simulate_specialization(
        "frontend", candidates=120, seed=12, config=EXPRESS_CONFIG, mode="express"
    )
    assert report.mean_items <= 8
    assert report.theta_correlation > 0.7
