from datetime import UTC, datetime, timedelta
from random import Random

import numpy as np
import pytest

from app.models.assessment import SessionOutcome, SessionStatus
from app.services.assessment.adaptive_engine import (
    EngineConfig,
    PoolItem,
    competency_deficits,
    select_next_item,
    should_stop,
)
from app.services.assessment.blueprint import CompetencyWeight, build_blueprint
from app.services.assessment.calibration import calibrate
from app.services.assessment.grade_policy import (
    GradeInfo,
    GradeOption,
    PolicyConfig,
    SessionSummary,
    evaluate_eligibility,
)
from app.services.assessment.grading import GradeLevel, decide_grade
from app.services.assessment.irt import (
    AbilityEstimate,
    ItemParameters,
    estimate_ability,
    estimate_ability_wle,
    information,
    probability,
    simulate_response,
)
from app.services.assessment.scoring import parse_number, score_answer

LEVELS = [
    GradeLevel(grade_id=1, code="intern", rank=1, theta_cut=-1.5),
    GradeLevel(grade_id=2, code="junior", rank=2, theta_cut=-0.5),
    GradeLevel(grade_id=3, code="middle", rank=3, theta_cut=0.4),
    GradeLevel(grade_id=4, code="senior", rank=4, theta_cut=1.2),
]
GRADES = [
    GradeInfo(grade_id=level.grade_id, code=level.code, name=level.code.title(), rank=level.rank)
    for level in LEVELS
]
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def test_probability_is_monotonic_and_respects_guessing() -> None:
    """Вероятность успеха растёт с θ и не опускается ниже параметра угадывания."""
    item = ItemParameters(a=1.5, b=0.0, c=0.2)
    values = probability(np.linspace(-4, 4, 50), item)
    assert np.all(np.diff(values) > 0)
    assert values[0] >= 0.2
    assert float(probability(0.0, ItemParameters(a=1.0, b=0.0))) == pytest.approx(0.5)


def test_information_peaks_near_difficulty() -> None:
    """Задание информативнее всего около своей сложности и почти бесполезно далеко от неё."""
    item = ItemParameters(a=1.4, b=0.5)
    assert information(0.5, item) > information(2.5, item) * 3
    assert information(0.5, item) > information(-1.5, item) * 3


def test_eap_recovers_ability_on_long_test() -> None:
    """На длинном тесте с точными параметрами EAP восстанавливает θ (корреляция выше 0,93)."""
    rng = Random(1)
    bank = [ItemParameters(a=rng.uniform(1.0, 2.0), b=rng.uniform(-2.5, 2.5)) for _ in range(40)]
    truths, estimates = [], []
    for _ in range(150):
        theta = rng.gauss(0, 1)
        responses = [(item, simulate_response(theta, item, rng.random())) for item in bank]
        truths.append(theta)
        estimates.append(estimate_ability(responses).theta)
    assert float(np.corrcoef(truths, estimates)[0, 1]) > 0.93


def test_se_shrinks_with_more_answers() -> None:
    """Каждый ответ уточняет оценку: стандартная ошибка убывает."""
    item = ItemParameters(a=1.5, b=0.0)
    short = estimate_ability([(item, 1.0)] * 2)
    long = estimate_ability([(item, 1.0), (item, 0.0)] * 6)
    assert estimate_ability([]).se == pytest.approx(1.0, abs=0.02)
    assert long.se < short.se < 1.0


def test_wle_is_less_biased_than_eap_for_strong_candidates() -> None:
    """WLE не стягивает сильных к среднему: смещение заметно меньше, чем у EAP.

    На коротком тесте EAP с априорным N(0, 1) занижает θ = 1,8; итоговое решение о
    грейде поэтому принимается по WLE.
    """
    rng = Random(3)
    bank = [ItemParameters(a=rng.uniform(1.0, 1.8), b=rng.uniform(0.5, 2.5)) for _ in range(14)]
    eap_bias = wle_bias = 0.0
    runs = 300
    for _ in range(runs):
        responses = [(item, simulate_response(1.8, item, rng.random())) for item in bank]
        eap_bias += estimate_ability(responses).theta - 1.8
        wle_bias += estimate_ability_wle(responses).theta - 1.8
    assert abs(wle_bias / runs) < abs(eap_bias / runs) / 2
    assert eap_bias / runs < -0.15


def test_wle_is_finite_on_extreme_patterns() -> None:
    """При всех верных или всех неверных ответах WLE конечна, без ответов — это EAP."""
    item = ItemParameters(a=1.5, b=0.0)
    perfect = estimate_ability_wle([(item, 1.0)] * 6)
    failed = estimate_ability_wle([(item, 0.0)] * 6)
    assert 0.5 < perfect.theta < 4.0 and -4.0 < failed.theta < -0.5
    assert perfect.theta == pytest.approx(-failed.theta, abs=0.02)
    assert estimate_ability_wle([]) == estimate_ability([])


def test_blueprint_gates_language_bound_competencies() -> None:
    """Без Python в стеке компетенция Python исключается, её вес делится между остальными."""
    weights = [
        CompetencyWeight("python_core", 0.4, ("python",)),
        CompetencyWeight("sql", 0.3),
        CompetencyWeight("algorithms", 0.3),
    ]
    with_python = build_blueprint(weights, ["python"])
    java_only = build_blueprint(weights, ["java"])
    assert with_python == {"algorithms": 0.3, "python_core": 0.4, "sql": 0.3}
    assert java_only == {"algorithms": 0.5, "sql": 0.5}
    assert build_blueprint(weights, ["python"], available_competencies=["sql"]) == {"sql": 1.0}


def test_competency_deficits_balance_content() -> None:
    """Компетенция, которой недодали заданий относительно blueprint, идёт первой."""
    blueprint = {"sql": 0.5, "algorithms": 0.3, "http": 0.2}
    assert competency_deficits(blueprint, ["sql", "sql", "sql"])[0][0] == "algorithms"
    assert competency_deficits(blueprint, [])[0][0] == "sql"


def _pool() -> list[PoolItem]:
    """Небольшой пул семейств трёх компетенций разной сложности."""
    items = []
    for index, (competency, b) in enumerate(
        [("sql", -1.0), ("sql", 0.0), ("sql", 1.0), ("sql", 2.0), ("algo", -0.5), ("algo", 0.8)]
    ):
        items.append(
            PoolItem(index, f"{competency}.{index}", competency, ItemParameters(a=1.5, b=b))
        )
    return items


def test_select_prefers_informative_item_in_deficit_competency() -> None:
    """Выбирается семейство недобранной компетенции, близкое по сложности к θ̂."""
    config = EngineConfig(randomesque=1)
    chosen = select_next_item(
        _pool(), {"sql": 0.5, "algo": 0.5}, ["algo"], AbilityEstimate(1.0, 0.5), Random(0), config
    )
    assert chosen is not None and chosen.competency == "sql"
    assert chosen.params.b == 1.0


def test_exposure_and_seen_penalties_change_choice() -> None:
    """Пережатое по экспозиции или уже виденное семейство уступает соседнему."""
    config = EngineConfig(randomesque=1)
    pool = [
        PoolItem(1, "sql.best", "sql", ItemParameters(1.5, 1.0), exposure_rate=0.9),
        PoolItem(2, "sql.near", "sql", ItemParameters(1.5, 0.7)),
    ]
    chosen = select_next_item(pool, {"sql": 1.0}, [], AbilityEstimate(1.0, 0.5), Random(0), config)
    assert chosen is not None and chosen.code == "sql.near"

    seen = [
        PoolItem(1, "sql.best", "sql", ItemParameters(1.5, 1.0), seen_before=True),
        PoolItem(2, "sql.near", "sql", ItemParameters(1.5, 0.6)),
    ]
    chosen = select_next_item(seen, {"sql": 1.0}, [], AbilityEstimate(1.0, 0.5), Random(0), config)
    assert chosen is not None and chosen.code == "sql.near"


def test_stopping_rule() -> None:
    """Тест не короче минимума и не длиннее максимума; в середине — по уверенности решения."""
    config = EngineConfig(min_items=4, max_items=10)
    far = AbilityEstimate(theta=2.0, se=0.4)
    near = AbilityEstimate(theta=0.5, se=0.4)
    assert not should_stop(
        scored_items=3, estimate=far, cut=0.4, config=config, pool_exhausted=False
    )
    assert should_stop(scored_items=4, estimate=far, cut=0.4, config=config, pool_exhausted=False)
    assert not should_stop(
        scored_items=6, estimate=near, cut=0.4, config=config, pool_exhausted=False
    )
    assert should_stop(scored_items=10, estimate=near, cut=0.4, config=config, pool_exhausted=False)
    assert should_stop(scored_items=1, estimate=near, cut=0.4, config=config, pool_exhausted=True)


@pytest.mark.parametrize(
    ("theta", "se", "expected", "suggested"),
    [
        (2.1, 0.3, SessionOutcome.PASSED_CONFIDENT, None),
        (0.6, 0.4, SessionOutcome.PASSED, None),
        (-0.1, 0.3, SessionOutcome.FAILED, "junior"),
        (-1.3, 0.5, SessionOutcome.FAILED, None),
    ],
)
def test_grade_decision(
    theta: float, se: float, expected: SessionOutcome, suggested: str | None
) -> None:
    """Уверенный успех открывает уровень выше, неудача может предложить нижний грейд."""
    decision = decide_grade(AbilityEstimate(theta, se), LEVELS[2], LEVELS)
    assert decision.outcome is expected
    assert (decision.suggested_lower.code if decision.suggested_lower else None) == suggested
    if expected is SessionOutcome.PASSED_CONFIDENT:
        assert (
            decision.next_grade_unlocked is not None
            and decision.next_grade_unlocked.code == "senior"
        )


def _session(
    status: SessionStatus,
    target_rank: int,
    outcome: SessionOutcome | None,
    hours_ago: float,
    rank_before: int | None = None,
) -> SessionSummary:
    """Сводка прошлой сессии для проверки политики."""
    moment = NOW - timedelta(hours=hours_ago)
    return SessionSummary(status, target_rank, outcome, moment, moment, rank_before)


def _allowed(options: list[GradeOption]) -> dict[str, bool]:
    """Карта «грейд → можно ли начать тест»."""
    return {option.grade.code: option.allowed for option in options}


def test_onboarding_failure_does_not_burn_lower_attempt() -> None:
    """После провала Middle уровни ниже доступны сразу, а Middle и Senior — через сутки."""
    sessions = [_session(SessionStatus.COMPLETED, 3, SessionOutcome.FAILED, hours_ago=1)]
    options = evaluate_eligibility(
        grades=GRADES,
        current_rank=None,
        last_change_at=None,
        sessions=sessions,
        now=NOW,
        config=PolicyConfig(),
    )
    assert _allowed(options) == {"intern": True, "junior": True, "middle": False, "senior": False}
    blocked = next(option for option in options if option.grade.code == "middle")
    assert blocked.available_at == NOW - timedelta(hours=1) + timedelta(hours=24)


def test_onboarding_abandon_counts_as_failure_and_expires() -> None:
    """Прерванный тест блокирует повтор уровня, но только на сутки."""
    recent = [_session(SessionStatus.ABANDONED, 2, None, hours_ago=2)]
    old = [_session(SessionStatus.ABANDONED, 2, None, hours_ago=30)]
    config = PolicyConfig()
    assert not _allowed(
        evaluate_eligibility(
            grades=GRADES,
            current_rank=None,
            last_change_at=None,
            sessions=recent,
            now=NOW,
            config=config,
        )
    )["junior"]
    assert all(
        _allowed(
            evaluate_eligibility(
                grades=GRADES,
                current_rank=None,
                last_change_at=None,
                sessions=old,
                now=NOW,
                config=config,
            )
        ).values()
    )


def test_assigned_grade_respects_cooldown_and_confident_window() -> None:
    """После присвоения смена раз в 90 дней; уверенный успех сразу открывает следующую ступень."""
    config = PolicyConfig()
    cooled = evaluate_eligibility(
        grades=GRADES,
        current_rank=2,
        last_change_at=NOW - timedelta(days=10),
        sessions=[],
        now=NOW,
        config=config,
    )
    assert _allowed(cooled) == {"intern": False, "junior": False, "middle": False, "senior": False}

    confident = [_session(SessionStatus.COMPLETED, 2, SessionOutcome.PASSED_CONFIDENT, hours_ago=1)]
    unlocked = evaluate_eligibility(
        grades=GRADES,
        current_rank=2,
        last_change_at=NOW - timedelta(hours=1),
        sessions=confident,
        now=NOW,
        config=config,
    )
    assert _allowed(unlocked) == {"intern": False, "junior": False, "middle": True, "senior": False}


def test_failed_upgrade_waits_retry_period() -> None:
    """Неудачное повышение не снижает грейд, повтор — через 30 дней."""
    config = PolicyConfig()
    failed = [
        _session(SessionStatus.COMPLETED, 3, SessionOutcome.FAILED, hours_ago=24 * 5, rank_before=2)
    ]
    options = evaluate_eligibility(
        grades=GRADES,
        current_rank=2,
        last_change_at=NOW - timedelta(days=200),
        sessions=failed,
        now=NOW,
        config=config,
    )
    assert _allowed(options)["middle"] is False
    assert _allowed(options)["intern"] is True
    in_progress = [_session(SessionStatus.IN_PROGRESS, 3, None, hours_ago=0.1)]
    assert not any(
        _allowed(
            evaluate_eligibility(
                grades=GRADES,
                current_rank=2,
                last_change_at=None,
                sessions=in_progress,
                now=NOW,
                config=config,
            )
        ).values()
    )


def test_calibration_recovers_difficulty() -> None:
    """MML-EM восстанавливает сложность и дискриминативность семейств по разреженным ответам."""
    rng = np.random.default_rng(7)
    true_b = np.linspace(-2, 2, 14)
    true_a = rng.uniform(0.9, 1.8, size=true_b.size)
    thetas = rng.normal(0, 1, size=1500)
    p = 1 / (1 + np.exp(-true_a[None, :] * (thetas[:, None] - true_b[None, :])))
    responses = (rng.random(p.shape) < p).astype(float)
    responses[rng.random(p.shape) < 0.3] = np.nan
    calibrated = calibrate(responses, np.zeros(true_b.size))
    estimated_b = np.array([item.b for item in calibrated])
    estimated_a = np.array([item.a for item in calibrated])
    assert float(np.corrcoef(true_b, estimated_b)[0, 1]) > 0.95
    assert float(np.corrcoef(true_a, estimated_a)[0, 1]) > 0.7
    assert calibrated[0].responses < 1500


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12,5", 12.5),
        (" 1 200 ", 1200.0),
        ("43.2 мин", 43.2),
        ("80 %", 80.0),
        ("-3", -3.0),
        ("abc", None),
        ("1+2", None),
    ],
)
def test_parse_number(raw: str, expected: float | None) -> None:
    """Числовой ответ принимается в привычной записи, выражения — нет."""
    assert parse_number(raw) == expected


def test_score_answer() -> None:
    """Выбор сравнивается по ключу варианта, число — с допуском генератора."""
    assert score_answer({"kind": "choice", "correct": "c"}, " C ") == 1.0
    assert score_answer({"kind": "choice", "correct": "c"}, "a") == 0.0
    assert score_answer({"kind": "numeric", "value": 43.2, "tolerance": 0.1}, "43,25") == 1.0
    assert score_answer({"kind": "numeric", "value": 43.2, "tolerance": 0.1}, "44") == 0.0
    assert score_answer({"kind": "numeric", "value": 5, "tolerance": 0}, "пять") == 0.0
