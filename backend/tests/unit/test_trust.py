from datetime import UTC, datetime

from app.core.inn import is_valid_inn
from app.crud.trust import ReputationCounts
from app.services.trust.reputation import build_reputation
from app.services.trust.salary_check import check_salary

SINCE = datetime(2026, 10, 1, tzinfo=UTC)


def test_inn_checksum() -> None:
    """Контрольные цифры ИНН организации и ИП; опечатка не проходит."""
    assert is_valid_inn("7707083893")
    assert is_valid_inn("500100732259")
    assert not is_valid_inn("7707083894")
    assert not is_valid_inn("77070838")
    assert not is_valid_inn("77070838931")


def test_salary_check_statuses() -> None:
    """Ниже рынка, в рынке, в разы выше рынка и «мало данных»."""
    market = [200_000, 250_000, 300_000]
    assert check_salary(220_000, 300_000, True, market).status == "ok"
    assert check_salary(90_000, 140_000, True, market).status == "below_market"
    suspicious = check_salary(600_000, 900_000, True, market)
    assert suspicious.status == "suspicious" and suspicious.median == 250_000
    assert check_salary(600_000, 900_000, True, market[:2]).status == "unknown"
    assert check_salary(200_000, 260_000, False, market).status == "ok"


def test_reputation_shows_facts_only_with_enough_data() -> None:
    """Проценты появляются от трёх событий; подтверждённые жалобы видны всегда."""
    young = build_reputation(ReputationCounts(applications_received=2), SINCE)
    assert young.response_rate is None
    assert young.summary == "Подтверждённых жалоб нет"
    active = build_reputation(
        ReputationCounts(
            invitations_answered=5,
            invitations_accepted=2,
            applications_received=10,
            applications_answered=8,
            complaints_confirmed=1,
        ),
        SINCE,
    )
    assert active.response_rate == 0.8 and active.acceptance_rate == 0.4
    assert active.summary == (
        "Отвечает на отклики: 80 %; приглашения принимают: 40 %; подтверждённых жалоб: 1"
    )
