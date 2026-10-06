import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import generate_opaque_token, hash_opaque_token
from app.crud import email_verification_token_crud
from app.integrations.email_templates import render_email
from app.integrations.mailer import MailDeliveryError, Mailer, OutgoingEmail
from app.models.user import User

logger = logging.getLogger(__name__)


class EmailVerificationService:
    """Выпуск ссылок подтверждения email и отправка писем."""

    def __init__(self, session: AsyncSession, settings: Settings, mailer: Mailer) -> None:
        """Получает сессию БД, настройки и способ отправки писем."""
        self._session = session
        self._settings = settings
        self._mailer = mailer

    async def issue_token(self, user: User, *, now: datetime) -> str:
        """Создаёт новый токен подтверждения и гасит предыдущие.

        Возвращается «сырой» токен для ссылки, в базу попадает только его хеш.
        Метод не фиксирует транзакцию: это делает вызывающий сценарий.
        """
        await email_verification_token_crud.invalidate_active(self._session, user.id, now)
        raw_token = generate_opaque_token()
        await email_verification_token_crud.create(
            self._session,
            {
                "user_id": user.id,
                "token_hash": hash_opaque_token(raw_token),
                "expires_at": now + timedelta(hours=self._settings.email_verification_ttl_hours),
            },
        )
        return raw_token

    def build_link(self, raw_token: str) -> str:
        """Ссылка на страницу фронтенда, которая подтвердит email по токену."""
        base = self._settings.frontend_url.rstrip("/")
        return f"{base}/auth/verify?{urlencode({'token': raw_token})}"

    async def send(self, user: User, raw_token: str) -> bool:
        """Отправляет письмо со ссылкой и сообщает, удалось ли.

        Сбой почты не должен ломать регистрацию: аккаунт уже создан, а письмо можно
        запросить повторно. Поэтому ошибку логируем и возвращаем `False`.
        """
        text_body, html_body = render_email(
            "verify_email",
            email=user.email,
            verification_link=self.build_link(raw_token),
            ttl_hours=self._settings.email_verification_ttl_hours,
        )
        message = OutgoingEmail(
            to=user.email,
            subject="Подтвердите email в «Скауте»",
            text_body=text_body,
            html_body=html_body,
        )
        try:
            await self._mailer.send(message)
        except MailDeliveryError:
            logger.warning("Не удалось отправить письмо подтверждения пользователю %s", user.id)
            return False
        return True
