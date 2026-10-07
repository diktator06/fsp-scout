import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.models.fsp import FspResultStatus

RESULT_CREDIT = {
    FspResultStatus.WINNER: 1.0,
    FspResultStatus.PRIZE: 1.0,
    FspResultStatus.FINALIST: 0.5,
    FspResultStatus.PARTICIPANT: 0.0,
}
RESULT_ORDER = {
    FspResultStatus.WINNER: 0,
    FspResultStatus.PRIZE: 1,
    FspResultStatus.FINALIST: 2,
    FspResultStatus.PARTICIPANT: 3,
}
RESULT_LABELS = {
    FspResultStatus.WINNER: "победитель",
    FspResultStatus.PRIZE: "призёр",
    FspResultStatus.FINALIST: "финалист",
    FspResultStatus.PARTICIPANT: "участник",
}
RESULTS_WEIGHT = 0.6
ACTIVITY_WEIGHT = 0.4
RESULTS_PRIOR = 1.0
ACTIVITY_SATURATION = 3.0
ONLINE_ATTENDANCE_BASE = 0.3
ONLINE_ATTENDANCE_DECAY = 0.7
RECENCY_HALF_LIFE_MONTHS = 24.0
DAYS_PER_MONTH = 30.44


@dataclass(frozen=True, slots=True)
class AchievementFact:
    """Участие в соревновании так, как его видит балл ФСП."""

    event_name: str
    event_date: date
    result_status: FspResultStatus
    is_online: bool
    place: int | None = None
    participants_total: int | None = None


@dataclass(frozen=True, slots=True)
class FspScore:
    """Балл ФСП F (0..1) и его составляющие для объяснения кандидату и работодателю."""

    value: float
    results: float
    activity: float
    effective_events: float
    events: int
    wins: int
    prizes: int
    finals: int
    online_attendance: int
    best: AchievementFact | None
    first_event: date | None
    last_event: date | None


EMPTY_SCORE = FspScore(
    value=0.0,
    results=0.0,
    activity=0.0,
    effective_events=0.0,
    events=0,
    wins=0,
    prizes=0,
    finals=0,
    online_attendance=0,
    best=None,
    first_event=None,
    last_event=None,
)


def recency_weight(event_date: date, today: date) -> float:
    """Вес участия по давности: полураспад 24 месяца, будущие даты весят как сегодняшние."""
    months = max(0, (today - event_date).days) / DAYS_PER_MONTH
    return float(0.5 ** (months / RECENCY_HALF_LIFE_MONTHS))


def is_online_attendance(item: AchievementFact) -> bool:
    """Онлайн-участие без результата — «явка», которую легко набить регистрациями."""
    return item.is_online and RESULT_CREDIT[item.result_status] == 0.0


def best_result(items: Sequence[AchievementFact]) -> AchievementFact | None:
    """Лучший результат: сначала по статусу, при равенстве — более свежий."""
    if not items:
        return None
    return min(
        items, key=lambda item: (RESULT_ORDER[item.result_status], -item.event_date.toordinal())
    )


def score_achievements(items: Sequence[AchievementFact], today: date) -> FspScore:
    """Балл ФСП: F = min(1; 0,6·R + 0,4·N).

    R — результативность: Σ w·c / (Σ w + 1), где c = 1 за победу или призовое место,
    0,5 за финал и 0 за участие, а w — вес давности. Единица в знаменателе — априорное
    «участие без результата»: одна победа из одного старта даёт R = 0,5, а пять из
    пяти — 0,83, поэтому случайный единичный успех не равен стабильному.

    N — активность: 1 − exp(−M/3), где M — взвешенное по давности число участий.
    Онлайн-явки без результата не входят в R и добавляют в M убывающий вклад
    0,3 · 0,7^i: профиль нельзя «набить» регистрациями.

    Уровень соревнования и дисциплина на балл не влияют (рекомендация менторов ФСП):
    все соревнования равноценны. Вклад участника в командный результат не выделяется,
    потому что реестр его не фиксирует.
    """
    if not items:
        return EMPTY_SCORE
    weighted_credit = 0.0
    weighted_events = 0.0
    effective = 0.0
    attendance = sorted(
        (item for item in items if is_online_attendance(item)),
        key=lambda item: item.event_date,
        reverse=True,
    )
    for item in items:
        if is_online_attendance(item):
            continue
        weight = recency_weight(item.event_date, today)
        weighted_credit += weight * RESULT_CREDIT[item.result_status]
        weighted_events += weight
        effective += weight
    for index, item in enumerate(attendance):
        effective += (
            ONLINE_ATTENDANCE_BASE
            * ONLINE_ATTENDANCE_DECAY**index
            * recency_weight(item.event_date, today)
        )
    results = weighted_credit / (weighted_events + RESULTS_PRIOR)
    activity = 1.0 - math.exp(-effective / ACTIVITY_SATURATION)
    value = min(1.0, RESULTS_WEIGHT * results + ACTIVITY_WEIGHT * activity)
    dates = [item.event_date for item in items]
    return FspScore(
        value=round(value, 4),
        results=round(results, 4),
        activity=round(activity, 4),
        effective_events=round(effective, 2),
        events=len(items),
        wins=sum(1 for item in items if item.result_status is FspResultStatus.WINNER),
        prizes=sum(1 for item in items if item.result_status is FspResultStatus.PRIZE),
        finals=sum(1 for item in items if item.result_status is FspResultStatus.FINALIST),
        online_attendance=len(attendance),
        best=best_result(items),
        first_event=min(dates),
        last_event=max(dates),
    )


def counted(count: int, one: str, few: str, many: str) -> str:
    """Число с существительным в нужной форме: 1 победа, 3 победы, 5 побед."""
    tail = count % 100
    if 11 <= tail <= 14:
        noun = many
    elif count % 10 == 1:
        noun = one
    elif 2 <= count % 10 <= 4:
        noun = few
    else:
        noun = many
    return f"{count} {noun}"


def describe_result(item: AchievementFact) -> str:
    """Результат одной строкой: «призёр (2 место из 140): Кубок …, 2025»."""
    label = RESULT_LABELS[item.result_status]
    if item.place is not None and item.result_status is not FspResultStatus.PARTICIPANT:
        total = f" из {item.participants_total}" if item.participants_total else ""
        label = f"{label} ({item.place} место{total})"
    return f"{label}: {item.event_name}, {item.event_date.year}"


def summarize(score: FspScore) -> str:
    """Сводка для карточки: «4 соревнования за 2 года, 1 призовое место, 1 финал»."""
    if score.events == 0 or score.first_event is None or score.last_event is None:
        return "Участий в соревнованиях ФСП пока нет"
    events = counted(score.events, "соревнование", "соревнования", "соревнований")
    years = score.last_event.year - score.first_event.year + 1
    period = (
        f"в {score.last_event.year} году"
        if years == 1
        else f"за {counted(years, 'год', 'года', 'лет')}"
    )
    parts = [f"{events} {period}"]
    if score.wins:
        parts.append(counted(score.wins, "победа", "победы", "побед"))
    if score.prizes:
        parts.append(counted(score.prizes, "призовое место", "призовых места", "призовых мест"))
    if score.finals:
        parts.append(counted(score.finals, "финал", "финала", "финалов"))
    if not (score.wins or score.prizes or score.finals):
        parts.append("без призовых мест")
    return ", ".join(parts)
