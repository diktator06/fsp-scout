import argparse
import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from random import Random

import numpy as np
import yaml

from app.models.assessment import ItemFamilyStatus, SessionOutcome
from app.services.assessment.adaptive_engine import (
    EngineConfig,
    PoolItem,
    select_next_item,
    should_stop,
)
from app.services.assessment.blueprint import CompetencyWeight, build_blueprint
from app.services.assessment.grading import GradeLevel, decide_grade, grade_for_theta
from app.services.assessment.irt import (
    AbilityEstimate,
    ItemParameters,
    estimate_ability,
    simulate_response,
)
from app.services.assessment.item_generators import REGISTRY

SEED_DATA = Path(__file__).resolve().parents[1] / "app" / "seed" / "data"
REPORT_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "validation" / "assessment_simulation.json"
)


@dataclass(frozen=True, slots=True)
class SimulatedFamily:
    """Семейство банка в симуляции: оперативные параметры движка и «истинные» параметры."""

    item: PoolItem
    true_params: ItemParameters


@dataclass
class ExposureTracker:
    """Сколько раз показано каждое семейство и сколько всего было сессий."""

    shows: Counter[str] = field(default_factory=Counter)
    sessions: int = 0

    def rate(self, code: str) -> float:
        """Доля сессий, в которых показывалось семейство."""
        return self.shows[code] / self.sessions if self.sessions else 0.0


@dataclass
class SpecializationReport:
    """Метрики стенда по одной специализации."""

    specialization: str
    candidates: int
    bank_size: int
    theta_correlation: float
    theta_rmse: float
    theta_bias: float
    decision_accuracy: float
    grade_exact: float
    grade_within_one: float
    retest_decision_agreement: float
    retest_grade_kappa: float
    retest_theta_correlation: float
    mean_items: float
    mean_se: float
    max_exposure_rate: float
    onboarding_exact: float = 0.0
    onboarding_within_one: float = 0.0
    onboarding_mean_sessions: float = 0.0
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    onboarding_confusion: dict[str, dict[str, int]] = field(default_factory=dict)


def load_levels() -> list[GradeLevel]:
    """Грейды и пороги θ из сида справочников."""
    grades = yaml.safe_load((SEED_DATA / "grades.yaml").read_text(encoding="utf-8"))
    return [
        GradeLevel(
            grade_id=g["rank"], code=g["code"], rank=g["rank"], theta_cut=g["default_theta_cut"]
        )
        for g in grades
    ]


def load_blueprint(specialization: str) -> list[CompetencyWeight]:
    """Blueprint специализации из сида компетенций."""
    data = yaml.safe_load((SEED_DATA / "competencies.yaml").read_text(encoding="utf-8"))
    gates = {item["code"]: tuple(item.get("gate_skills", [])) for item in data["competencies"]}
    weights = data["blueprints"][specialization]
    return [
        CompetencyWeight(code=code, weight=weight, gate_skill_slugs=gates[code])
        for code, weight in weights.items()
    ]


def build_bank(
    competencies: set[str], rng: Random, noise_b: float, noise_log_a: float
) -> list[SimulatedFamily]:
    """Банк семейств специализации.

    Движок работает с экспертными априорными параметрами, а ответы виртуальных
    кандидатов генерируются по «истинным» параметрам, которые отличаются от
    априорных случайным шумом. Так проверяется устойчивость к неточной начальной
    оценке сложности: в реальности её исправит калибровка.
    """
    bank = []
    for index, spec in enumerate(sorted(REGISTRY.values(), key=lambda s: s.code)):
        if spec.competency not in competencies or spec.status is not ItemFamilyStatus.ACTIVE:
            continue
        operational = ItemParameters(
            a=spec.discrimination, b=spec.prior_difficulty, c=spec.guessing
        )
        true_params = ItemParameters(
            a=spec.discrimination * math.exp(rng.gauss(0, noise_log_a)),
            b=spec.prior_difficulty + rng.gauss(0, noise_b),
            c=spec.guessing,
        )
        bank.append(
            SimulatedFamily(
                item=PoolItem(
                    family_id=index, code=spec.code, competency=spec.competency, params=operational
                ),
                true_params=true_params,
            )
        )
    return bank


def run_session(
    theta_true: float,
    bank: Sequence[SimulatedFamily],
    blueprint: dict[str, float],
    target: GradeLevel,
    rng: Random,
    config: EngineConfig,
    tracker: ExposureTracker,
    excluded: set[str] | None = None,
) -> tuple[AbilityEstimate, list[str]]:
    """Одна адаптивная сессия виртуального кандидата тем же движком, что и в продукте.

    Доля показов семейства передаётся движку так же, как в продукте (показы ÷ сессии):
    без этого контроль экспозиции в симуляции не работал бы.
    """
    by_code = {family.item.code: family for family in bank}
    tracker.sessions += 1
    seen_before = set(excluded or ())
    used: set[str] = set()
    responses: list[tuple[ItemParameters, float]] = []
    administered: list[str] = []
    competencies: list[str] = []
    estimate = estimate_ability([])
    while True:
        pool = [
            replace(
                family.item,
                seen_before=family.item.code in seen_before,
                exposure_rate=tracker.rate(family.item.code),
            )
            for family in bank
            if family.item.code not in used
        ]
        if should_stop(
            scored_items=len(responses),
            estimate=estimate,
            cut=target.theta_cut,
            config=config,
            pool_exhausted=not pool,
        ):
            break
        chosen = select_next_item(pool, blueprint, competencies, estimate, rng, config)
        if chosen is None:
            break
        used.add(chosen.code)
        tracker.shows[chosen.code] += 1
        score = simulate_response(theta_true, by_code[chosen.code].true_params, rng.random())
        responses.append((chosen.params, score))
        administered.append(chosen.code)
        competencies.append(chosen.competency)
        estimate = estimate_ability(responses)
    return estimate, administered


def simulate_onboarding(
    theta_true: float,
    claimed: GradeLevel,
    levels: Sequence[GradeLevel],
    bank: Sequence[SimulatedFamily],
    blueprint: dict[str, float],
    rng: Random,
    config: EngineConfig,
    tracker: ExposureTracker,
    max_sessions: int = 3,
) -> tuple[GradeLevel | None, int]:
    """Путь кандидата по правилам продукта до присвоения категории.

    * Сдал заявленный грейд — категория присвоена. При уверенном прохождении
      кандидат сразу пробует уровень выше (в продукте это окно 24 часа).
    * Не сдал — принимает предложенный нижний грейд, если он есть, иначе в тот же
      день сдаёт тест на ступень ниже. Всего не больше трёх сессий, как в политике.
    """
    by_rank = {level.rank: level for level in levels}
    assigned: GradeLevel | None = None
    target = claimed
    seen: set[str] = set()
    sessions = 0
    while sessions < max_sessions:
        estimate, administered = run_session(
            theta_true, bank, blueprint, target, rng, config, tracker, seen
        )
        seen.update(administered)
        sessions += 1
        decision = decide_grade(estimate, target, levels)
        if decision.outcome is SessionOutcome.FAILED:
            if assigned is not None:
                break
            if decision.suggested_lower is not None:
                assigned = decision.suggested_lower
                break
            if target.rank == 1:
                break
            target = by_rank[target.rank - 1]
            continue
        assigned = target
        if decision.outcome is SessionOutcome.PASSED_CONFIDENT and decision.next_grade_unlocked:
            target = decision.next_grade_unlocked
            continue
        break
    return assigned, sessions


def _claimed_rank(true_rank: int, rng: Random, max_rank: int) -> int:
    """Заявленный грейд: чаще совпадает с истинным, иногда завышен, реже занижен."""
    roll = rng.random()
    if roll < 0.6:
        return true_rank
    if roll < 0.85:
        return min(max_rank, true_rank + 1)
    return max(1, true_rank - 1)


def _kappa(first: Sequence[str], second: Sequence[str]) -> float:
    """Каппа Коэна согласия двух классификаций."""
    labels = sorted(set(first) | set(second))
    total = len(first)
    observed = sum(1 for a, b in zip(first, second, strict=True) if a == b) / total
    expected = sum((first.count(label) / total) * (second.count(label) / total) for label in labels)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def simulate_specialization(
    specialization: str,
    *,
    candidates: int = 400,
    seed: int = 2026,
    config: EngineConfig | None = None,
    noise_b: float = 0.3,
    noise_log_a: float = 0.15,
) -> SpecializationReport:
    """Прогоняет популяцию кандидатов через два независимых теста и считает метрики."""
    config = config or EngineConfig()
    rng = Random(seed)
    levels = load_levels()
    weights = load_blueprint(specialization)
    bank = build_bank({w.code for w in weights}, rng, noise_b, noise_log_a)
    all_skills = {slug for w in weights for slug in w.gate_skill_slugs}
    blueprint = build_blueprint(weights, all_skills, {f.item.competency for f in bank})
    by_rank = {level.rank: level for level in levels}
    max_rank = max(by_rank)

    thetas, estimates, retest_estimates = [], [], []
    decision_hits, retest_agreements = [], []
    true_grades, estimated_grades, retest_grades = [], [], []
    lengths, errors = [], []
    onboarding_truth, onboarding_result, onboarding_sessions = [], [], []
    tracker = ExposureTracker()

    for _ in range(candidates):
        theta_true = rng.gauss(0, 1)
        true_level = grade_for_theta(theta_true, levels) or levels[0]
        target = by_rank[_claimed_rank(true_level.rank, rng, max_rank)]

        first, administered = run_session(theta_true, bank, blueprint, target, rng, config, tracker)
        second, _ = run_session(
            theta_true, bank, blueprint, target, rng, config, tracker, set(administered)
        )

        truly_passes = theta_true >= target.theta_cut
        first_decision = decide_grade(first, target, levels).outcome is not SessionOutcome.FAILED
        second_decision = decide_grade(second, target, levels).outcome is not SessionOutcome.FAILED

        thetas.append(theta_true)
        estimates.append(first.theta)
        retest_estimates.append(second.theta)
        decision_hits.append(first_decision == truly_passes)
        retest_agreements.append(first_decision == second_decision)
        true_grades.append(true_level.code)
        estimated_grades.append((grade_for_theta(first.theta, levels) or levels[0]).code)
        retest_grades.append((grade_for_theta(second.theta, levels) or levels[0]).code)
        lengths.append(len(administered))
        errors.append(first.se)

        truth = grade_for_theta(theta_true, levels)
        assigned, used = simulate_onboarding(
            theta_true, target, levels, bank, blueprint, rng, config, tracker
        )
        onboarding_truth.append(truth.code if truth else "none")
        onboarding_result.append(assigned.code if assigned else "none")
        onboarding_sessions.append(used)

    theta_array, estimate_array = np.array(thetas), np.array(estimates)
    rank_of = {level.code: level.rank for level in levels}
    confusion: dict[str, dict[str, int]] = {
        level.code: dict.fromkeys(rank_of, 0) for level in levels
    }
    for true_code, guess_code in zip(true_grades, estimated_grades, strict=True):
        confusion[true_code][guess_code] += 1

    ranks = {"none": 0} | rank_of
    onboarding_confusion: dict[str, dict[str, int]] = {
        label: dict.fromkeys(ranks, 0) for label in ranks
    }
    for truth_label, result_label in zip(onboarding_truth, onboarding_result, strict=True):
        onboarding_confusion[truth_label][result_label] += 1
    pairs = list(zip(onboarding_truth, onboarding_result, strict=True))

    return SpecializationReport(
        specialization=specialization,
        candidates=candidates,
        bank_size=len(bank),
        theta_correlation=round(float(np.corrcoef(theta_array, estimate_array)[0, 1]), 3),
        theta_rmse=round(float(np.sqrt(np.mean((theta_array - estimate_array) ** 2))), 3),
        theta_bias=round(float(np.mean(estimate_array - theta_array)), 3),
        decision_accuracy=round(float(np.mean(decision_hits)), 3),
        grade_exact=round(
            float(np.mean([a == b for a, b in zip(true_grades, estimated_grades, strict=True)])), 3
        ),
        grade_within_one=round(
            float(
                np.mean(
                    [
                        abs(rank_of[a] - rank_of[b]) <= 1
                        for a, b in zip(true_grades, estimated_grades, strict=True)
                    ]
                )
            ),
            3,
        ),
        retest_decision_agreement=round(float(np.mean(retest_agreements)), 3),
        retest_grade_kappa=round(_kappa(estimated_grades, retest_grades), 3),
        retest_theta_correlation=round(
            float(np.corrcoef(estimate_array, np.array(retest_estimates))[0, 1]), 3
        ),
        mean_items=round(float(np.mean(lengths)), 2),
        mean_se=round(float(np.mean(errors)), 3),
        max_exposure_rate=round(max(tracker.rate(code) for code in tracker.shows), 3)
        if tracker.shows
        else 0.0,
        onboarding_exact=round(float(np.mean([a == b for a, b in pairs])), 3),
        onboarding_within_one=round(
            float(np.mean([abs(ranks[a] - ranks[b]) <= 1 for a, b in pairs])), 3
        ),
        onboarding_mean_sessions=round(float(np.mean(onboarding_sessions)), 2),
        confusion=confusion,
        onboarding_confusion=onboarding_confusion,
    )


def main() -> None:
    """CLI: прогоняет стенд по специализациям и сохраняет отчёт в docs/validation."""
    parser = argparse.ArgumentParser(description="Симуляция адаптивного тестирования «Скаута»")
    parser.add_argument("--candidates", type=int, default=400)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--specializations",
        nargs="*",
        default=["backend", "frontend", "data_analytics", "ml", "qa", "devops", "mobile"],
    )
    args = parser.parse_args()
    reports = [
        simulate_specialization(code, candidates=args.candidates, seed=args.seed + index)
        for index, code in enumerate(args.specializations)
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps([asdict(report) for report in reports], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for report in reports:
        print(
            f"{report.specialization:15} банк={report.bank_size:2} "
            f"r(θ)={report.theta_correlation:.3f} "
            f"RMSE={report.theta_rmse:.3f} решение={report.decision_accuracy:.1%} "
            f"грейд={report.grade_exact:.1%} (±1: {report.grade_within_one:.1%}) "
            f"ретест κ={report.retest_grade_kappa:.2f} r={report.retest_theta_correlation:.2f} "
            f"онбординг={report.onboarding_exact:.1%} (±1: {report.onboarding_within_one:.1%}) "
            f"заданий={report.mean_items:.1f} SE={report.mean_se:.2f} "
            f"экспозиция max={report.max_exposure_rate:.1%}"
        )
    print(f"Отчёт: {REPORT_PATH}")


if __name__ == "__main__":
    main()
