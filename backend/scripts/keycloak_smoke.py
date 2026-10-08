import base64
import hashlib
import html
import re
import secrets
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import jwt

KEYCLOAK_ISSUER = "http://localhost:8081/realms/fsp"
SCOUT_API = "http://localhost:8080/api/v1"
REGISTRY_URL = "http://localhost:8090"
CLIENT_ID = "fsp-scout"
CLIENT_SECRET = "dev-only-fsp-client-secret"
REDIRECT_URI = "http://localhost:8080/c/fsp/callback"
USER_SCOPE = "openid profile achievements"
REGISTRY_AUDIENCE = "fsp-registry"
PERSONA_PASSWORD = "FspDemo2026"
DEMO_PASSWORD = "ScoutDemo2026"
SHOWCASE_PERSONA = ("fsp000021", "fsp-000021", 7)
SPARE_PERSONAS = ("fsp000030", "fsp000012", "fsp000007")
DEMO_CANDIDATES = tuple(f"demo.backend.{number:02d}@example.com" for number in range(1, 9))
TIMEOUT_SECONDS = 15


@dataclass
class Report:
    """Итог прогона: счётчик пройденных проверок и список упавших."""

    passed: int = 0
    failed: list[str] = field(default_factory=list)

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        """Печатает строку проверки и запоминает результат."""
        mark = "OK  " if condition else "FAIL"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))
        if condition:
            self.passed += 1
        else:
            self.failed.append(name)
        return condition


def pkce_pair() -> tuple[str, str]:
    """Верификатор PKCE и его challenge по методу S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def authorization_url(
    challenge: str | None, state: str, nonce: str, redirect_uri: str = REDIRECT_URI
) -> str:
    """Адрес страницы входа Keycloak; без challenge — чтобы проверить, что PKCE обязателен."""
    query = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": USER_SCOPE,
        "state": state,
        "nonce": nonce,
    }
    if challenge:
        query |= {"code_challenge": challenge, "code_challenge_method": "S256"}
    return f"{KEYCLOAK_ISSUER}/protocol/openid-connect/auth?{urlencode(query)}"


def keycloak_login(url: str, login: str, password: str) -> dict[str, str]:
    """Проходит форму входа Keycloak как браузер и возвращает параметры возврата.

    Успех — `code` и `state`; ошибка протокола — `error`; отказ формы (неверный
    пароль) — ключ `rejected`. Keycloak ставит cookie с флагом Secure: браузер шлёт
    их на http://localhost как в безопасный контекст, а httpx — нет, поэтому они
    передаются явно.
    """
    with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False) as browser:
        page = browser.get(url)
        if page.is_redirect:
            return _redirect_params(page.headers["location"])
        form = re.search(r'id="kc-form-login"[^>]*action="([^"]+)"', page.text)
        if form is None:
            return {"rejected": f"нет формы входа, ответ {page.status_code}"}
        cookie = "; ".join(f"{name}={value}" for name, value in browser.cookies.items())
        answer = browser.post(
            html.unescape(form.group(1)),
            data={"username": login, "password": password, "credentialId": ""},
            headers={"Cookie": cookie},
        )
        if not answer.is_redirect:
            return {"rejected": f"форма вернула {answer.status_code}"}
        return _redirect_params(answer.headers["location"])


def _redirect_params(location: str) -> dict[str, str]:
    """Параметры запроса из адреса возврата на фронтенд."""
    return {key: values[0] for key, values in parse_qs(urlparse(location).query).items()}


class TokenVerifier:
    """Проверка токенов Keycloak по JWKS — тем же способом, что у бэкенда и реестра."""

    def __init__(self, jwks: dict[str, Any]) -> None:
        """Запоминает набор открытых ключей realm."""
        self._keys = jwt.PyJWKSet.from_dict(jwks)

    def verify(self, token: str, audience: str) -> dict[str, Any]:
        """Подпись RS256, издатель, аудитория и срок действия."""
        kid = jwt.get_unverified_header(token).get("kid")
        key = next(item for item in self._keys.keys if item.key_id == kid)
        claims: dict[str, Any] = jwt.decode(
            token, key.key, algorithms=["RS256"], audience=audience, issuer=KEYCLOAK_ISSUER
        )
        return claims


def check_protocol(report: Report, http: httpx.Client) -> None:
    """OIDC напрямую с Keycloak: discovery, токены, claims, реестр и отказы."""
    meta = http.get(f"{KEYCLOAK_ISSUER}/.well-known/openid-configuration").json()
    report.check("discovery: issuer публичный", meta["issuer"] == KEYCLOAK_ISSUER, meta["issuer"])
    report.check(
        "discovery: поддерживается PKCE S256",
        "S256" in meta.get("code_challenge_methods_supported", []),
    )
    verifier = TokenVerifier(http.get(meta["jwks_uri"]).json())
    token_url = meta["token_endpoint"]
    client_auth = (CLIENT_ID, CLIENT_SECRET)

    service = http.post(
        token_url,
        data={"grant_type": "client_credentials", "scope": "registry:read"},
        auth=client_auth,
    ).json()
    service_claims = verifier.verify(service["access_token"], REGISTRY_AUDIENCE)
    report.check(
        "сервисный токен: подпись, iss, aud=fsp-registry",
        "registry:read" in service_claims["scope"].split(),
        f"scope='{service_claims['scope']}'",
    )
    listing = http.get(
        f"{REGISTRY_URL}/participants",
        params={"limit": 1},
        headers={"Authorization": f"Bearer {service['access_token']}"},
    )
    report.check("реестр принимает сервисный токен Keycloak", listing.status_code == 200)

    login, participant_id, events = SHOWCASE_PERSONA
    code_verifier, challenge = pkce_pair()
    state, nonce = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    back = keycloak_login(authorization_url(challenge, state, nonce), login, PERSONA_PASSWORD)
    if not report.check(
        f"вход {login} через форму Keycloak: code и тот же state",
        "code" in back and back.get("state") == state,
        back.get("rejected", ""),
    ):
        return
    exchange = {
        "grant_type": "authorization_code",
        "code": back["code"],
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier,
    }
    tokens = http.post(token_url, data=exchange, auth=client_auth).json()
    identity = verifier.verify(tokens["id_token"], CLIENT_ID)
    report.check("id_token: подпись, iss, aud=fsp-scout, nonce", identity.get("nonce") == nonce)
    report.check(
        "id_token: номер участника в claim fsp_participant_id",
        identity.get("fsp_participant_id") == participant_id,
        f"sub={identity['sub'][:8]}… — внутренний UUID Keycloak",
    )
    report.check(
        "id_token: без имени и email (минимизация данных)",
        not ({"name", "given_name", "family_name", "email"} & identity.keys()),
        f"region={identity.get('region')}",
    )
    access = verifier.verify(tokens["access_token"], REGISTRY_AUDIENCE)
    report.check(
        "access_token: aud=fsp-registry, scope achievements", "achievements" in access["scope"]
    )
    bearer = {"Authorization": f"Bearer {tokens['access_token']}"}
    own = http.get(f"{REGISTRY_URL}/participants/{participant_id}/achievements", headers=bearer)
    report.check(
        "реестр: свои достижения по токену участника",
        own.status_code == 200 and len(own.json()["achievements"]) == events,
        f"участий {len(own.json().get('achievements', []))}",
    )
    foreign = http.get(f"{REGISTRY_URL}/participants/fsp-000030/achievements", headers=bearer)
    report.check("реестр: чужие достижения закрыты", foreign.status_code == 403)
    forged = {"Authorization": f"Bearer {tokens['access_token'][:-4]}AAAA"}
    tampered = http.get(
        f"{REGISTRY_URL}/participants/{participant_id}/achievements", headers=forged
    )
    report.check("реестр: токен с испорченной подписью → 401", tampered.status_code == 401)

    reuse = http.post(token_url, data=exchange, auth=client_auth)
    report.check("повторный обмен того же кода отклонён", reuse.status_code == 400)
    no_pkce = keycloak_login(authorization_url(None, "s", "n"), login, PERSONA_PASSWORD)
    report.check(
        "вход без PKCE отклонён",
        no_pkce.get("error") == "invalid_request",
        no_pkce.get("error_description", ""),
    )
    wrong_password = keycloak_login(
        authorization_url(pkce_pair()[1], "s", "n"), login, "wrong-password"
    )
    report.check("неверный пароль: кода нет", "code" not in wrong_password)
    foreign_redirect = http.get(
        authorization_url(pkce_pair()[1], "s", "n", redirect_uri="https://evil.example/cb")
    )
    report.check("чужой redirect_uri отклонён", foreign_redirect.status_code == 400)
    bad_secret = http.post(
        token_url, data={"grant_type": "client_credentials"}, auth=(CLIENT_ID, "x")
    )
    report.check("неверный секрет клиента → 401", bad_secret.status_code == 401)


def _demo_sessions(http: httpx.Client) -> Iterator[tuple[str, dict[str, str]]]:
    """Демо-кандидаты без привязки ФСП с заголовком авторизации."""
    for email in DEMO_CANDIDATES:
        response = http.post(
            f"{SCOUT_API}/auth/login", json={"email": email, "password": DEMO_PASSWORD}
        )
        if response.status_code != 200:
            continue
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        if (
            http.get(f"{SCOUT_API}/candidates/me/fsp", headers=headers).json()["state"]
            == "not_linked"
        ):
            yield email, headers


def check_backend(report: Report, http: httpx.Client) -> None:
    """Сквозной путь через бэкенд «Скаута»: привязка, синхронизация, вход, отвязка.

    Берётся свободный демо-кандидат и свободная персона. В конце привязка снимается,
    поэтому стенд остаётся в исходном состоянии.
    """
    email, headers = next(_demo_sessions(http), ("", {}))
    if not report.check("найден демо-кандидат без привязки ФСП", bool(email), email):
        return
    before = http.get(f"{SCOUT_API}/candidates/me/fsp", headers=headers).json()
    linked: dict[str, Any] = {}
    persona = ""
    for persona in SPARE_PERSONAS:
        start = http.post(
            f"{SCOUT_API}/candidates/me/fsp/link", json={"consent": True}, headers=headers
        )
        back = keycloak_login(start.json()["authorization_url"], persona, PERSONA_PASSWORD)
        response = http.post(
            f"{SCOUT_API}/candidates/me/fsp/link/callback",
            json={"code": back.get("code", ""), "state": back.get("state", "")},
            headers=headers,
        )
        if response.status_code == 200:
            linked = response.json()
            break
    if not report.check(
        "привязка ФСП ID через Keycloak",
        linked.get("state") in {"linked", "linked_empty"},
        f"{email} ← {persona}",
    ):
        return
    report.check(
        "номер участника из claim, достижения из реестра",
        linked["participant_id"] == f"fsp-{persona[3:]}",
        f"{linked['participant_id']}, участий {len(linked['achievements'])}, "
        f"регион {linked.get('region')}",
    )
    report.check(
        "индекс профиля учёл ФСП",
        linked["verified_score"]["total"] >= before["verified_score"]["total"],
        f"{before['verified_score']['total']} → {linked['verified_score']['total']}",
    )
    sync = http.post(f"{SCOUT_API}/candidates/me/fsp/sync", headers=headers)
    report.check("повторная синхронизация сервисным токеном", sync.status_code == 200)

    start = http.post(f"{SCOUT_API}/auth/fsp/start").json()
    back = keycloak_login(start["authorization_url"], persona, PERSONA_PASSWORD)
    session = http.post(
        f"{SCOUT_API}/auth/fsp/callback",
        json={"code": back.get("code", ""), "state": back.get("state", "")},
    )
    me = (
        http.get(
            f"{SCOUT_API}/auth/me",
            headers={"Authorization": f"Bearer {session.json()['access_token']}"},
        ).json()
        if session.status_code == 200
        else {}
    )
    report.check("«Войти через ФСП ID» открывает того же кандидата", me.get("email") == email)

    unlinked = http.delete(f"{SCOUT_API}/candidates/me/fsp", headers=headers)
    report.check("отвязка снимает данные ФСП", unlinked.status_code in {200, 204})
    start = http.post(f"{SCOUT_API}/auth/fsp/start").json()
    back = keycloak_login(start["authorization_url"], persona, PERSONA_PASSWORD)
    refused = http.post(
        f"{SCOUT_API}/auth/fsp/callback",
        json={"code": back.get("code", ""), "state": back.get("state", "")},
    )
    report.check("вход непривязанным участником — понятный отказ", refused.status_code == 409)


def main() -> int:
    """Прогоняет проверки против стенда, поднятого `make up-keycloak`."""
    report = Report()
    with httpx.Client(timeout=TIMEOUT_SECONDS) as http:
        try:
            http.get(f"{KEYCLOAK_ISSUER}/.well-known/openid-configuration").raise_for_status()
        except httpx.HTTPError:
            print("Keycloak не отвечает на http://localhost:8081 — запустите `make up-keycloak`")
            return 2
        print("— Протокол OIDC: Keycloak и реестр")
        check_protocol(report, http)
        print("— Бэкенд «Скаута» поверх Keycloak")
        check_backend(report, http)
    total = report.passed + len(report.failed)
    print(f"\nПройдено {report.passed} из {total}")
    return 0 if not report.failed else 1


if __name__ == "__main__":
    sys.exit(main())
