from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from app.models.fsp import FspAchievement, FspLink, FspState
from app.services.fsp.achievements_scoring import (
    EMPTY_SCORE,
    AchievementFact,
    FspScore,
    score_achievements,
)

FSP_MESSAGES = {
    FspState.NOT_LINKED: "Профиль ФСП не привязан — оценка основана на тесте и профиле",
    FspState.LINKED_EMPTY: (
        "ФСП ID привязан, участий в соревнованиях пока нет — оценка основана на тесте и профиле"
    ),
    FspState.LINKED: "Участия подтверждены реестром ФСП",
    FspState.HIDDEN: "Кандидат не показывает достижения ФСП — оценка основана на тесте и профиле",
}


@dataclass(frozen=True, slots=True)
class FspStanding:
    """Состояние ФСП кандидата, балл F и участия, которые можно показать."""

    state: FspState
    score: FspScore = EMPTY_SCORE
    link: FspLink | None = None
    achievements: tuple[FspAchievement, ...] = field(default=())

    @property
    def message(self) -> str:
        """Нейтральный текст состояния для карточки."""
        return FSP_MESSAGES[self.state]


NOT_LINKED = FspStanding(state=FspState.NOT_LINKED)


def achievement_fact(item: FspAchievement) -> AchievementFact:
    """Запись реестра в форме, нужной баллу."""
    return AchievementFact(
        event_name=item.event_name,
        event_date=item.event_date,
        result_status=item.result_status,
        is_online=item.is_online,
        place=item.place,
        participants_total=item.participants_total,
    )


def fsp_standing(
    link: FspLink | None,
    achievements: Sequence[FspAchievement],
    *,
    visible: bool,
    today: date,
) -> FspStanding:
    """Определяет одно из состояний ФСП и считает балл.

    Если кандидат скрыл достижения, работодатель не получает ни участий, ни балла:
    по порядку выдачи нельзя догадаться о том, что человек решил не показывать.
    """
    if link is None:
        return NOT_LINKED
    if not visible:
        return FspStanding(state=FspState.HIDDEN, link=link)
    if not achievements:
        return FspStanding(state=FspState.LINKED_EMPTY, link=link)
    return FspStanding(
        state=FspState.LINKED,
        score=score_achievements([achievement_fact(item) for item in achievements], today),
        link=link,
        achievements=tuple(achievements),
    )
