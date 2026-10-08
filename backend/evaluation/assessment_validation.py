import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from random import Random
from statistics import mean, median
from typing import Any

import numpy as np

from app.models.assessment import SessionOutcome
from app.services.assessment.adaptive_engine import EngineConfig
from app.services.assessment.blueprint import build_blueprint
from app.services.assessment.grading import GradeLevel, decide_grade, grade_for_theta
from app.services.assessment.irt import (
    ItemParameters,
    estimate_ability,
    estimate_ability_wle,
    information,
    simulate_response,
)
from evaluation.integrity import person_fit, preknowledge
from evaluation.simulate_assessment import (
    ExposureTracker,
    Responder,
    SimulatedFamily,
    build_bank,
    claimed_rank,
    cohen_kappa,
    load_blueprint,
    load_levels,
    run_session,
    weighted_kappa,
)

REPORT_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "validation" / "assessment_validation.json"
)
SPECIALIZATIONS = ("backend", "frontend", "data_analytics", "ml", "qa", "devops", "mobile")
GRADE_SHARES = {1: 0.12, 2: 0.28, 3: 0.38, 4: 0.22}
TOP_BAND = 1.1
LEAK_BUDGETS = (4, 8, 12)
TEMPLATE_ADVANTAGES = (0.3, 0.6, 1.0)
MAIN_BUDGET = 8
MAIN_ADVANTAGE = 0.6
FIXED_TEST_LENGTH = 16
FALSE_POSITIVE_RATE = 0.05
EXPOSED_SHARE = 0.2
MIN_EXPOSED_FAMILIES = 3
MIN_ADMINISTRATIONS = 30
ACCEPTABLE_POINT_BISERIAL = 0.2
NOISE_B = 0.3
NOISE_LOG_A = 0.15


@dataclass(frozen=True, slots=True)
class Stand:
    """Банк специализации и blueprint — как в продукте, с шумом «истинных» параметров."""

    bank: list[SimulatedFamily]
    blueprint: dict[str, float]
    levels: list[GradeLevel]


def build_stand(specialization: str, rng: Random) -> Stand:
    """Банк и blueprint специализации."""
    weights = load_blueprint(specialization)
    bank = build_bank({weight.code for weight in weights}, rng, NOISE_B, NOISE_LOG_A)
    skills = {slug for weight in weights for slug in weight.gate_skill_slugs}
    blueprint = build_blueprint(weights, skills, {family.item.competency for family in bank})
    return Stand(bank=bank, blueprint=blueprint, levels=load_levels())


def graded_theta(rng: Random, levels: Sequence[GradeLevel], max_rank: int = 4) -> float:
    """Способность в реалистичной популяции: доли грейдов 12/28/38/22 %, внутри — равномерно."""
    shares = {rank: share for rank, share in GRADE_SHARES.items() if rank <= max_rank}
    rank = rng.choices(list(shares), weights=list(shares.values()))[0]
    by_rank = {level.rank: level for level in levels}
    cut = by_rank[rank].theta_cut
    upper = by_rank[rank + 1].theta_cut if rank + 1 in by_rank else cut + TOP_BAND
    return rng.uniform(cut + 0.05, upper - 0.05)


def auc(positives: Sequence[float], negatives: Sequence[float]) -> float:
    """Площадь под ROC-кривой: вероятность, что случайный «сильный» оценён выше «слабого»."""
    if not positives or not negatives:
        return 0.0
    pos = np.asarray(positives)
    neg = np.asarray(negatives)
    greater = (pos[:, None] > neg[None, :]).mean()
    ties = (pos[:, None] == neg[None, :]).mean()
    return float(greater + 0.5 * ties)


def _rank(theta: float, levels: Sequence[GradeLevel]) -> int:
    """Грейд по θ: 0 — ниже первого порога."""
    level = grade_for_theta(theta, levels)
    return level.rank if level else 0


def compare_estimators(
    specialization: str, population: str, candidates: int, seed: int
) -> dict[str, Any]:
    """EAP против WLE на одних и тех же ответах: смещение по грейдам, точность и повтор."""
    rng = Random(seed)
    stand = build_stand(specialization, rng)
    by_rank = {level.rank: level for level in stand.levels}
    config = EngineConfig()
    tracker = ExposureTracker()
    results: dict[str, dict[str, list[Any]]] = {name: defaultdict(list) for name in ("eap", "wle")}
    for _ in range(candidates):
        theta = rng.gauss(0, 1) if population == "normal" else graded_theta(rng, stand.levels)
        true_rank = max(1, _rank(theta, stand.levels))
        target = by_rank[claimed_rank(true_rank, rng, max(by_rank))]
        first = run_session(theta, stand.bank, stand.blueprint, target, rng, config, tracker)
        second = run_session(
            theta,
            stand.bank,
            stand.blueprint,
            target,
            rng,
            config,
            tracker,
            set(first.administered),
        )
        for name, estimator in (("eap", estimate_ability), ("wle", estimate_ability_wle)):
            one, two = estimator(first.responses), estimator(second.responses)
            bucket = results[name]
            bucket["true"].append(true_rank)
            bucket["first"].append(max(1, _rank(one.theta, stand.levels)))
            bucket["second"].append(max(1, _rank(two.theta, stand.levels)))
            bucket[f"bias_{true_rank}"].append(one.theta - theta)
            passed = decide_grade(one, target, stand.levels).outcome is not SessionOutcome.FAILED
            bucket["decision"].append(passed == (theta >= target.theta_cut))
    report: dict[str, Any] = {}
    for name, bucket in results.items():
        pairs = list(zip(bucket["true"], bucket["first"], strict=True))
        report[name] = {
            "grade_exact": round(mean(1.0 if a == b else 0.0 for a, b in pairs), 3),
            "grade_within_one": round(mean(1.0 if abs(a - b) <= 1 else 0.0 for a, b in pairs), 3),
            "decision_accuracy": round(mean(1.0 if hit else 0.0 for hit in bucket["decision"]), 3),
            "retest_kappa": round(
                cohen_kappa([str(x) for x in bucket["first"]], [str(x) for x in bucket["second"]]),
                3,
            ),
            "retest_kappa_weighted": round(
                weighted_kappa(bucket["first"], bucket["second"], len(stand.levels)), 3
            ),
            "bias_by_true_grade": {
                stand.levels[rank - 1].code: round(mean(bucket[f"bias_{rank}"]), 3)
                for rank in by_rank
                if bucket[f"bias_{rank}"]
            },
        }
    return report


def discrimination(specialization: str, candidates: int, seed: int) -> dict[str, Any]:
    """Разделяющая сила: параметры банка, корреляция заданий с θ̂ и AUC по порогам грейдов."""
    rng = Random(seed)
    stand = build_stand(specialization, rng)
    by_rank = {level.rank: level for level in stand.levels}
    config = EngineConfig()
    tracker = ExposureTracker()
    per_family: dict[str, list[tuple[float, float]]] = defaultdict(list)
    estimates: list[tuple[float, float, int]] = []
    for _ in range(candidates):
        theta = graded_theta(rng, stand.levels)
        true_rank = max(1, _rank(theta, stand.levels))
        target = by_rank[claimed_rank(true_rank, rng, max(by_rank))]
        run = run_session(theta, stand.bank, stand.blueprint, target, rng, config, tracker)
        for code, (_, score) in zip(run.administered, run.responses, strict=True):
            per_family[code].append((score, run.estimate.theta))
        estimates.append((theta, run.estimate.theta, true_rank))
    correlations = {}
    for code, values in per_family.items():
        scores = np.array([score for score, _ in values])
        thetas = np.array([estimate for _, estimate in values])
        if len(values) >= MIN_ADMINISTRATIONS and scores.std() > 0 and thetas.std() > 0:
            correlations[code] = float(np.corrcoef(scores, thetas)[0, 1])
    discriminations = [family.item.params.a for family in stand.bank]
    weakest = sorted(correlations.items(), key=lambda item: item[1])[:3]
    ordered = sorted(estimates, key=lambda item: item[0])
    third = len(ordered) // 3
    return {
        "bank_size": len(stand.bank),
        "a_median": round(median(discriminations), 3),
        "a_share_at_least_0_8": round(mean(1.0 if a >= 0.8 else 0.0 for a in discriminations), 3),
        "point_biserial_median": round(median(correlations.values()), 3) if correlations else None,
        "point_biserial_acceptable_share": round(
            mean(
                1.0 if value >= ACCEPTABLE_POINT_BISERIAL else 0.0
                for value in correlations.values()
            ),
            3,
        )
        if correlations
        else None,
        "families_measured": len(correlations),
        "weakest_families": [{"family": code, "r_pb": round(value, 3)} for code, value in weakest],
        "auc_by_cut": {
            level.code: round(
                auc(
                    [estimate for _, estimate, rank in estimates if rank >= level.rank],
                    [estimate for _, estimate, rank in estimates if rank < level.rank],
                ),
                3,
            )
            for level in stand.levels
            if level.rank > 1
        },
        "auc_strong_vs_weak": round(
            auc(
                [estimate for _, estimate, _ in ordered[-third:]],
                [estimate for _, estimate, _ in ordered[:third]],
            ),
            3,
        ),
    }


def _fixed_items(stand: Stand, target: GradeLevel) -> list[SimulatedFamily]:
    """Единый тест на грейд: одни и те же самые информативные у порога задания для всех."""
    ranked = sorted(
        stand.bank,
        key=lambda family: information(target.theta_cut, family.item.params),
        reverse=True,
    )
    return ranked[:FIXED_TEST_LENGTH]


def _fixed_session(
    items: Sequence[SimulatedFamily], theta: float, rng: Random, leaked: set[str]
) -> list[tuple[ItemParameters, float]]:
    """Прохождение единого теста: утёкшие задания решены наверняка — ответ известен целиком."""
    return [
        (
            family.item.params,
            1.0
            if family.item.code in leaked
            else simulate_response(theta, family.true_params, rng.random()),
        )
        for family in items
    ]


def _template_responder(theta: float, leaked: set[str], advantage: float) -> Responder:
    """Кандидат, знающий шаблоны утёкших семейств, но не ответы на новый экземпляр.

    Экземпляр каждый раз новый (другие числа, данные, варианты), поэтому знание
    шаблона не даёт ответ, а лишь повышает шанс: P' = P + β·(1 − P). β = 1 — худший
    случай, когда шаблон равносилен ответу.
    """

    def respond(family: SimulatedFamily, uniform: float) -> float:
        """Ответ с учётом знания шаблона."""
        logistic = 1.0 / (1.0 + np.exp(-family.true_params.a * (theta - family.true_params.b)))
        probability = family.true_params.c + (1.0 - family.true_params.c) * float(logistic)
        if family.item.code in leaked:
            probability += advantage * (1.0 - probability)
        return 1.0 if uniform < probability else 0.0

    return respond


@dataclass
class LeakArm:
    """Одна группа сценария утечки: доля «повышенных» грейдов и статистики честности."""

    inflated: list[float]
    fits: list[float]
    preknowledge: list[float] | None = None

    def summary(self) -> dict[str, Any]:
        """Сводка группы."""
        return {"inflation_rate": round(mean(self.inflated), 3) if self.inflated else 0.0}


def leak_resistance(specialization: str, candidates: int, seed: int) -> dict[str, Any]:
    """Утечки заданий: насколько они помогают получить грейд выше истинного.

    Все кандидаты целятся на грейд выше своего (мотив списывать). Сравниваются:
    единый тест (утекают точные ответы его заданий) и адаптивный тест «Скаута»
    (утекают шаблоны самых показываемых семейств — худший для нас случай). Бюджет
    утечки одинаковый — столько-то заданий или семейств.
    """
    rng = Random(seed)
    stand = build_stand(specialization, rng)
    by_rank = {level.rank: level for level in stand.levels}
    config = EngineConfig()
    tracker = ExposureTracker()
    population = [graded_theta(rng, stand.levels, max_rank=3) for _ in range(candidates)]

    honest_cat = LeakArm([], [], [])
    honest_fixed = LeakArm([], [])
    honest_runs = []
    for theta in population:
        target = by_rank[max(1, _rank(theta, stand.levels)) + 1]
        run = run_session(theta, stand.bank, stand.blueprint, target, rng, config, tracker)
        honest_runs.append(run)
        passed = decide_grade(run.estimate, target, stand.levels).outcome
        honest_cat.inflated.append(0.0 if passed is SessionOutcome.FAILED else 1.0)
        fit = person_fit(run.responses, run.estimate.theta)
        if fit is not None:
            honest_cat.fits.append(fit)
        responses = _fixed_session(_fixed_items(stand, target), theta, rng, set())
        estimate = estimate_ability_wle(responses)
        outcome = decide_grade(estimate, target, stand.levels).outcome
        honest_fixed.inflated.append(0.0 if outcome is SessionOutcome.FAILED else 1.0)
        fit = person_fit(responses, estimate.theta)
        if fit is not None:
            honest_fixed.fits.append(fit)

    most_exposed = [code for code, _ in tracker.shows.most_common()]
    exposed = set(most_exposed[: max(MIN_EXPOSED_FAMILIES, round(EXPOSED_SHARE * len(stand.bank)))])
    for run in honest_runs:
        statistic = preknowledge(run.administered, run.responses, exposed)
        if statistic is not None and honest_cat.preknowledge is not None:
            honest_cat.preknowledge.append(statistic)
    scenarios: list[dict[str, Any]] = []
    cheaters: dict[str, LeakArm] = {}
    for budget in LEAK_BUDGETS:
        advantages = TEMPLATE_ADVANTAGES if budget == MAIN_BUDGET else (MAIN_ADVANTAGE,)
        leaked_families = set(most_exposed[:budget])
        fixed_arm = LeakArm([], [])
        for theta in population:
            target = by_rank[max(1, _rank(theta, stand.levels)) + 1]
            items = _fixed_items(stand, target)
            leaked_items = {family.item.code for family in items[:budget]}
            responses = _fixed_session(items, theta, rng, leaked_items)
            estimate = estimate_ability_wle(responses)
            outcome = decide_grade(estimate, target, stand.levels).outcome
            fixed_arm.inflated.append(0.0 if outcome is SessionOutcome.FAILED else 1.0)
            fit = person_fit(responses, estimate.theta)
            if fit is not None:
                fixed_arm.fits.append(fit)
        for advantage in advantages:
            cat_arm = LeakArm([], [], [])
            for theta in population:
                target = by_rank[max(1, _rank(theta, stand.levels)) + 1]
                run = run_session(
                    theta,
                    stand.bank,
                    stand.blueprint,
                    target,
                    rng,
                    config,
                    ExposureTracker(),
                    responder=_template_responder(theta, leaked_families, advantage),
                )
                outcome = decide_grade(run.estimate, target, stand.levels).outcome
                cat_arm.inflated.append(0.0 if outcome is SessionOutcome.FAILED else 1.0)
                fit = person_fit(run.responses, run.estimate.theta)
                if fit is not None:
                    cat_arm.fits.append(fit)
                statistic = preknowledge(run.administered, run.responses, exposed)
                if statistic is not None and cat_arm.preknowledge is not None:
                    cat_arm.preknowledge.append(statistic)
            scenarios.append(
                {
                    "budget": budget,
                    "template_advantage": advantage,
                    "fixed_test": fixed_arm.summary(),
                    "scout_cat": cat_arm.summary(),
                }
            )
            if budget == MAIN_BUDGET and advantage == MAIN_ADVANTAGE:
                cheaters = {"scout_cat": cat_arm, "fixed_test": fixed_arm}
    return {
        "candidates": candidates,
        "bank_size": len(stand.bank),
        "fixed_test_length": FIXED_TEST_LENGTH,
        "honest": {"scout_cat": honest_cat.summary(), "fixed_test": honest_fixed.summary()},
        "scenarios": scenarios,
        "_fits": {
            "honest_cat": honest_cat.fits,
            "honest_fixed": honest_fixed.fits,
            "cheater_cat": cheaters["scout_cat"].fits if cheaters else [],
            "cheater_fixed": cheaters["fixed_test"].fits if cheaters else [],
            "honest_preknowledge": honest_cat.preknowledge or [],
            "cheater_preknowledge": (cheaters["scout_cat"].preknowledge or []) if cheaters else [],
        },
    }


def person_fit_summary(leaks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Сила двух статистических детекторов списывания при 5 % ложных срабатываний.

    Для l_z порог — 5-й процентиль честных кандидатов (подозрительны малые значения),
    для статистики предзнания — 95-й (подозрительны большие).
    """
    pooled: dict[str, list[float]] = defaultdict(list)
    for report in leaks.values():
        for key, values in report.pop("_fits").items():
            pooled[key].extend(values)
    threshold = float(np.percentile(pooled["honest_cat"], 100 * FALSE_POSITIVE_RATE))

    def caught(values: Sequence[float], limit: float) -> float:
        """Доля сессий с индексом ниже порога."""
        return round(mean(1.0 if value < limit else 0.0 for value in values), 3) if values else 0.0

    fixed_threshold = float(np.percentile(pooled["honest_fixed"], 100 * FALSE_POSITIVE_RATE))
    knowledge_threshold = float(
        np.percentile(pooled["honest_preknowledge"], 100 * (1 - FALSE_POSITIVE_RATE))
    )
    return {
        "threshold": round(threshold, 2),
        "false_positive_rate": caught(pooled["honest_cat"], threshold),
        "recall_cat_cheaters": caught(pooled["cheater_cat"], threshold),
        "auc_cat": round(
            auc(
                [-value for value in pooled["cheater_cat"]],
                [-value for value in pooled["honest_cat"]],
            ),
            3,
        ),
        "fixed_test_threshold": round(fixed_threshold, 2),
        "recall_fixed_cheaters": caught(pooled["cheater_fixed"], fixed_threshold),
        "auc_fixed": round(
            auc(
                [-value for value in pooled["cheater_fixed"]],
                [-value for value in pooled["honest_fixed"]],
            ),
            3,
        ),
        "preknowledge_threshold": round(knowledge_threshold, 2),
        "preknowledge_recall": round(
            mean(
                1.0 if value > knowledge_threshold else 0.0
                for value in pooled["cheater_preknowledge"]
            ),
            3,
        ),
        "preknowledge_auc": round(
            auc(pooled["cheater_preknowledge"], pooled["honest_preknowledge"]), 3
        ),
        "scenario": {"budget": MAIN_BUDGET, "template_advantage": MAIN_ADVANTAGE},
    }


def pooled_leaks(leaks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Средние по специализациям доли «повышенных» грейдов в каждом сценарии утечки."""
    keys = [
        (scenario["budget"], scenario["template_advantage"])
        for scenario in next(iter(leaks.values()))["scenarios"]
    ]
    rows = []
    for budget, advantage in keys:
        matching = [
            scenario
            for report in leaks.values()
            for scenario in report["scenarios"]
            if (scenario["budget"], scenario["template_advantage"]) == (budget, advantage)
        ]
        rows.append(
            {
                "budget": budget,
                "template_advantage": advantage,
                "fixed_test_inflation": round(
                    mean(item["fixed_test"]["inflation_rate"] for item in matching), 3
                ),
                "scout_cat_inflation": round(
                    mean(item["scout_cat"]["inflation_rate"] for item in matching), 3
                ),
            }
        )
    return rows


def run(candidates: int, seed: int) -> dict[str, Any]:
    """Все проверки по всем специализациям."""
    estimators = {
        code: {
            population: compare_estimators(code, population, candidates, seed + index)
            for population in ("normal", "graded")
        }
        for index, code in enumerate(SPECIALIZATIONS)
    }
    discriminations = {
        code: discrimination(code, candidates, seed + 50 + index)
        for index, code in enumerate(SPECIALIZATIONS)
    }
    leaks = {
        code: leak_resistance(code, candidates, seed + 80 + index)
        for index, code in enumerate(SPECIALIZATIONS)
    }
    fit = person_fit_summary(leaks)
    honest = {
        "scout_cat": round(
            mean(report["honest"]["scout_cat"]["inflation_rate"] for report in leaks.values()), 3
        ),
        "fixed_test": round(
            mean(report["honest"]["fixed_test"]["inflation_rate"] for report in leaks.values()), 3
        ),
    }
    return {
        "candidates_per_specialization": candidates,
        "seed": seed,
        "estimators": estimators,
        "discrimination": discriminations,
        "leaks": {"honest": honest, "pooled": pooled_leaks(leaks), "by_specialization": leaks},
        "person_fit": fit,
    }


def _bias_line(report: dict[str, Any], name: str) -> str:
    """Смещение по грейдам одной строкой."""
    return " ".join(
        f"{code}:{value:+.2f}" for code, value in report[name]["bias_by_true_grade"].items()
    )


def main() -> None:
    """CLI: считает проверки и сохраняет отчёт в docs/validation."""
    parser = argparse.ArgumentParser(description="Валидация механики тестирования «Скаута»")
    parser.add_argument("--candidates", type=int, default=300)
    parser.add_argument("--seed", type=int, default=3030)
    parser.add_argument("--output", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    report = run(args.candidates, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    for code, populations in report["estimators"].items():
        graded = populations["graded"]
        eap, wle = graded["eap"], graded["wle"]
        print(
            f"{code:15} EAP: точно {eap['grade_exact']:.3f} [{_bias_line(graded, 'eap')}] | "
            f"WLE: точно {wle['grade_exact']:.3f} [{_bias_line(graded, 'wle')}] "
            f"κw {wle['retest_kappa_weighted']:.2f}"
        )
    for code, values in report["discrimination"].items():
        print(
            f"{code:15} a̅={values['a_median']} r_pb={values['point_biserial_median']} "
            f"AUC сильные/слабые={values['auc_strong_vs_weak']} по порогам={values['auc_by_cut']}"
        )
    print("Честные (доля грейдов выше истинного):", report["leaks"]["honest"])
    for row in report["leaks"]["pooled"]:
        print(row)
    print("Индекс согласованности:", report["person_fit"])
    print(f"Отчёт: {args.output}")


if __name__ == "__main__":
    main()
