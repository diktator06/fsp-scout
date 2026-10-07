import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings

REGISTRY_AUDIENCE = "fsp-registry"


def achievement(
    event_id: str,
    *,
    result: str = "participant",
    event_date: str = "2026-03-01",
    level: str = "regional",
    discipline: str = "продуктовое программирование",
    online: bool = False,
    place: int | None = 15,
    total: int | None = 120,
) -> dict[str, Any]:
    """Запись реестра в формате API эмулятора."""
    return {
        "event_id": event_id,
        "event_name": f"Кубок «{event_id}»",
        "event_level": level,
        "discipline": discipline,
        "event_date": event_date,
        "participation_format": "individual",
        "team_name": None,
        "team_role": None,
        "place": place,
        "participants_total": total,
        "result_status": result,
        "is_online": online,
        "rating_points": 50.0,
        "protocol_url": f"https://fsp-registry.example/protocols/{event_id}",
    }


@dataclass
class FakeFsp:
    """Поддельный ФСП ID и реестр для тестов: тот же протокол, что у эмулятора.

    Токены подписываются настоящим ключом RS256, поэтому бэкенд проверяет подпись,
    издателя, получателя и nonce так же, как с живым провайдером.
    """

    settings: Settings
    participants: dict[str, dict[str, Any]] = field(default_factory=dict)
    codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    registry_down: bool = False
    forged_nonce: str | None = None
    calls: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Создаёт первый ключ подписи."""
        self.rotate_key()

    def rotate_key(self) -> None:
        """Меняет ключ подписи, как эмулятор при перезапуске."""
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = secrets.token_hex(4)

    def add(
        self,
        participant_id: str,
        achievements: list[dict[str, Any]] | None = None,
        *,
        sport_rank: str | None = "КМС",
    ) -> str:
        """Добавляет участника реестра."""
        self.participants[participant_id] = {
            "participant_id": participant_id,
            "region": "Москва",
            "sport_rank": sport_rank,
            "achievements": achievements or [],
        }
        return participant_id

    def authorize(self, authorization_url: str, participant_id: str) -> tuple[str, str]:
        """Имитирует вход участника на странице ФСП ID; возвращает code и state."""
        query = {
            key: values[0] for key, values in parse_qs(urlparse(authorization_url).query).items()
        }
        assert query["client_id"] == self.settings.fsp_client_id
        assert query["code_challenge_method"] == "S256"
        assert query["response_type"] == "code"
        code = secrets.token_urlsafe(16)
        self.codes[code] = {
            "participant_id": participant_id,
            "challenge": query["code_challenge"],
            "nonce": query["nonce"],
            "redirect_uri": query["redirect_uri"],
        }
        return code, query["state"]

    def sign(self, claims: dict[str, Any]) -> str:
        """Подписывает токен текущим ключом."""
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": self.kid})

    def _json(self, payload: dict[str, Any], status: int = 200) -> httpx.Response:
        """Ответ JSON."""
        return httpx.Response(status, json=payload)

    def _client_ok(self, request: httpx.Request) -> bool:
        """Проверка client_secret_basic."""
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("basic "):
            return False
        client_id, _, secret = base64.b64decode(header[6:]).decode().partition(":")
        return (
            client_id == self.settings.fsp_client_id and secret == self.settings.fsp_client_secret
        )

    def _token(self, request: httpx.Request) -> httpx.Response:
        """Token endpoint: код авторизации с PKCE или client credentials."""
        if not self._client_ok(request):
            return self._json({"error": "invalid_client"}, 401)
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        now = int(time.time())
        issuer = self.settings.fsp_issuer
        if form["grant_type"] == "client_credentials":
            token = self.sign(
                {
                    "iss": issuer,
                    "sub": "fsp-scout",
                    "aud": REGISTRY_AUDIENCE,
                    "scope": "registry:read",
                    "iat": now,
                    "exp": now + 600,
                }
            )
            return self._json({"access_token": token, "expires_in": 600, "token_type": "Bearer"})
        issued = self.codes.pop(form.get("code", ""), None)
        verifier = form.get("code_verifier", "")
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        if (
            issued is None
            or issued["challenge"] != challenge
            or issued["redirect_uri"] != form.get("redirect_uri")
        ):
            return self._json({"error": "invalid_grant"}, 400)
        participant_id = issued["participant_id"]
        base = {"iss": issuer, "sub": participant_id, "iat": now, "exp": now + 600}
        return self._json(
            {
                "access_token": self.sign(
                    {**base, "aud": REGISTRY_AUDIENCE, "scope": "openid profile achievements"}
                ),
                "id_token": self.sign(
                    {
                        **base,
                        "aud": self.settings.fsp_client_id,
                        "nonce": self.forged_nonce or issued["nonce"],
                        "name": "Участник ФСП",
                        "region": "Москва",
                    }
                ),
                "token_type": "Bearer",
                "expires_in": 600,
            }
        )

    def _registry(self, request: httpx.Request, path: str) -> httpx.Response:
        """API реестра: список участников и достижения участника."""
        if self.registry_down:
            return httpx.Response(503, text="maintenance")
        token = request.headers.get("authorization", "")[7:]
        claims = jwt.decode(
            token,
            self.key.public_key(),
            algorithms=["RS256"],
            audience=REGISTRY_AUDIENCE,
            issuer=self.settings.fsp_issuer,
        )
        if path == "/participants":
            return self._json(
                {
                    "items": [
                        {"id": pid, "events": len(item["achievements"]), "demo_persona": False}
                        for pid, item in self.participants.items()
                    ],
                    "total": len(self.participants),
                }
            )
        participant_id = path.split("/")[2]
        own = claims["sub"] == participant_id
        if not own and claims.get("scope") != "registry:read":
            return self._json({"detail": "forbidden"}, 403)
        if participant_id not in self.participants:
            return self._json({"detail": "not found"}, 404)
        return self._json(self.participants[participant_id])

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Маршрутизация запросов бэкенда к поддельному провайдеру."""
        path = request.url.path
        self.calls.append(path)
        issuer = self.settings.fsp_issuer
        if path == "/.well-known/openid-configuration":
            return self._json(
                {
                    "issuer": issuer,
                    "authorization_endpoint": f"{issuer}/authorize",
                    "token_endpoint": f"{issuer}/token",
                    "jwks_uri": f"{issuer}/jwks.json",
                }
            )
        if path == "/jwks.json":
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
            return self._json({"keys": [{**jwk, "kid": self.kid, "alg": "RS256", "use": "sig"}]})
        if path == "/token":
            return self._token(request)
        if path.startswith("/participants"):
            return self._registry(request, path)
        return httpx.Response(404)

    def transport(self) -> httpx.MockTransport:
        """Транспорт HTTP для шлюза ФСП в тестах."""
        return httpx.MockTransport(self.handle)
