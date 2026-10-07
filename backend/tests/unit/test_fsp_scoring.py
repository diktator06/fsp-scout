import math
import uuid
from datetime import UTC, date, datetime

import pytest

from app.models.fsp import (
    FspAchievement,
    FspEventLevel,
    FspLink,
    FspParticipationFormat,
    FspResultStatus,
    FspState,
)
from app.services.fsp.achievements_scoring import (
    AchievementFact,
    counted,
    describe_result,
    recency_weight,
    score_achievements,
    summarize,
)
from app.services.fsp.standing import fsp_standing
from app.services.matching.explanations import explain_fsp
from app.services.matching.facts import CandidateFacts
from app.services.matching.verified_score import compute_verified_score

TODAY = date(2026, 10, 7)


def fact(
    result: FspResultStatus = FspResultStatus.PARTICIPANT,
    *,
    when: date = TODAY,
    online: bool = False,
    name: str = "Кубок",
) -> AchievementFact:
    """Участие для расчёта балла."""
    return AchievementFact(event_name=name, event_date=when, result_status=result, is_online=online)


def record(level: FspEventLevel, discipline: str, result: FspResultStatus) -> FspAchievement:
    """Запись реестра с заданным уровнем и дисциплиной."""
    return FspAchievement(
        candidate_id=uuid.uuid4(),
        external_event_id=str(uuid.uuid4()),
        event_name="Соревнование",
        event_level=level,
        discipline=discipline,
        event_date=TODAY,
        participation_format=FspParticipationFormat.INDIVIDUAL,
        result_status=result,
        is_online=False,
    )


def test_empty_history_gives_zero() -> None:
    """Нет участий — F = 0: отсутствие бонуса, а не ошибка."""
    score = score_achievements([], TODAY)
    assert score.value == 0
    assert score.best is None
    assert summarize(score) == "Участий в соревнованиях ФСП пока нет"


def test_formula_matches_definition() -> None:
    """F = min(1; 0,6·R + 0,4·N): одна свежая победа даёт R = 1/2 и N = 1 − e^(−1/3)."""
    score = score_achievements([fact(FspResultStatus.WINNER)], TODAY)
    activity = 1 - math.exp(-1 / 3)
    assert score.results == pytest.approx(0.5, abs=1e-4)
    assert score.activity == pytest.approx(activity, abs=1e-4)
    assert score.value == pytest.approx(0.6 * 0.5 + 0.4 * activity, abs=1e-4)


def test_stable_results_beat_single_luck() -> None:
    """Пять побед из пяти стартов весят больше, чем одна из одного, и F не больше 1."""
    one = score_achievements([fact(FspResultStatus.WINNER)], TODAY)
    five = score_achievements([fact(FspResultStatus.WINNER) for _ in range(5)], TODAY)
    many = score_achievements([fact(FspResultStatus.WINNER) for _ in range(200)], TODAY)
    assert five.value > one.value
    assert many.value <= 1


def test_results_order_and_finalist_half_credit() -> None:
    """Победа и призовое место равноценны, финал засчитывается наполовину, участие — активность."""
    winner = score_achievements([fact(FspResultStatus.WINNER)], TODAY)
    prize = score_achievements([fact(FspResultStatus.PRIZE)], TODAY)
    finalist = score_achievements([fact(FspResultStatus.FINALIST)], TODAY)
    participant = score_achievements([fact()], TODAY)
    assert winner.value == prize.value > finalist.value > participant.value > 0
    assert finalist.results == pytest.approx(0.25, abs=1e-4)


def test_no_discrimination_by_level_or_discipline() -> None:
    """Уровень соревнования и дисциплина на балл не влияют (рекомендация менторов)."""
    link = FspLink(candidate_id=uuid.uuid4(), participant_id="fsp-1")
    international = fsp_standing(
        link,
        [record(FspEventLevel.INTERNATIONAL, "алгоритмическое", FspResultStatus.PRIZE)],
        visible=True,
        today=TODAY,
    )
    local = fsp_standing(
        link,
        [record(FspEventLevel.LOCAL, "робототехника", FspResultStatus.PRIZE)],
        visible=True,
        today=TODAY,
    )
    assert international.score.value == local.score.value > 0


def test_online_attendance_cannot_be_farmed() -> None:
    """Онлайн-явки без результата дают убывающий вклад: десятки регистраций не заменят очное."""
    farmed = score_achievements([fact(online=True) for _ in range(50)], TODAY)
    offline = score_achievements([fact() for _ in range(3)], TODAY)
    assert farmed.results == 0
    assert farmed.effective_events <= 1.0
    assert farmed.value < offline.value
    with_attendance = score_achievements(
        [fact(FspResultStatus.WINNER)] + [fact(online=True) for _ in range(5)], TODAY
    )
    alone = score_achievements([fact(FspResultStatus.WINNER)], TODAY)
    assert with_attendance.results == alone.results
    assert with_attendance.value > alone.value


def test_recency_half_life_two_years() -> None:
    """Участие двухлетней давности весит вдвое меньше свежего."""
    assert recency_weight(date(2024, 10, 7), TODAY) == pytest.approx(0.5, abs=0.01)
    assert recency_weight(date(2027, 1, 1), TODAY) == 1.0
    fresh = score_achievements([fact(FspResultStatus.PRIZE)], TODAY)
    old = score_achievements([fact(FspResultStatus.PRIZE, when=date(2022, 10, 7))], TODAY)
    assert old.value < fresh.value


def test_three_states_and_hidden() -> None:
    """Не привязан, привязан без истории, привязан с участиями и скрыт — разные состояния."""
    link = FspLink(candidate_id=uuid.uuid4(), participant_id="fsp-2")
    item = record(FspEventLevel.REGIONAL, "продуктовое", FspResultStatus.WINNER)
    assert fsp_standing(None, [], visible=True, today=TODAY).state is FspState.NOT_LINKED
    assert fsp_standing(link, [], visible=True, today=TODAY).state is FspState.LINKED_EMPTY
    linked = fsp_standing(link, [item], visible=True, today=TODAY)
    assert linked.state is FspState.LINKED and linked.score.value > 0
    hidden = fsp_standing(link, [item], visible=False, today=TODAY)
    assert hidden.state is FspState.HIDDEN
    assert hidden.score.value == 0 and hidden.achievements == ()


def test_fsp_adds_up_to_fifteen_points_to_index() -> None:
    """Вес ФСП в индексе подтверждённого профиля — 15 баллов из 100."""
    facts = CandidateFacts(
        candidate_id=uuid.uuid4(),
        alias="A1B2",
        specialization_id=1,
        grade_id=1,
        grade_rank=1,
        confirmed=False,
    )
    now = datetime(2026, 10, 7, tzinfo=UTC)
    without = compute_verified_score(facts, [], (0.0, None), now)
    full = compute_verified_score(facts, [], (0.0, None), now, fsp=1.0)
    assert full.total - without.total == pytest.approx(15.0, abs=0.1)


def test_texts() -> None:
    """Склонения, описание результата, сводка и объяснения для всех состояний."""
    assert counted(1, "победа", "победы", "побед") == "1 победа"
    assert counted(3, "победа", "победы", "побед") == "3 победы"
    assert counted(11, "победа", "победы", "побед") == "11 побед"
    assert counted(22, "год", "года", "лет") == "22 года"
    prize = AchievementFact(
        event_name="Кубок России",
        event_date=date(2025, 5, 1),
        result_status=FspResultStatus.PRIZE,
        is_online=False,
        place=2,
        participants_total=140,
    )
    assert describe_result(prize) == "призёр (2 место из 140): Кубок России, 2025"
    score = score_achievements([prize, fact(when=date(2026, 3, 1))], TODAY)
    assert summarize(score) == "2 соревнования за 2 года, 1 призовое место"

    facts = CandidateFacts(
        candidate_id=uuid.uuid4(),
        alias="A1B2",
        specialization_id=1,
        grade_id=1,
        grade_rank=1,
        confirmed=True,
    )
    assert "не привязан" in explain_fsp(facts).text
    facts.fsp_state = FspState.LINKED_EMPTY
    assert "участий пока нет" in explain_fsp(facts).text
    facts.fsp_state = FspState.HIDDEN
    assert "скрыты" in explain_fsp(facts).text
    facts.fsp_state = FspState.LINKED
    facts.fsp_summary = "1 соревнование в 2026 году, без призовых мест"
    assert explain_fsp(facts).kind == "info"
    facts.fsp_best = describe_result(prize)
    item = explain_fsp(facts)
    assert item.kind == "plus" and item.text.startswith("ФСП: призёр")
