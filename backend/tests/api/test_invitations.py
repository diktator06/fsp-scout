from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.candidate import ContactChannel
from app.models.employer import TrustLevel
from app.models.invitation import Invitation
from app.models.user import User
from app.services.invitations import quotas
from tests.api.test_employer_matching import create_need, employer_headers
from tests.factories import BankCandidate, make_bank_candidate
from tests.helpers import RecordingMailer, auth_headers

UserFactory = Callable[..., Awaitable[User]]
INVITATIONS = "/api/v1/employer/invitations"
INBOX = "/api/v1/candidates/me/invitations"


def offer(candidate: BankCandidate, **overrides: Any) -> dict[str, Any]:
    """Корректное приглашение с вилкой и способом связи."""
    payload: dict[str, Any] = {
        "candidate_id": candidate.profile_id,
        "title": "Python-разработчик в платежи",
        "offer_description": "Развиваем платёжный шлюз: эквайринг и биллинг. Команда из 8 человек.",
        "salary_from": 250_000,
        "salary_to": 320_000,
        "salary_gross": True,
        "work_format": "remote",
        "contact_method": "Telegram @kedr_hr, отвечаем в течение дня",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "override",
    [
        {"salary_from": None},
        {"salary_to": 200_000},
        {"salary_to": 600_000},
        {"salary_from": 0},
        {"contact_method": ""},
        {"offer_description": "коротко"},
    ],
)
async def test_invitation_requires_salary_range_and_contact(
    client: AsyncClient,
    make_user: UserFactory,
    db_session: AsyncSession,
    override: dict[str, Any],
) -> None:
    """R2, R3: вилка «от–до» обязательна, «от» ≤ «до», не шире вдвое.

    Описание предложения и способ связи тоже обязательны.
    """
    candidate = await make_bank_candidate(db_session)
    headers = await employer_headers(client, make_user)
    response = await client.post(INVITATIONS, json=offer(candidate, **override), headers=headers)
    assert response.status_code == 422


async def test_full_invitation_cycle_discloses_contacts_only_after_accept(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession, mailer: RecordingMailer
) -> None:
    """R4, R5: статусы видны обеим сторонам, контакты раскрываются только после принятия."""
    candidate = await make_bank_candidate(
        db_session, revealed=(ContactChannel.TELEGRAM,), phone="+7 900 000-77-88"
    )
    headers = await employer_headers(client, make_user)
    need = await create_need(client, headers)
    created = await client.post(
        INVITATIONS, json=offer(candidate, need_id=need["id"]), headers=headers
    )
    assert created.status_code == 201, created.text
    invitation = created.json()
    assert invitation["status"] == "sent"
    assert invitation["candidate"]["contacts"] is None
    assert invitation["need_title"] == need["title"]
    assert candidate.full_name not in created.text and candidate.telegram not in created.text
    assert mailer.outbox and "Кедр Технологии" in mailer.outbox[-1].subject

    duplicate = await client.post(INVITATIONS, json=offer(candidate), headers=headers)
    assert duplicate.status_code == 409

    candidate_headers = auth_headers(candidate.user)
    inbox = (await client.get(INBOX, headers=candidate_headers)).json()
    assert inbox[0]["company"]["name"] == "Кедр Технологии"
    assert (inbox[0]["salary_from"], inbox[0]["salary_to"]) == (250_000, 320_000)
    assert inbox[0]["employer_contacts"] is None

    opened = (await client.get(f"{INBOX}/{invitation['id']}", headers=candidate_headers)).json()
    assert opened["status"] == "viewed"
    employer_view = (await client.get(f"{INVITATIONS}/{invitation['id']}", headers=headers)).json()
    assert employer_view["status"] == "viewed"
    assert employer_view["candidate"]["contacts"] is None
    card = (
        await client.get(f"/api/v1/employer/candidates/{candidate.profile_id}", headers=headers)
    ).json()
    assert card["contacts"] is None

    accepted = await client.post(f"{INBOX}/{invitation['id']}/accept", headers=candidate_headers)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["employer_contacts"]["telegram"] == "@kedr_hr"
    assert accepted.json()["employer_contacts"]["recruiter_name"] == "Мария Соколова"

    after = (await client.get(f"{INVITATIONS}/{invitation['id']}", headers=headers)).json()
    contacts = after["candidate"]["contacts"]
    assert after["status"] == "accepted"
    assert contacts["full_name"] == candidate.full_name
    assert contacts["telegram"] == candidate.telegram
    assert contacts["phone"] is None and contacts["email"] is None
    assert [(e["status"], e["actor"]) for e in after["events"]] == [
        ("sent", "employer"),
        ("viewed", "candidate"),
        ("accepted", "candidate"),
    ]
    card = (
        await client.get(f"/api/v1/employer/candidates/{candidate.profile_id}", headers=headers)
    ).json()
    assert card["contacts"]["full_name"] == candidate.full_name
    audit = (
        await db_session.scalars(select(AuditLog).where(AuditLog.action == "contacts_disclosed"))
    ).all()
    assert any(row.entity_id == candidate.profile_id for row in audit)

    again = await client.post(
        f"{INBOX}/{invitation['id']}/decline", json={"reason": "salary"}, headers=candidate_headers
    )
    assert again.status_code == 409

    notes = (await client.get("/api/v1/notifications", headers=headers)).json()
    assert notes["unread"] >= 1 and notes["items"][0]["kind"] == "invitation_accepted"
    cleared = (await client.post("/api/v1/notifications/read-all", headers=headers)).json()
    assert cleared["unread"] == 0


async def test_decline_withdraw_and_expiry(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """Отказ с причиной не раскрывает контакты; отозванное и просроченное нельзя принять."""
    first = await make_bank_candidate(db_session)
    second = await make_bank_candidate(db_session, telegram="second_bank_test")
    third = await make_bank_candidate(db_session, telegram="third_bank_test")
    headers = await employer_headers(client, make_user)

    declined_id = (await client.post(INVITATIONS, json=offer(first), headers=headers)).json()["id"]
    declined = await client.post(
        f"{INBOX}/{declined_id}/decline",
        json={"reason": "salary", "comment": "Ожидаю больше"},
        headers=auth_headers(first.user),
    )
    assert declined.json()["status"] == "declined"
    employer_view = (await client.get(f"{INVITATIONS}/{declined_id}", headers=headers)).json()
    assert employer_view["decline_reason"] == "salary"
    assert employer_view["candidate"]["contacts"] is None

    withdrawn_id = (await client.post(INVITATIONS, json=offer(second), headers=headers)).json()[
        "id"
    ]
    withdrawn = await client.post(f"{INVITATIONS}/{withdrawn_id}/withdraw", headers=headers)
    assert withdrawn.json()["status"] == "withdrawn"
    late = await client.post(f"{INBOX}/{withdrawn_id}/accept", headers=auth_headers(second.user))
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "invitation_state"

    expired_id = (await client.post(INVITATIONS, json=offer(third), headers=headers)).json()["id"]
    await db_session.execute(
        update(Invitation)
        .where(Invitation.id == expired_id)
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()
    inbox = (await client.get(INBOX, headers=auth_headers(third.user))).json()
    assert inbox[0]["status"] == "expired"
    assert (
        await client.post(f"{INBOX}/{expired_id}/accept", headers=auth_headers(third.user))
    ).status_code == 409
    filtered = (await client.get(INVITATIONS, params={"status": "expired"}, headers=headers)).json()
    assert [item["id"] for item in filtered] == [expired_id]


async def test_invitations_are_isolated(
    client: AsyncClient, make_user: UserFactory, db_session: AsyncSession
) -> None:
    """R11: кандидат видит только свои приглашения, компания — только свои."""
    owner = await make_bank_candidate(db_session)
    stranger = await make_bank_candidate(db_session, telegram="stranger_bank_test")
    headers = await employer_headers(client, make_user)
    invitation_id = (await client.post(INVITATIONS, json=offer(owner), headers=headers)).json()[
        "id"
    ]

    assert (
        await client.get(f"{INBOX}/{invitation_id}", headers=auth_headers(stranger.user))
    ).status_code == 404
    assert (
        await client.post(f"{INBOX}/{invitation_id}/accept", headers=auth_headers(stranger.user))
    ).status_code == 404
    assert (await client.get(INBOX, headers=auth_headers(stranger.user))).json() == []
    other_company = await employer_headers(client, make_user)
    assert (
        await client.get(f"{INVITATIONS}/{invitation_id}", headers=other_company)
    ).status_code == 404
    assert (
        await client.post(f"{INVITATIONS}/{invitation_id}/withdraw", headers=other_company)
    ).status_code == 404
    assert (await client.get(INVITATIONS, headers=other_company)).json() == []


async def test_daily_quota_and_hidden_candidates(
    client: AsyncClient,
    make_user: UserFactory,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Квота приглашений и запрет приглашать тех, кто скрыл профиль."""
    monkeypatch.setitem(quotas.DAILY_INVITATION_LIMITS, TrustLevel.NEW, 1)
    first = await make_bank_candidate(db_session)
    second = await make_bank_candidate(db_session, telegram="quota_second")
    hidden = await make_bank_candidate(db_session, published=False, telegram="quota_hidden")
    headers = await employer_headers(client, make_user)
    assert (await client.post(INVITATIONS, json=offer(hidden), headers=headers)).status_code == 404
    assert (await client.post(INVITATIONS, json=offer(first), headers=headers)).status_code == 201
    exceeded = await client.post(INVITATIONS, json=offer(second), headers=headers)
    assert exceeded.status_code == 429
    assert exceeded.json()["error"]["code"] == "invitation_quota_exceeded"
