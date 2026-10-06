from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models.assessment import SessionOutcome, SessionStatus


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    """Ограничения частоты тестов и смены грейда (см. ARCHITECTURE_AND_PLAN.md §2.3)."""

    grade_change_cooldown_days: int = 90
    upgrade_retry_days: int = 30
    onboarding_retry_hours: int = 24
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
    * до первой категории (онбординг) доступен любой грейд. После неудачи уровень
      ниже открыт сразу и попыткой не считается («провал и уход ниже — без
      сжигания попытки»), а повтор того же или более высокого — через сутки;
    * после присвоения грейд меняется не чаще раза в 90 дней, тест на свой грейд
      не нужен, повышение идёт на одну ступень;
    * после уверенного прохождения уровень выше открывается сразу, без кулдауна;
    * неудачная или прерванная попытка повышения грейд не снижает, но повтор —
      через 30 дней.
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
    unsuccessful = [s for s in sessions if _is_unsuccessful(s)]
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
        for s in unsuccessful
        if s.finished_at is not None and s.rank_before is not None and s.target_rank > s.rank_before
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


def _is_unsuccessful(session: SessionSummary) -> bool:
    """Попытка не удалась: тест провален, прерван или истёк по времени.

    Прерванный тест считается неудачей, иначе можно было бы бросать тест на трудных
    заданиях и начинать заново в надежде на более лёгкие.
    """
    if session.status is SessionStatus.COMPLETED:
        return session.outcome is SessionOutcome.FAILED
    return session.status in {SessionStatus.ABANDONED, SessionStatus.EXPIRED}


def _onboarding_options(
    grades: Sequence[GradeInfo],
    sessions: Sequence[SessionSummary],
    now: datetime,
    config: PolicyConfig,
) -> list[GradeOption]:
    """Онбординг: любой грейд; после неудачи на g тест на g и выше — только через паузу.

    Тест ниже проваленного уровня открыт сразу и попыткой не считается. Пауза перед
    повтором того же уровня нужна, чтобы нельзя было перебором «вытянуть» удобный
    набор заданий.
    """
    retry = timedelta(hours=config.onboarding_retry_hours)
    blocked_until: dict[int, datetime] = {}
    for session in sessions:
        moment = session.finished_at or session.started_at
        if not _is_unsuccessful(session) or now >= moment + retry:
            continue
        for grade in grades:
            if grade.rank >= session.target_rank:
                previous = blocked_until.get(grade.rank)
                release = moment + retry
                blocked_until[grade.rank] = max(previous, release) if previous else release

    options = []
    for grade in grades:
        release_at = blocked_until.get(grade.rank)
        if release_at is not None:
            options.append(
                GradeOption(grade, False, "Повтор этого уровня — после паузы в сутки", release_at)
            )
        else:
            options.append(GradeOption(grade, True, "Выберите грейд, на который претендуете"))
    return options
