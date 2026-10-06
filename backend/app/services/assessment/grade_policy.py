from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models.assessment import SessionOutcome, SessionStatus


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    """Ограничения частоты тестов и смены грейда (см. ARCHITECTURE_AND_PLAN.md §2.3)."""

    grade_change_cooldown_days: int = 90
    upgrade_retry_days: int = 30
    onboarding_daily_sessions: int = 3
    confident_upgrade_window_hours: int = 24


@dataclass(frozen=True, slots=True)
class GradeInfo:
    """Грейд справочника."""

    grade_id: int
    code: str
    name: str
    rank: int


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Сведения о прошлой сессии, нужные политике."""

    status: SessionStatus
    target_rank: int
    outcome: SessionOutcome | None
    started_at: datetime
    finished_at: datetime | None
    rank_before: int | None


@dataclass(frozen=True, slots=True)
class GradeOption:
    """Можно ли сейчас пройти тест на грейд и почему."""

    grade: GradeInfo
    allowed: bool
    reason: str
    available_at: datetime | None = None


def evaluate_eligibility(
    *,
    grades: Sequence[GradeInfo],
    current_rank: int | None,
    last_change_at: datetime | None,
    sessions: Sequence[SessionSummary],
    now: datetime,
    config: PolicyConfig,
) -> list[GradeOption]:
    """Для каждого грейда решает, можно ли сейчас начать тест.

    Правила:
    * пока идёт сессия, новую начать нельзя;
    * до первой категории (онбординг) доступен любой грейд, но не больше N сессий
      за сутки: можно сразу сдать уровень ниже после неудачи;
    * после присвоения грейд меняется не чаще раза в 90 дней, тест на свой грейд
      не нужен, повышение идёт на одну ступень;
    * после уверенного прохождения уровень выше открывается сразу, без кулдауна;
    * неудачная попытка повышения грейд не снижает, но повтор — через 30 дней.
    """
    ordered = sorted(grades, key=lambda grade: grade.rank)
    if any(session.status is SessionStatus.IN_PROGRESS for session in sessions):
        return [GradeOption(grade, False, "Завершите начатый тест") for grade in ordered]

    if current_rank is None:
        return _onboarding_options(ordered, sessions, now, config)

    finished = sorted(
        (s for s in sessions if s.finished_at is not None and s.status is SessionStatus.COMPLETED),
        key=lambda s: s.finished_at or now,
    )
    latest = finished[-1] if finished else None
    confident_window = (
        latest is not None
        and latest.outcome is SessionOutcome.PASSED_CONFIDENT
        and latest.target_rank == current_rank
        and latest.finished_at is not None
        and now - latest.finished_at <= timedelta(hours=config.confident_upgrade_window_hours)
    )
    cooldown_until = (
        last_change_at + timedelta(days=config.grade_change_cooldown_days)
        if last_change_at
        else None
    )
    failed_upgrades = [
        s.finished_at
        for s in finished
        if s.outcome is SessionOutcome.FAILED
        and s.finished_at is not None
        and s.rank_before is not None
        and s.target_rank > s.rank_before
    ]
    retry_until = (
        max(failed_upgrades) + timedelta(days=config.upgrade_retry_days)
        if failed_upgrades
        else None
    )

    options: list[GradeOption] = []
    for grade in ordered:
        if grade.rank == current_rank:
            options.append(GradeOption(grade, False, "Это ваш текущий грейд"))
            continue
        if grade.rank > current_rank + 1:
            options.append(GradeOption(grade, False, "Повышение идёт на одну ступень за раз"))
            continue
        if grade.rank == current_rank + 1 and confident_window:
            options.append(GradeOption(grade, True, "Открыто после уверенного прохождения теста"))
            continue
        if cooldown_until and now < cooldown_until:
            options.append(
                GradeOption(
                    grade, False, "Грейд можно менять не чаще раза в 90 дней", cooldown_until
                )
            )
            continue
        if grade.rank > current_rank and retry_until and now < retry_until:
            options.append(
                GradeOption(
                    grade, False, "После неудачной попытки повтор — через 30 дней", retry_until
                )
            )
            continue
        reason = (
            "Тест на повышение грейда"
            if grade.rank > current_rank
            else "Тест на грейд ниже текущего"
        )
        options.append(GradeOption(grade, True, reason))
    return options


def _onboarding_options(
    grades: Sequence[GradeInfo],
    sessions: Sequence[SessionSummary],
    now: datetime,
    config: PolicyConfig,
) -> list[GradeOption]:
    """Онбординг: любой грейд, но ограниченное число сессий за скользящие сутки."""
    window_start = now - timedelta(hours=24)
    recent = sorted(s.started_at for s in sessions if s.started_at >= window_start)
    if len(recent) >= config.onboarding_daily_sessions:
        available_at = recent[0] + timedelta(hours=24)
        return [
            GradeOption(grade, False, "Лимит попыток на сегодня исчерпан", available_at)
            for grade in grades
        ]
    return [GradeOption(grade, True, "Выберите грейд, на который претендуете") for grade in grades]
