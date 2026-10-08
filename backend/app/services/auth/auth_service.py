import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
    VerificationTokenError,
)
from app.core.security import (
    hash_opaque_token,
    hash_password_async,
    password_needs_rehash,
    verify_password_async,
)
from app.crud import consent_crud, email_verification_token_crud, refresh_session_crud, user_crud
from app.integrations.mailer import Mailer
from app.models.auth_session import SessionRevokeReason
from app.models.consent import ConsentType
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth.email_verification import EmailVerificationService
from app.services.auth.tokens import ClientContext, IssuedTokens, issue_session_tokens
from app.services.consents import PERSONAL_DATA_POLICY_VERSION

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    """Итог регистрации."""

    user: User
    verification_email_sent: bool


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    """Пользователь и выданная ему пара токенов."""

    user: User
    tokens: IssuedTokens


class AuthService:
    """Сценарии аутентификации: регистрация, подтверждение email, вход, обновление и выход.

    Каждый публичный метод — одна транзакция: CRUD только делает `flush`, а фиксирует
    изменения сервис в конце сценария.
    """

    def __init__(self, session: AsyncSession, settings: Settings, mailer: Mailer) -> None:
        """Собирает зависимости сценариев."""
        self._session = session
        self._settings = settings
        self._verification = EmailVerificationService(session, settings, mailer)

    async def register(self, payload: RegisterRequest, client: ClientContext) -> RegistrationResult:
        """Создаёт аккаунт, фиксирует согласие на обработку ПДн и отправляет письмо.

        Письмо уходит после `commit`: отправлять ссылку на аккаунт, которого в базе ещё
        (или уже) нет, нельзя. Повторная регистрация того же email между проверкой и
        вставкой отсекается уникальным индексом, поэтому `IntegrityError` превращаем
        в ту же доменную ошибку.
        """
        now = datetime.now(UTC)
        if await user_crud.get_by_email(self._session, payload.email):
            raise EmailAlreadyRegisteredError()
        password_hash = await hash_password_async(payload.password)

        try:
            user = await user_crud.create_local(
                self._session,
                email=payload.email,
                password_hash=password_hash,
                role=payload.role,
            )
            await consent_crud.grant(
                self._session,
                user_id=user.id,
                consent_type=ConsentType.PERSONAL_DATA_PROCESSING,
                document_version=PERSONAL_DATA_POLICY_VERSION,
                ip_address=client.ip_address,
            )
            raw_token = await self._verification.issue_token(user, now=now)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EmailAlreadyRegisteredError() from exc

        logger.info("Зарегистрирован пользователь %s с ролью %s", user.id, user.role.value)
        email_sent = await self._verification.send(user, raw_token)
        return RegistrationResult(user=user, verification_email_sent=email_sent)

    async def verify_email(self, raw_token: str, client: ClientContext) -> AuthenticatedSession:
        """Подтверждает email по токену из письма и сразу открывает сессию.

        Автоматический вход после подтверждения избавляет человека от повторного ввода
        пароля: он только что доказал владение почтой.
        """
        now = datetime.now(UTC)
        token = await email_verification_token_crud.get_by_hash(
            self._session, hash_opaque_token(raw_token)
        )
        if token is None:
            raise VerificationTokenError()
        if token.used_at is not None:
            raise VerificationTokenError(
                "Ссылка уже использована. Если email подтверждён, просто войдите в аккаунт",
                details={"reason": "used"},
            )
        if token.expires_at <= now:
            raise VerificationTokenError(
                "Срок действия ссылки истёк, запросите новое письмо", details={"reason": "expired"}
            )

        user = await user_crud.get(self._session, token.user_id)
        if user is None:
            raise VerificationTokenError()
        if not user.is_active:
            raise AccountDisabledError()

        await email_verification_token_crud.mark_used(self._session, token, now)
        if not user.is_email_verified:
            await user_crud.mark_email_verified(self._session, user, now)
        await user_crud.register_login(self._session, user, now)
        tokens, _ = await issue_session_tokens(
            self._session, user, self._settings, client=client, now=now
        )
        await self._session.commit()
        logger.info("Подтверждён email пользователя %s", user.id)
        return AuthenticatedSession(user=user, tokens=tokens)

    async def resend_verification(self, email: str) -> None:
        """Повторно отправляет письмо подтверждения.

        Ответ API одинаков в любом случае (аккаунта нет, уже подтверждён, письмо ушло),
        чтобы по нему нельзя было проверить, зарегистрирован ли адрес.
        """
        user = await user_crud.get_by_email(self._session, email)
        if user is None or user.is_email_verified or not user.is_active:
            return
        raw_token = await self._verification.issue_token(user, now=datetime.now(UTC))
        await self._session.commit()
        await self._verification.send(user, raw_token)

    async def login(self, payload: LoginRequest, client: ClientContext) -> AuthenticatedSession:
        """Вход по email и паролю.

        Порядок проверок важен: сначала пароль, потом статус аккаунта. Иначе по тексту
        ошибки «email не подтверждён» можно было бы узнать о существовании аккаунта,
        не зная пароля.
        """
        now = datetime.now(UTC)
        user = await user_crud.get_by_email(self._session, payload.email)
        password_hash = user.password_hash if user else None
        verified = await verify_password_async(payload.password, password_hash)
        if user is None or not verified:
            raise InvalidCredentialsError()
        if not user.is_active:
            raise AccountDisabledError()
        if not user.is_email_verified:
            raise EmailNotVerifiedError()

        rehashed = None
        if password_hash and password_needs_rehash(password_hash):
            rehashed = await hash_password_async(payload.password)
        await user_crud.register_login(self._session, user, now, new_password_hash=rehashed)
        tokens, _ = await issue_session_tokens(
            self._session, user, self._settings, client=client, now=now
        )
        await self._session.commit()
        return AuthenticatedSession(user=user, tokens=tokens)

    async def refresh(self, raw_refresh_token: str, client: ClientContext) -> AuthenticatedSession:
        """Ротация refresh-токена: старая сессия отзывается, выдаётся новая пара.

        Если предъявлен уже отозванный при ротации токен, значит им пользуется кто-то
        ещё (украденная cookie или повтор запроса злоумышленником). В этом случае
        отзываем всё семейство: и у злоумышленника, и у владельца сессия обрывается,
        владелец просто войдёт заново.
        """
        now = datetime.now(UTC)
        current = await refresh_session_crud.get_by_hash(
            self._session, hash_opaque_token(raw_refresh_token)
        )
        if current is None:
            raise InvalidTokenError()

        if current.revoked_at is not None:
            if current.revoke_reason == SessionRevokeReason.ROTATED:
                await refresh_session_crud.revoke_family(
                    self._session,
                    current.family_id,
                    reason=SessionRevokeReason.REUSE_DETECTED,
                    at=now,
                )
                await self._session.commit()
                logger.warning(
                    "Повторное использование refresh-токена, семейство %s отозвано",
                    current.family_id,
                )
            raise InvalidTokenError()

        if current.expires_at <= now:
            await refresh_session_crud.revoke(
                self._session, current, reason=SessionRevokeReason.EXPIRED, at=now
            )
            await self._session.commit()
            raise InvalidTokenError("Сессия истекла, войдите заново")

        user = await user_crud.get(self._session, current.user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError()

        tokens, replacement = await issue_session_tokens(
            self._session, user, self._settings, client=client, now=now, family_id=current.family_id
        )
        await refresh_session_crud.revoke(
            self._session,
            current,
            reason=SessionRevokeReason.ROTATED,
            at=now,
            replaced_by_id=replacement.id,
        )
        await self._session.commit()
        return AuthenticatedSession(user=user, tokens=tokens)

    async def logout(self, raw_refresh_token: str | None) -> None:
        """Завершает текущую сессию. Повторный выход или выход без cookie не считается ошибкой."""
        if not raw_refresh_token:
            return
        current = await refresh_session_crud.get_by_hash(
            self._session, hash_opaque_token(raw_refresh_token)
        )
        if current is None or current.revoked_at is not None:
            return
        await refresh_session_crud.revoke(
            self._session, current, reason=SessionRevokeReason.LOGOUT, at=datetime.now(UTC)
        )
        await self._session.commit()
