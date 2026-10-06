import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, parseaddr
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    """Письмо, готовое к отправке."""

    to: str
    subject: str
    text_body: str
    html_body: str | None = None


class MailDeliveryError(Exception):
    """Почтовый сервер недоступен или отклонил письмо."""


class Mailer(Protocol):
    """Интерфейс отправки писем: сервисы не знают, SMTP это, консоль или заглушка в тестах."""

    async def send(self, message: OutgoingEmail) -> None:
        """Отправляет письмо или бросает `MailDeliveryError`."""


class SmtpMailer:
    """Отправка через SMTP. В демо-стенде письма ловит Mailpit, в production это реальный сервер."""

    def __init__(self, settings: Settings) -> None:
        """Сохраняет параметры подключения."""
        self._settings = settings

    async def send(self, message: OutgoingEmail) -> None:
        """Отправляет письмо в отдельном потоке.

        Стандартный `smtplib` синхронный. Отдельная зависимость ради асинхронного
        SMTP не нужна: писем мало, а `to_thread` не блокирует event loop.
        """
        await asyncio.to_thread(self._send_blocking, message)

    def _send_blocking(self, message: OutgoingEmail) -> None:
        """Собирает MIME-сообщение и передаёт его SMTP-серверу."""
        settings = self._settings
        mime = MimeMessage()
        sender_name, sender_address = parseaddr(settings.mail_from)
        mime["From"] = formataddr((sender_name, sender_address))
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text_body)
        if message.html_body:
            mime.add_alternative(message.html_body, subtype="html")

        try:
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
            ) as client:
                if settings.smtp_use_tls:
                    client.starttls()
                if settings.smtp_username and settings.smtp_password:
                    client.login(settings.smtp_username, settings.smtp_password)
                client.send_message(mime)
        except (OSError, smtplib.SMTPException) as exc:
            raise MailDeliveryError(str(exc)) from exc


class ConsoleMailer:
    """Пишет письма в лог вместо отправки. Удобно, когда SMTP под рукой нет."""

    async def send(self, message: OutgoingEmail) -> None:
        """Логирует тему и текст письма. Адрес не логируем, чтобы не тащить ПДн в логи."""
        logger.info("Письмо «%s»:\n%s", message.subject, message.text_body)


def build_mailer(settings: Settings) -> Mailer:
    """Выбирает реализацию отправки по настройке `MAIL_BACKEND`."""
    if settings.mail_backend == "console":
        return ConsoleMailer()
    return SmtpMailer(settings)
