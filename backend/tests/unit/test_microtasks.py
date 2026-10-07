from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import DomainValidationError
from app.services.microtasks.freshness import GradedResult, freshness, recency_weight
from app.services.microtasks.grading import auto_grade, rating_to_score

NOW = datetime(2026, 10, 7, tzinfo=UTC)


def test_freshness_formula_and_decay() -> None:
    """M = Σw·s / (Σw + 0,5): одна свежая отличная задача — 2/3, без задач — 0."""
    assert freshness([], NOW).value == 0
    one = freshness([GradedResult(score=1.0, graded_at=NOW)], NOW)
    assert one.value == pytest.approx(2 / 3, abs=1e-4)
    three = freshness([GradedResult(score=1.0, graded_at=NOW)] * 3, NOW)
    assert three.value == pytest.approx(3 / 3.5, abs=1e-4)
    old = freshness([GradedResult(score=1.0, graded_at=NOW - timedelta(days=60))], NOW)
    assert old.value == pytest.approx(0.5, abs=1e-3)
    assert recency_weight(NOW - timedelta(days=120), NOW) == pytest.approx(0.25, abs=1e-3)


def test_freshness_reports_last_result() -> None:
    """Последний результат нужен для объяснения «5/5, 12 дней назад»."""
    results = [
        GradedResult(score=0.5, graded_at=NOW - timedelta(days=30), title="Старая"),
        GradedResult(score=1.0, graded_at=NOW - timedelta(days=2), title="Свежая"),
    ]
    summary = freshness(results, NOW)
    assert summary.count == 2
    assert summary.last is not None and summary.last.title == "Свежая"


def test_auto_grade_number_and_choice() -> None:
    """Число сверяется с допуском и понимает запятую, выбор — по номеру варианта."""
    key = {"kind": "number", "value": 11, "tolerance": 0.5}
    assert auto_grade(key, "11") == 1
    assert auto_grade(key, "11,4") == 1
    assert auto_grade(key, "12") == 0
    with pytest.raises(DomainValidationError):
        auto_grade(key, "одиннадцать")
    choice = {"kind": "choice", "correct": 2}
    assert auto_grade(choice, "2") == 1
    assert auto_grade(choice, "0") == 0


def test_rating_scale() -> None:
    """Оценка 1–5 переводится в балл 0..1."""
    assert [rating_to_score(value) for value in (1, 3, 5)] == [0, 0.5, 1]
