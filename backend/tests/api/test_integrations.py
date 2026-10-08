import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.main import app
from app.models.audit import AuditLog
from app.models.integration import WebhookDelivery
from app.models.notification import Notification, NotificationKind
from app.models.user import UserRole
from app.services.integrations import signing
from app.services.integrations.dispatcher import MAX_ATTEMPTS, RETRY_DELAYS, WebhookDispatcher
from tests.api.test_employer_matching import employer_headers
from tests.api.test_invitations import INBOX, INVITATIONS, UserFactory, offer
from tests.api.test_vacancies import publish_vacancy
from tests.factories import make_bank_candidate
from tests.helpers import auth_headers

BASE = "/api/v1/employer/integrations"
PUBLIC_URL = "https://93.184.215.14/hooks/scout"


def same_session(
    session: AsyncSession,
) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    """Фабрика сессий диспетчера, которая отдаёт тестовую сессию."""

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        """Тестовая сессия вместо новой из пула."""
        yield session

    return factory


def sandbox_dispatcher(session: AsyncSession) -> WebhookDispatcher:
    """Диспетчер, который доставляет в песочницу внутри того же приложения."""
    return WebhookDispatcher(
        same_session(session), get_settings(), transport=httpx.ASGITransport(app=app)
    )


async def test_endpoint_management_and_ssrf_guard(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Адрес во внутреннюю сеть не принимается; секрет виден полностью один раз."""
    headers = await employer_headers(client, make_user)
    unsafe = await client.post(
        f"{BASE}/webhooks",
        json={"url": "http://169.254.169.254/latest", "events": ["invitation.accepted"]},
        headers=headers,
    )
    assert unsafe.status_code == 422
    assert unsafe.json()["error"]["code"] == "unsafe_webhook_url"
    no_events = await client.post(
        f"{BASE}/webhooks", json={"url": PUBLIC_URL, "events": ["ping"]}, headers=headers
    )
    assert no_events.status_code == 422

    created = await client.post(
        f"{BASE}/webhooks",
        json={"url": PUBLIC_URL, "events": ["invitation.accepted"], "description": "Хантфлоу"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    endpoint = created.json()
    assert endpoint["secret"].startswith("whsec_") and endpoint["is_sandbox"] is False
    listed = (await client.get(f"{BASE}/webhooks", headers=headers)).json()
    assert "secret" not in listed[0] and listed[0]["secret_hint"].endswith(endpoint["secret"][-4:])

    updated = await client.patch(
        f"{BASE}/webhooks/{endpoint['id']}",
        json={"events": ["application.created", "application.created"], "is_active": False},
        headers=headers,
    )
    assert updated.json()["events"] == ["application.created"]
    assert updated.json()["is_active"] is False
    rotated = (
        await client.post(f"{BASE}/webhooks/{endpoint['id']}/secret", headers=headers)
    ).json()
    assert rotated["secret"] != endpoint["secret"]

    stranger = await employer_headers(client, make_user)
    assert (
        await client.delete(f"{BASE}/webhooks/{endpoint['id']}", headers=stranger)
    ).status_code == 404
    candidate = auth_headers(await make_user(UserRole.CANDIDATE))
    assert (await client.get(f"{BASE}/webhooks", headers=candidate)).status_code == 403
    assert (
        await client.delete(f"{BASE}/webhooks/{endpoint['id']}", headers=headers)
    ).status_code == 204
    assert (await client.get(f"{BASE}/webhooks", headers=headers)).json() == []


async def test_invitation_events_reach_sandbox_signed(
    client: AsyncClient, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Принятие приглашения уходит в ATS с открытыми контактами, отказ — без них."""
    headers = await employer_headers(client, make_user)
    sandbox = await client.post(f"{BASE}/sandbox", headers=headers)
    assert sandbox.status_code == 201 and sandbox.json()["is_sandbox"] is True
    assert (await client.post(f"{BASE}/sandbox", headers=headers)).status_code == 409

    accepting = await make_bank_candidate(db_session)
    invitation = (await client.post(INVITATIONS, json=offer(accepting), headers=headers)).json()
    accepted = await client.post(
        f"{INBOX}/{invitation['id']}/accept", headers=auth_headers(accepting.user)
    )
    assert accepted.status_code == 200
    log = (await client.get(f"{BASE}/deliveries", headers=headers)).json()
    assert [item["event_type"] for item in log] == ["invitation.accepted"]
    candidate = log[0]["payload"]["data"]["candidate"]
    assert candidate["full_name"] == accepting.full_name
    assert candidate["telegram"] == accepting.telegram and candidate["phone"] is None
    assert candidate["source"] == "invitation_accepted" and candidate["grade_confirmed"] is True

    assert await sandbox_dispatcher(db_session).run_once() == 1
    delivered = (await client.get(f"{BASE}/deliveries", headers=headers)).json()[0]
    assert delivered["status"] == "delivered" and delivered["response_status"] == 200
    assert f"«{accepting.full_name}» заведена" in delivered["response_body"]

    declining = await make_bank_candidate(db_session, telegram="declining_test")
    second = (await client.post(INVITATIONS, json=offer(declining), headers=headers)).json()
    await client.post(
        f"{INBOX}/{second['id']}/decline",
        json={"reason": "salary", "comment": "Мало"},
        headers=auth_headers(declining.user),
    )
    declined = (await client.get(f"{BASE}/deliveries", headers=headers)).json()[0]
    assert declined["event_type"] == "invitation.declined"
    assert declined["payload"]["data"]["reason"] == "salary"
    assert declining.full_name not in json.dumps(declined["payload"], ensure_ascii=False)

    forged = await client.post(
        "/api/v1/integrations/sandbox/receive",
        content=b"{}",
        headers={
            signing.DELIVERY_HEADER: declined["id"],
            signing.TIMESTAMP_HEADER: str(int(datetime.now(UTC).timestamp())),
            signing.SIGNATURE_HEADER: "sha256=00",
        },
    )
    assert forged.status_code == 401


async def test_failed_delivery_retries_with_backoff_then_notifies(
    client: AsyncClient, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Пять повторов с растущей паузой, потом «не доставлено», уведомление и ручной повтор."""
    headers = await employer_headers(client, make_user)
    endpoint = (
        await client.post(
            f"{BASE}/webhooks",
            json={"url": PUBLIC_URL, "events": ["application.created"]},
            headers=headers,
        )
    ).json()
    queued = await client.post(f"{BASE}/webhooks/{endpoint['id']}/test", headers=headers)
    assert queued.status_code == 202 and queued.json()["event_type"] == "ping"

    seen: list[httpx.Request] = []

    def broken_ats(request: httpx.Request) -> httpx.Response:
        """ATS, которая лежит."""
        seen.append(request)
        return httpx.Response(503, text="maintenance")

    now = [datetime.now(UTC) + timedelta(seconds=1)]
    dispatcher = WebhookDispatcher(
        same_session(db_session),
        get_settings(),
        transport=httpx.MockTransport(broken_ats),
        clock=lambda: now[0],
    )
    assert await dispatcher.run_once() == 1
    first = (await client.get(f"{BASE}/deliveries", headers=headers)).json()[0]
    assert first["status"] == "pending" and first["attempts"] == 1
    assert first["error"] == "Получатель ответил 503"
    request = seen[0]
    assert request.headers[signing.EVENT_HEADER] == "ping"
    assert signing.verify(
        endpoint["secret"],
        request.headers[signing.TIMESTAMP_HEADER],
        request.content,
        request.headers[signing.SIGNATURE_HEADER],
        int(now[0].timestamp()),
    )

    assert await dispatcher.run_once() == 0
    for delay in RETRY_DELAYS:
        now[0] += delay
        assert await dispatcher.run_once() == 1
    final = (await client.get(f"{BASE}/deliveries", headers=headers)).json()[0]
    assert final["status"] == "failed" and final["attempts"] == MAX_ATTEMPTS
    assert len({item.headers[signing.EVENT_ID_HEADER] for item in seen}) == 1
    notices = (
        await db_session.scalars(
            select(Notification).where(Notification.kind == NotificationKind.WEBHOOK_FAILED)
        )
    ).all()
    assert notices

    retry = await client.post(f"{BASE}/deliveries/{final['id']}/retry", headers=headers)
    assert retry.status_code == 202
    assert retry.json()["event_id"] == final["event_id"] and retry.json()["status"] == "pending"
    again = await client.post(f"{BASE}/deliveries/{retry.json()['id']}/retry", headers=headers)
    assert again.status_code == 409


async def test_applications_feed_ats_and_export(
    client: AsyncClient, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Отклик и его отзыв уходят событиями; выгрузка — только открывшие контакты, с аудитом."""
    headers = await employer_headers(client, make_user)
    await client.post(f"{BASE}/sandbox", headers=headers)
    vacancy = await publish_vacancy(client, headers)
    applicant = await make_bank_candidate(db_session, skills=("python", "fastapi", "sql"))
    hidden = await make_bank_candidate(db_session, full_name="Скрытый Кандидат", telegram="hidden1")
    me = auth_headers(applicant.user)
    applied = await client.post(
        f"/api/v1/vacancies/{vacancy['id']}/applications",
        json={"cover_letter": "Строил биллинг", "share_contacts": True},
        headers=me,
    )
    assert applied.status_code == 201
    await client.post(
        f"/api/v1/candidates/me/applications/{applied.json()['id']}/withdraw", headers=me
    )
    log = (await client.get(f"{BASE}/deliveries", headers=headers)).json()
    assert [item["event_type"] for item in log] == ["application.withdrawn", "application.created"]
    created = log[1]["payload"]["data"]
    assert created["vacancy"]["title"] == vacancy["title"]
    assert created["candidate"]["full_name"] == applicant.full_name
    assert created["application"]["match_score"] > 0

    csv_file = await client.get(f"{BASE}/export", params={"format": "csv"}, headers=headers)
    assert csv_file.status_code == 200
    assert csv_file.headers["content-disposition"].startswith("attachment;")
    text = csv_file.content.decode("utf-8-sig")
    assert applicant.full_name in text and hidden.full_name not in text
    exported = (
        await client.get(f"{BASE}/export", params={"format": "json"}, headers=headers)
    ).json()
    assert exported["count"] == 1
    assert exported["candidates"][0]["source"] == "application"
    audit = (
        await db_session.scalars(select(AuditLog).where(AuditLog.action == "candidates_exported"))
    ).all()
    assert len(audit) == 2

    candidate = auth_headers(await make_user(UserRole.CANDIDATE))
    assert (await client.get(f"{BASE}/export", headers=candidate)).status_code == 403
    pending = (await db_session.scalars(select(WebhookDelivery))).all()
    assert all(item.status.value == "pending" for item in pending)
