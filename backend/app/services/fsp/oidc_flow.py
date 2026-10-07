import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import FspAuthError, FspDisabledError
from app.crud import oidc_flow_state_crud
from app.integrations.fsp_gateway import FspGateway
from app.integrations.fsp_id import FspIdentity, UserTokens, new_pkce_pair
from app.models.fsp import OidcFlowPurpose
from app.schemas.fsp import FspAuthorizationRead, FspCallback


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class OidcFlow:
    """Вход через ФСП ID по коду авторизации с PKCE: начало и завершение.

    Общий для привязки профиля и для входа в аккаунт. Верификатор PKCE и nonce
    хранятся только на сервере, браузер видит лишь state и challenge.
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        gateway: FspGateway,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        """Получает сессию БД, настройки, шлюз ФСП и источник времени."""
        self._session = session
        self._settings = settings
        self._gateway = gateway
        self._clock = clock

    def require_enabled(self) -> None:
        """Интеграция может быть выключена на стенде без ФСП."""
        if not self._settings.fsp_enabled:
            raise FspDisabledError()

    def redirect_uri(self, purpose: OidcFlowPurpose) -> str:
        """Адрес возврата во фронтенд; он же зарегистрирован у провайдера."""
        path = (
            self._settings.fsp_link_redirect_path
            if purpose is OidcFlowPurpose.LINK
            else self._settings.fsp_login_redirect_path
        )
        return f"{self._settings.frontend_url.rstrip('/')}{path}"

    async def begin(
        self, purpose: OidcFlowPurpose, user_id: uuid.UUID | None
    ) -> FspAuthorizationRead:
        """Создаёт state, nonce и PKCE и возвращает адрес страницы входа ФСП ID.

        Транзакцию не фиксирует: это делает вызывающий сценарий.
        """
        self.require_enabled()
        now = self._clock()
        pkce = new_pkce_pair()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        redirect_uri = self.redirect_uri(purpose)
        url = await self._gateway.identity.authorization_url(
            state=state, nonce=nonce, code_challenge=pkce.challenge, redirect_uri=redirect_uri
        )
        await oidc_flow_state_crud.purge_expired(self._session, now)
        ttl = timedelta(minutes=self._settings.fsp_flow_ttl_minutes)
        await oidc_flow_state_crud.create(
            self._session,
            {
                "state": state,
                "purpose": purpose,
                "user_id": user_id,
                "code_verifier": pkce.verifier,
                "nonce": nonce,
                "redirect_uri": redirect_uri,
                "expires_at": now + ttl,
            },
        )
        return FspAuthorizationRead(authorization_url=url, expires_in=int(ttl.total_seconds()))

    async def finish(
        self, purpose: OidcFlowPurpose, payload: FspCallback, user_id: uuid.UUID | None
    ) -> tuple[FspIdentity, UserTokens]:
        """Проверяет state, обменивает код и проверяет id_token.

        State погашается и фиксируется до обращения к провайдеру: даже если обмен
        не удастся, повторить тот же ответ ФСП ID уже нельзя. Начатое одним
        пользователем нельзя завершить в сессии другого.
        """
        self.require_enabled()
        flow = await oidc_flow_state_crud.pop(self._session, payload.state)
        await self._session.commit()
        if (
            flow is None
            or flow.purpose is not purpose
            or flow.expires_at < self._clock()
            or flow.user_id != user_id
        ):
            raise FspAuthError("Вход через ФСП ID устарел или уже завершён, начните заново")
        tokens = await self._gateway.identity.exchange_code(
            payload.code, flow.code_verifier, flow.redirect_uri
        )
        identity = await self._gateway.identity.verify_id_token(tokens.id_token, flow.nonce)
        return identity, tokens
