from collections.abc import Sequence
from dataclasses import dataclass

from app.models.assessment import SessionOutcome
from app.services.assessment.irt import AbilityEstimate

CONFIDENT_Z = 1.64
LOWER_GRADE_Z = 1.0


@dataclass(frozen=True, slots=True)
class GradeLevel:
    """Грейд на шкале способностей: ранг и порог θ категории."""

    grade_id: int
    code: str
    rank: int
    theta_cut: float


@dataclass(frozen=True, slots=True)
class GradeDecision:
    """Итог теста и предложения кандидату."""

    outcome: SessionOutcome
    suggested_lower: GradeLevel | None
    next_grade_unlocked: GradeLevel | None


def decide_grade(
    estimate: AbilityEstimate, target: GradeLevel, levels: Sequence[GradeLevel]
) -> GradeDecision:
    """Решение по заявленному грейду.

    * `passed_confident`: нижняя граница 90 % интервала выше порога следующего грейда.
      Кандидату сразу открывается тест на уровень выше.
    * `passed`: оценка θ не ниже порога заявленного грейда.
    * `failed`: грейд не подтверждён. Принудительно ничего не понижаем, но если
      оценка уверенно (θ − SE) выше порога одного из нижних грейдов, предлагаем
      принять его без пересдачи.
    """
    ordered = sorted(levels, key=lambda level: level.rank)
    higher = [level for level in ordered if level.rank > target.rank]
    next_level = higher[0] if higher else None

    if estimate.theta >= target.theta_cut:
        confident = (
            next_level is not None
            and estimate.theta - CONFIDENT_Z * estimate.se >= next_level.theta_cut
        )
        return GradeDecision(
            outcome=SessionOutcome.PASSED_CONFIDENT if confident else SessionOutcome.PASSED,
            suggested_lower=None,
            next_grade_unlocked=next_level if confident else None,
        )

    lower = [
        level
        for level in ordered
        if level.rank < target.rank
        and estimate.theta - LOWER_GRADE_Z * estimate.se >= level.theta_cut
    ]
    return GradeDecision(
        outcome=SessionOutcome.FAILED,
        suggested_lower=lower[-1] if lower else None,
        next_grade_unlocked=None,
    )


def grade_for_theta(theta: float, levels: Sequence[GradeLevel]) -> GradeLevel | None:
    """Наивысший грейд, порог которого не выше θ (для валидации и шкалы в интерфейсе)."""
    passed = [
        level for level in sorted(levels, key=lambda level: level.rank) if theta >= level.theta_cut
    ]
    return passed[-1] if passed else None
