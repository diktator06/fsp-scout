from typing import Any, ClassVar


class AppError(Exception):
    """Базовое доменное исключение.

    Сервисы бросают только наследников этого класса, а HTTP-слой единообразно
    превращает их в ответ `{"error": {"code", "message", "details"}}`. Благодаря этому
    в роутерах нет `try/except` ради кодов ответа.
    """

    status_code: ClassVar[int] = 400
    code: ClassVar[str] = "bad_request"
    default_message: ClassVar[str] = "Некорректный запрос"

    def __init__(
        self, message: str | None = None, *, details: dict[str, Any] | None = None
    ) -> None:
        """Сохраняет текст для пользователя и машиночитаемые детали ошибки."""
        self.message = message or self.default_message
        self.details: dict[str, Any] = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    """Объект не найден или недоступен текущему пользователю."""

    status_code = 404
    code = "not_found"
    default_message = "Объект не найден"


class ConflictError(AppError):
    """Операция конфликтует с текущим состоянием данных."""

    status_code = 409
    code = "conflict"
    default_message = "Операция конфликтует с текущим состоянием данных"


class EmailAlreadyRegisteredError(ConflictError):
    """Пользователь с таким email уже существует."""

    code = "email_already_registered"
    default_message = "Пользователь с таким email уже зарегистрирован"


class DomainValidationError(AppError):
    """Данные синтаксически корректны, но нарушают бизнес-правило."""

    status_code = 422
    code = "validation_error"
    default_message = "Данные не прошли проверку"


class AuthenticationError(AppError):
    """Запрос требует аутентификации."""

    status_code = 401
    code = "authentication_required"
    default_message = "Требуется вход в систему"


class InvalidCredentialsError(AuthenticationError):
    """Неверная пара email/пароль. Текст намеренно не уточняет, что именно не так."""

    code = "invalid_credentials"
    default_message = "Неверный email или пароль"


class InvalidTokenError(AuthenticationError):
    """Токен доступа или обновления недействителен."""

    code = "invalid_token"
    default_message = "Сессия недействительна, войдите заново"


class PermissionDeniedError(AppError):
    """У пользователя нет прав на операцию."""

    status_code = 403
    code = "permission_denied"
    default_message = "Недостаточно прав для выполнения операции"


class EmailNotVerifiedError(PermissionDeniedError):
    """Вход до подтверждения email запрещён: этого требует ТЗ (§2.2, п. 4)."""

    code = "email_not_verified"
    default_message = "Подтвердите email: ссылка отправлена в письме при регистрации"


class AccountDisabledError(PermissionDeniedError):
    """Аккаунт заблокирован."""

    code = "account_disabled"
    default_message = "Аккаунт заблокирован"


class VerificationTokenError(AppError):
    """Ссылка подтверждения недействительна, просрочена или уже использована."""

    code = "invalid_verification_token"
    default_message = "Ссылка подтверждения недействительна"


class RateLimitExceededError(AppError):
    """Слишком много запросов с одного адреса."""

    status_code = 429
    code = "rate_limit_exceeded"
    default_message = "Слишком много запросов, попробуйте позже"
