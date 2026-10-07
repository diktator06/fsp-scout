import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_fsp_gateway
from app.core.config import get_settings
from app.integrations.fsp_gateway import build_fsp_gateway
from app.main import app
from app.models.audit import AuditLog
from app.models.consent import Consent, ConsentType
from app.models.user import User, UserRole
from tests.api.test_employer_matching import UserFactory, create_need, employer_headers
from tests.factories import make_bank_candidate
from tests.fsp_fake import FakeFsp, achievement
from tests.helpers import auth_headers

FSP = "/api/v1/candidates/me/fsp"
RICH = [
    achievement("EV-1", result="winner", event_date="2026-05-10", level="national", place=1),
    achievement("EV-2", result="prize", event_date="2025-11-02", level="local", place=3),
    achievement("EV-3", result="finalist", event_date="2025-04-20", place=9),
    achievement("EV-4", event_date="2024-09-14"),
    achievement("EV-5", event_date="2026-02-01", online=True, place=None, total=None),
]


@pytest.fixture
def fsp(client: AsyncClient) -> FakeFsp:
    """Поддельный ФСП ID и реестр вместо эмулятора."""
    fake = FakeFsp(get_settings())
    gateway = build_fsp_gateway(get_settings(), fake.transport())
    app.dependency_overrides[get_fsp_gateway] = lambda: gateway
    return fake


async def link(
    client: AsyncClient, fsp: FakeFsp, user: User, participant_id: str
) -> tuple[int, dict]:
    """Полный путь привязки: согласие → страница ФСП ID → возврат с кодом."""
    headers = auth_headers(user)
    start = await client.post(f"{FSP}/link", json={"consent": True}, headers=headers)
    assert start.status_code == 200, start.text
    code, state = fsp.authorize(start.json()["authorization_url"], participant_id)
    response = await client.post(
        f"{FSP}/link/callback", json={"code": code, "state": state}, headers=headers
    )
    return response.status_code, response.json()


def fsp_component(score: dict) -> float:
    """Вклад ФСП в индекс подтверждённого профиля, баллов."""
    return next(item["contribution"] for item in score["components"] if item["key"] == "fsp")


async def test_not_linked_is_neutral_state(
    client: AsyncClient, fsp: FakeFsp, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Без привязки: F = 0 без ошибок, нейтральный текст у кандидата и у работодателя."""
    candidate = await make_bank_candidate(db_session)
    own = (await client.get(FSP, headers=auth_headers(candidate.user))).json()
    assert own["state"] == "not_linked"
    assert own["score"]["value"] == 0
    assert own["achievements"] == []
    assert own["verified_score"] is not None
    assert fsp_component(own["verified_score"]) == 0

    employer = await employer_headers(client, make_user)
    card = (
        await client.get(f"/api/v1/employer/candidates/{candidate.profile_id}", headers=employer)
    ).json()["card"]
    assert card["fsp"]["state"] == "not_linked"
    assert "не привязан" in card["fsp"]["message"]
    assert fsp.calls == []


async def test_link_with_achievements_raises_index(
    client: AsyncClient, fsp: FakeFsp, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Привязка с историей: участия сохранены, F > 0, индекс вырос, работодатель видит блок."""
    candidate = await make_bank_candidate(db_session)
    before = (await client.get(FSP, headers=auth_headers(candidate.user))).json()
    refused = await client.post(
        f"{FSP}/link", json={"consent": False}, headers=auth_headers(candidate.user)
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "consent_required"

    status, body = await link(client, fsp, candidate.user, fsp.add("fsp-000101", RICH))
    assert status == 200, body
    assert body["state"] == "linked"
    assert body["participant_id"] == "fsp-000101"
    assert body["consent_active"] is True
    assert len(body["achievements"]) == 5
    assert body["last_sync"]["status"] == "ok"
    assert body["sport_rank"] == "КМС"
    score = body["score"]
    assert 0 < score["value"] <= 1
    assert score["wins"] == 1 and score["prizes"] == 1 and score["finals"] == 1
    assert score["online_attendance"] == 1
    assert score["best_result"].startswith("победитель")
    assert body["verified_score"]["total"] > before["verified_score"]["total"]
    assert fsp_component(body["verified_score"]) == pytest.approx(score["vps_points"], abs=0.1)

    consents = await db_session.scalars(
        select(Consent).where(
            Consent.user_id == candidate.user.id,
            Consent.consent_type == ConsentType.FSP_DATA_ACCESS,
        )
    )
    assert len(consents.all()) == 1
    audit = await db_session.scalars(select(AuditLog).where(AuditLog.action == "fsp_linked"))
    assert len(audit.all()) == 1

    employer = await employer_headers(client, make_user)
    bank = (
        await client.get("/api/v1/employer/candidates", params={"has_fsp": True}, headers=employer)
    ).json()
    assert [item["card"]["candidate_id"] for item in bank["items"]] == [candidate.profile_id]
    card = bank["items"][0]["card"]["fsp"]
    assert card["state"] == "linked"
    assert card["score"] == score["value"]
    assert card["best_result"].startswith("победитель")
    assert len(card["achievements"]) == 5
    assert card["achievements"][0]["protocol_url"].startswith("https://")

    need = await create_need(client, employer)
    shortlist = (
        await client.post(
            f"/api/v1/employer/needs/{need['id']}/shortlists",
            json={"fsp_only": True},
            headers=employer,
        )
    ).json()
    entry = next(
        item
        for item in shortlist["entries"]
        if item["card"]["candidate_id"] == candidate.profile_id
    )
    texts = [item["text"] for item in entry["match"]["explanation"]]
    assert any(text.startswith("ФСП: победитель") for text in texts)


async def test_link_without_history(
    client: AsyncClient, fsp: FakeFsp, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Привязан без истории: отдельное нейтральное состояние, F = 0, синхронизация «пусто»."""
    candidate = await make_bank_candidate(db_session)
    status, body = await link(client, fsp, candidate.user, fsp.add("fsp-000102", []))
    assert status == 200, body
    assert body["state"] == "linked_empty"
    assert body["score"]["value"] == 0
    assert body["last_sync"]["status"] == "empty"
    assert fsp_component(body["verified_score"]) == 0

    employer = await employer_headers(client, make_user)
    card = (
        await client.get(f"/api/v1/employer/candidates/{candidate.profile_id}", headers=employer)
    ).json()["card"]["fsp"]
    assert card["state"] == "linked_empty"
    assert "участий в соревнованиях пока нет" in card["message"]
    bank = (
        await client.get("/api/v1/employer/candidates", params={"has_fsp": True}, headers=employer)
    ).json()
    assert bank["total"] == 0


async def test_hidden_achievements_are_not_used(
    client: AsyncClient, fsp: FakeFsp, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Скрытые кандидатом достижения не видны работодателю и не влияют на его выдачу."""
    candidate = await make_bank_candidate(db_session)
    await link(client, fsp, candidate.user, fsp.add("fsp-000103", RICH))
    headers = auth_headers(candidate.user)
    privacy = (await client.get("/api/v1/candidates/me/privacy", headers=headers)).json()
    response = await client.put(
        "/api/v1/candidates/me/privacy",
        json={**privacy, "show_fsp_achievements": False},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    employer = await employer_headers(client, make_user)
    card = (
        await client.get(f"/api/v1/employer/candidates/{candidate.profile_id}", headers=employer)
    ).json()["card"]
    assert card["fsp"]["state"] == "hidden"
    assert card["fsp"]["achievements"] == []
    assert card["fsp"]["score"] == 0
    assert fsp_component(card["verified_score"]) == 0
    own = (await client.get(FSP, headers=headers)).json()
    assert own["state"] == "linked" and own["visible_to_employers"] is False


async def test_registry_down_keeps_last_data(
    client: AsyncClient, fsp: FakeFsp, db_session: AsyncSession
) -> None:
    """Реестр недоступен: прошлые участия остаются, ошибка — в журнале и в ответе."""
    candidate = await make_bank_candidate(db_session, take_test=False)
    await link(client, fsp, candidate.user, fsp.add("fsp-000104", RICH))
    fsp.registry_down = True
    response = await client.post(f"{FSP}/sync", headers=auth_headers(candidate.user))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["last_sync"]["status"] == "error"
    assert body["state"] == "linked"
    assert len(body["achievements"]) == 5

    fsp.registry_down = False
    fsp.participants["fsp-000104"]["achievements"] = RICH[:2]
    refreshed = (await client.post(f"{FSP}/sync", headers=auth_headers(candidate.user))).json()
    assert refreshed["last_sync"]["status"] == "ok"
    assert len(refreshed["achievements"]) == 2


async def test_state_is_single_use_and_bound_to_user(
    client: AsyncClient, fsp: FakeFsp, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """State одноразовый и принадлежит начавшему привязку; подмена nonce отвергается."""
    owner = await make_user(UserRole.CANDIDATE)
    stranger = await make_user(UserRole.CANDIDATE)
    fsp.add("fsp-000105", RICH)
    start = await client.post(f"{FSP}/link", json={"consent": True}, headers=auth_headers(owner))
    code, state = fsp.authorize(start.json()["authorization_url"], "fsp-000105")
    hijack = await client.post(
        f"{FSP}/link/callback", json={"code": code, "state": state}, headers=auth_headers(stranger)
    )
    assert hijack.status_code == 400
    assert hijack.json()["error"]["code"] == "fsp_auth_failed"
    replay = await client.post(
        f"{FSP}/link/callback", json={"code": code, "state": state}, headers=auth_headers(owner)
    )
    assert replay.status_code == 400

    fsp.forged_nonce = "forged"
    status, body = await link(client, fsp, owner, "fsp-000105")
    assert status == 400
    assert body["error"]["code"] == "fsp_auth_failed"
    fsp.forged_nonce = None
    fsp.rotate_key()
    status, body = await link(client, fsp, owner, "fsp-000105")
    assert status == 200, body


async def test_participant_links_to_one_profile_only(
    client: AsyncClient, fsp: FakeFsp, make_user: UserFactory
) -> None:
    """Один участник ФСП — один профиль: чужие победы себе не приписать."""
    first = await make_user(UserRole.CANDIDATE)
    second = await make_user(UserRole.CANDIDATE)
    fsp.add("fsp-000106", RICH)
    assert (await link(client, fsp, first, "fsp-000106"))[0] == 200
    status, body = await link(client, fsp, second, "fsp-000106")
    assert status == 409
    assert body["error"]["code"] == "fsp_already_linked"
    again = await client.post(f"{FSP}/link", json={"consent": True}, headers=auth_headers(first))
    assert again.status_code == 409


async def test_unlink_removes_data_and_revokes_consent(
    client: AsyncClient, fsp: FakeFsp, db_session: AsyncSession, make_user: UserFactory
) -> None:
    """Отвязка удаляет участия и привязку и отзывает согласие на данные ФСП."""
    user = await make_user(UserRole.CANDIDATE)
    await link(client, fsp, user, fsp.add("fsp-000107", RICH))
    response = await client.delete(FSP, headers=auth_headers(user))
    assert response.status_code == 204
    body = (await client.get(FSP, headers=auth_headers(user))).json()
    assert body["state"] == "not_linked"
    assert body["achievements"] == []
    assert body["consent_active"] is False
    assert (await client.delete(FSP, headers=auth_headers(user))).status_code == 409
    other = await make_user(UserRole.CANDIDATE)
    assert (await link(client, fsp, other, "fsp-000107"))[0] == 200


async def test_login_with_fsp_id(client: AsyncClient, fsp: FakeFsp, make_user: UserFactory) -> None:
    """Вход через ФСП ID работает для привязанного аккаунта и честно отказывает остальным."""
    fsp.add("fsp-000108", RICH)
    start = await client.post("/api/v1/auth/fsp/start")
    assert start.status_code == 200, start.text
    code, state = fsp.authorize(start.json()["authorization_url"], "fsp-000108")
    unknown = await client.post("/api/v1/auth/fsp/callback", json={"code": code, "state": state})
    assert unknown.status_code == 409
    assert unknown.json()["error"]["code"] == "fsp_not_linked"

    user = await make_user(UserRole.CANDIDATE)
    await link(client, fsp, user, "fsp-000108")
    start = await client.post("/api/v1/auth/fsp/start")
    code, state = fsp.authorize(start.json()["authorization_url"], "fsp-000108")
    response = await client.post("/api/v1/auth/fsp/callback", json={"code": code, "state": state})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == str(user.id)
    assert get_settings().refresh_cookie_name in response.cookies


async def test_fsp_unavailable_on_start(
    client: AsyncClient, fsp: FakeFsp, make_user: UserFactory
) -> None:
    """Если ФСП ID не отвечает, начать вход нельзя, и это понятная ошибка 503."""
    user = await make_user(UserRole.CANDIDATE)

    def broken(request: httpx.Request) -> httpx.Response:
        """Провайдер недоступен."""
        raise httpx.ConnectError("down", request=request)

    gateway = build_fsp_gateway(get_settings(), httpx.MockTransport(broken))
    app.dependency_overrides[get_fsp_gateway] = lambda: gateway
    response = await client.post(f"{FSP}/link", json={"consent": True}, headers=auth_headers(user))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "fsp_unavailable"
