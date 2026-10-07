import base64
import hashlib
import re
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest

from app.config import get_settings
from app.main import app
from app.store import get_registry

SETTINGS = get_settings()
REDIRECT = SETTINGS.redirect_uris[0]
VERIFIER = "x" * 64


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """HTTP-клиент к приложению эмулятора без сети."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://mock") as http:
        yield http


def _challenge(verifier: str) -> str:
    """PKCE S256 от verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def _authorize(
    client: httpx.AsyncClient, login: str, password: str = "FspDemo2026"
) -> dict[str, list[str]]:
    """Проходит страницу входа и возвращает параметры редиректа на клиента."""
    form = {
        "client_id": SETTINGS.client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "code_challenge": _challenge(VERIFIER),
        "code_challenge_method": "S256",
        "state": "st4te",
        "nonce": "n0nce",
        "scope": "openid profile achievements",
        "login": login,
        "password": password,
        "action": "login",
    }
    response = await client.post("/authorize", data=form, follow_redirects=False)
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    assert location.startswith(REDIRECT)
    return parse_qs(urlparse(location).query)


async def _token(
    client: httpx.AsyncClient, code: str, verifier: str = VERIFIER
) -> dict[str, object]:
    """Обмен кода на токены с аутентификацией клиента в теле запроса."""
    response = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "code_verifier": verifier,
            "client_id": SETTINGS.client_id,
            "client_secret": SETTINGS.client_secret,
        },
    )
    return {"status": response.status_code, **response.json()}


async def test_discovery_and_jwks(client: httpx.AsyncClient) -> None:
    """Discovery указывает на свои эндпоинты, JWKS публикует ключ RS256."""
    config = (await client.get("/.well-known/openid-configuration")).json()
    assert config["issuer"] == SETTINGS.issuer
    assert config["code_challenge_methods_supported"] == ["S256"]
    keys = (await client.get("/jwks.json")).json()["keys"]
    assert keys[0]["alg"] == "RS256" and keys[0]["kty"] == "RSA"


async def test_authorization_code_flow_with_pkce(client: httpx.AsyncClient) -> None:
    """Полный вход: страница, код, обмен с PKCE, проверяемый по JWKS id_token, реестр."""
    page = await client.get(
        "/authorize",
        params={
            "client_id": SETTINGS.client_id,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "code_challenge": _challenge(VERIFIER),
            "code_challenge_method": "S256",
            "state": "st4te",
        },
    )
    assert page.status_code == 200 and "Эмулятор" in page.text
    login = re.search(r'name="login" value="(fsp\d+)"', page.text)
    assert login is not None
    redirect = await _authorize(client, login.group(1))
    assert redirect["state"] == ["st4te"]
    tokens = await _token(client, redirect["code"][0])
    assert tokens["status"] == 200
    jwk = (await client.get("/jwks.json")).json()["keys"][0]
    public_key = jwt.PyJWK(jwk).key
    claims = jwt.decode(
        str(tokens["id_token"]), public_key, algorithms=["RS256"], audience=SETTINGS.client_id
    )
    assert claims["sub"].startswith("fsp-") and claims["nonce"] == "n0nce"

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    own = await client.get(f"/participants/{claims['sub']}/achievements", headers=headers)
    assert own.status_code == 200 and "full_name" not in own.text
    other = await client.get("/participants/fsp-000002/achievements", headers=headers)
    assert other.status_code == 403 or claims["sub"] == "fsp-000002"
    assert (await client.get("/userinfo", headers=headers)).json()["sub"] == claims["sub"]


async def test_code_is_single_use_and_pkce_is_enforced(client: httpx.AsyncClient) -> None:
    """Неверный verifier и повторный код отклоняются."""
    login = get_registry().participants[0]["login"]
    code = (await _authorize(client, login))["code"][0]
    assert (await _token(client, code, verifier="y" * 64))["status"] == 400
    assert (await _token(client, code))["status"] == 400
    assert (await client.post("/authorize", data={"login": login})).status_code == 422


async def test_wrong_password_and_foreign_redirect(client: httpx.AsyncClient) -> None:
    """Неверный пароль не выдаёт код; чужой redirect_uri блокирует страницу."""
    response = await client.post(
        "/authorize",
        data={
            "client_id": SETTINGS.client_id,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "code_challenge": _challenge(VERIFIER),
            "code_challenge_method": "S256",
            "login": "fsp000001",
            "password": "wrong",
        },
        follow_redirects=False,
    )
    assert response.status_code == 401
    bad = await client.get(
        "/authorize",
        params={
            "client_id": SETTINGS.client_id,
            "redirect_uri": "https://evil.example/cb",
            "response_type": "code",
            "code_challenge": "c",
            "code_challenge_method": "S256",
        },
    )
    assert bad.status_code == 400 and "не зарегистрирован" in bad.text


async def test_service_access_to_registry(client: httpx.AsyncClient) -> None:
    """Сервисный клиент получает список участников и достижения любого из них."""
    basic = base64.b64encode(f"{SETTINGS.client_id}:{SETTINGS.client_secret}".encode()).decode()
    token = (
        await client.post(
            "/token",
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {basic}"},
        )
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    listing = (await client.get("/participants", params={"limit": 500}, headers=headers)).json()
    assert listing["total"] == len(listing["items"]) > 100
    assert any(item["events"] == 0 for item in listing["items"])
    detail = await client.get(
        f"/participants/{listing['items'][0]['id']}/achievements", headers=headers
    )
    assert detail.status_code == 200
    assert (
        await client.get("/participants", headers={"Authorization": "Bearer junk"})
    ).status_code == 401
    wrong = await client.post(
        "/token",
        data={
            "grant_type": "client_credentials",
            "client_id": SETTINGS.client_id,
            "client_secret": "x",
        },
    )
    assert wrong.status_code == 401
