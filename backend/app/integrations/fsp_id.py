import asyncio
import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import Settings
from app.core.exceptions import FspAuthError, FspUnavailableError

USER_SCOPE = "openid profile achievements"
SERVICE_SCOPE = "registry:read"
TOKEN_REFRESH_MARGIN_SECONDS = 30
CLOCK_LEEWAY_SECONDS = 30


@dataclass(frozen=True, slots=True)
class PkcePair:
    """Пара PKCE: верификатор остаётся на сервере, challenge уходит провайдеру."""

    verifier: str
    challenge: str


@dataclass(frozen=True, slots=True)
class UserTokens:
    """Токены участника после обмена кода авторизации."""

    access_token: str
    id_token: str


@dataclass(frozen=True, slots=True)
class FspIdentity:
    """Проверенные сведения об участнике из id_token."""

    participant_id: str
    name: str | None
    username: str | None
    region: str | None


def read_json(response: httpx.Response) -> dict[str, Any]:
    """Тело ответа как JSON-объект. Нечитаемый ответ означает, что провайдер неисправен."""
    try:
        payload = response.json()
    except ValueError as error:
        raise FspUnavailableError() from error
    if not isinstance(payload, dict):
        raise FspUnavailableError()
    return payload


def new_pkce_pair() -> PkcePair:
    """Создаёт верификатор PKCE и его challenge по методу S256 (RFC 7636)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PkcePair(verifier=verifier, challenge=challenge)


class FspIdClient:
    """Клиент ФСП ID по OpenID Connect — тот же протокол, что у Keycloak.

    Метаданные провайдера, ключи JWKS и сервисный токен кешируются в экземпляре,
    поэтому экземпляр один на процесс. Для перехода на боевой ФСП ID достаточно
    поменять адрес, идентификатор и секрет клиента в настройках.
    """

    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        """Запоминает настройки и, в тестах, подменённый транспорт HTTP."""
        self._settings = settings
        self._transport = transport
        self._metadata: dict[str, Any] | None = None
        self._jwks: jwt.PyJWKSet | None = None
        self._service_token: tuple[str, float] | None = None
        self._lock = asyncio.Lock()

    def http(self) -> httpx.AsyncClient:
        """HTTP-клиент с таймаутом из настроек."""
        return httpx.AsyncClient(
            transport=self._transport, timeout=self._settings.fsp_http_timeout_seconds
        )

    def backchannel(self, url: str) -> str:
        """Переводит публичный адрес провайдера во внутренний для запросов с сервера."""
        issuer = self._settings.fsp_issuer
        if url.startswith(issuer):
            return self._settings.fsp_backchannel_url + url[len(issuer) :]
        return url

    async def _get_json(self, url: str) -> dict[str, Any]:
        """GET-запрос к провайдеру. Сетевые ошибки и 5xx означают недоступность ФСП."""
        try:
            async with self.http() as client:
                response = await client.get(url)
        except httpx.HTTPError as error:
            raise FspUnavailableError() from error
        if response.status_code != httpx.codes.OK:
            raise FspUnavailableError()
        return read_json(response)

    async def metadata(self) -> dict[str, Any]:
        """Метаданные провайдера из discovery.

        `issuer` в документе обязан совпасть с настроенным: иначе токены, подписанные
        чужим провайдером, могли бы пройти проверку (OpenID Connect Discovery, §4.3).
        """
        if self._metadata is None:
            document = await self._get_json(
                f"{self._settings.fsp_backchannel_url}/.well-known/openid-configuration"
            )
            if str(document.get("issuer", "")).rstrip("/") != self._settings.fsp_issuer:
                raise FspUnavailableError("ФСП ID вернул метаданные другого провайдера")
            self._metadata = document
        return self._metadata

    async def authorization_url(
        self, *, state: str, nonce: str, code_challenge: str, redirect_uri: str
    ) -> str:
        """Адрес страницы входа ФСП ID, на который уходит браузер пользователя."""
        metadata = await self.metadata()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._settings.fsp_client_id,
                "redirect_uri": redirect_uri,
                "scope": USER_SCOPE,
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{metadata['authorization_endpoint']}?{query}"

    async def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        """POST на token endpoint с аутентификацией клиента client_secret_basic."""
        metadata = await self.metadata()
        try:
            async with self.http() as client:
                response = await client.post(
                    self.backchannel(metadata["token_endpoint"]),
                    data=form,
                    auth=(self._settings.fsp_client_id, self._settings.fsp_client_secret),
                )
        except httpx.HTTPError as error:
            raise FspUnavailableError() from error
        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise FspUnavailableError()
        payload = read_json(response)
        if response.status_code != httpx.codes.OK:
            raise FspAuthError(details={"provider_error": payload.get("error")})
        return payload

    async def exchange_code(self, code: str, code_verifier: str, redirect_uri: str) -> UserTokens:
        """Обменивает код авторизации на токены участника (с проверкой PKCE у провайдера)."""
        payload = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            }
        )
        if not payload.get("id_token") or not payload.get("access_token"):
            raise FspAuthError()
        return UserTokens(access_token=payload["access_token"], id_token=payload["id_token"])

    async def _signing_key(self, kid: str | None) -> jwt.PyJWK:
        """Публичный ключ по `kid`.

        Если ключ не найден, JWKS перечитывается один раз: провайдер мог сменить ключи
        (эмулятор создаёт новый ключ при каждом перезапуске).
        """
        for attempt in range(2):
            if self._jwks is None or attempt == 1:
                metadata = await self.metadata()
                self._jwks = jwt.PyJWKSet.from_dict(
                    await self._get_json(self.backchannel(metadata["jwks_uri"]))
                )
            for key in self._jwks.keys:
                if key.key_id == kid:
                    return key
        raise FspAuthError("Токен ФСП ID подписан неизвестным ключом")

    async def verify_id_token(self, id_token: str, nonce: str) -> FspIdentity:
        """Проверяет подпись RS256, издателя, получателя, срок и nonce id_token.

        Идентификатор участника реестра берётся из claim `FSP_PARTICIPANT_CLAIM`. У
        эмулятора это `sub`, а в Keycloak `sub` — внутренний UUID пользователя, поэтому
        реестровый номер приходит отдельным claim из атрибута пользователя.
        """
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError as error:
            raise FspAuthError() from error
        key = await self._signing_key(header.get("kid"))
        try:
            claims = jwt.decode(
                id_token,
                key=key.key,
                algorithms=["RS256"],
                audience=self._settings.fsp_client_id,
                issuer=self._settings.fsp_issuer,
                leeway=CLOCK_LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as error:
            raise FspAuthError() from error
        if not hmac.compare_digest(str(claims.get("nonce") or ""), nonce):
            raise FspAuthError()
        participant_id = claims.get(self._settings.fsp_participant_claim)
        if not participant_id:
            raise FspAuthError("В токене ФСП ID нет идентификатора участника реестра")
        return FspIdentity(
            participant_id=str(participant_id),
            name=claims.get("name"),
            username=claims.get("preferred_username"),
            region=claims.get("region"),
        )

    async def service_token(self) -> str:
        """Сервисный токен для чтения реестра (client credentials), с кешем до истечения."""
        async with self._lock:
            now = time.monotonic()
            if self._service_token is not None and self._service_token[1] > now:
                return self._service_token[0]
            payload = await self._token_request(
                {"grant_type": "client_credentials", "scope": SERVICE_SCOPE}
            )
            lifetime = max(0, int(payload.get("expires_in", 60)) - TOKEN_REFRESH_MARGIN_SECONDS)
            self._service_token = (payload["access_token"], now + lifetime)
            return self._service_token[0]

    def forget_service_token(self) -> None:
        """Сбрасывает кеш сервисного токена: реестр его отверг."""
        self._service_token = None
