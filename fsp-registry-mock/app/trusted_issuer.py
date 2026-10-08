import json
import urllib.request
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import jwt

from app.config import get_settings

JWKS_TIMEOUT_SECONDS = 5

type JwksFetcher = Callable[[str], dict[str, Any]]


def fetch_jwks(url: str) -> dict[str, Any]:
    """JWKS провайдера по HTTP — стандартной библиотекой, без лишних зависимостей."""
    with urllib.request.urlopen(url, timeout=JWKS_TIMEOUT_SECONDS) as response:
        payload: dict[str, Any] = json.loads(response.read())
    return payload


class TrustedIssuer:
    """Внешний провайдер ФСП ID (Keycloak), чьим токенам реестр доверяет.

    Реестр в целевой архитектуре — отдельный ресурсный сервер: он не выпускает токены,
    а проверяет чужие по JWKS провайдера. У Keycloak `sub` — внутренний UUID
    пользователя, поэтому номер участника реестра берётся из отдельного claim и
    подставляется на место `sub` — дальше реестр работает с токеном как обычно.
    """

    def __init__(
        self,
        issuer: str,
        jwks_url: str,
        participant_claim: str,
        fetch: JwksFetcher = fetch_jwks,
    ) -> None:
        """Запоминает издателя, адрес JWKS, claim участника и способ загрузки ключей."""
        self.issuer = issuer.rstrip("/")
        self._jwks_url = jwks_url
        self._participant_claim = participant_claim
        self._fetch = fetch
        self._jwks: jwt.PyJWKSet | None = None

    def _key(self, kid: str | None) -> jwt.PyJWK:
        """Ключ по `kid`; при промахе JWKS перечитывается один раз — провайдер мог сменить ключ."""
        for attempt in range(2):
            if self._jwks is None or attempt == 1:
                self._jwks = jwt.PyJWKSet.from_dict(self._fetch(self._jwks_url))
            for key in self._jwks.keys:
                if key.key_id == kid:
                    return key
        raise jwt.InvalidKeyError("Неизвестный ключ подписи")

    def verify(self, token: str, audience: str) -> dict[str, Any]:
        """Проверяет подпись, срок, издателя и аудиторию; номер участника кладёт в `sub`."""
        key = self._key(jwt.get_unverified_header(token).get("kid"))
        claims: dict[str, Any] = jwt.decode(
            token, key.key, algorithms=["RS256"], audience=audience, issuer=self.issuer
        )
        participant = claims.get(self._participant_claim)
        return {**claims, "sub": str(participant)} if participant else claims


@lru_cache
def get_trusted_issuer() -> TrustedIssuer | None:
    """Доверенный провайдер из настроек или None, если эмулятор сам себе провайдер."""
    settings = get_settings()
    if not settings.trusted_issuer or not settings.trusted_jwks_url:
        return None
    return TrustedIssuer(
        settings.trusted_issuer, settings.trusted_jwks_url, settings.trusted_participant_claim
    )
