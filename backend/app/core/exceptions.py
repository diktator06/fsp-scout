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


class CompanyRequiredError(ConflictError):
    """Работодатель ещё не заполнил профиль компании: искать и приглашать рано."""

    code = "company_required"
    default_message = "Сначала заполните профиль компании"


class InvitationStateError(ConflictError):
    """Переход приглашения в этот статус невозможен из текущего."""

    code = "invitation_state"
    default_message = "Приглашение уже в другом статусе, обновите страницу"


class InvitationQuotaExceededError(AppError):
    """Компания исчерпала дневную квоту приглашений."""

    status_code = 429
    code = "invitation_quota_exceeded"
    default_message = "Дневной лимит приглашений исчерпан, попробуйте завтра"


class ConsentRequiredError(AppError):
    """Действие требует отдельного согласия по 152-ФЗ, а оно не дано."""

    status_code = 422
    code = "consent_required"
    default_message = "Нужно согласие на обработку данных"


class FspUnavailableError(AppError):
    """ФСП ID или реестр достижений не отвечает или отвечает ошибкой."""

    status_code = 503
    code = "fsp_unavailable"
    default_message = "Сервис ФСП сейчас недоступен, попробуйте позже"


class FspAuthError(AppError):
    """Вход через ФСП ID не удался: просроченный state, неверный код или подпись токена."""

    status_code = 400
    code = "fsp_auth_failed"
    default_message = "Не удалось подтвердить вход через ФСП ID, попробуйте ещё раз"


class FspAlreadyLinkedError(ConflictError):
    """Этот участник ФСП уже привязан к другому профилю."""

    code = "fsp_already_linked"
    default_message = "Этот ФСП ID уже привязан к другому аккаунту"


class FspNotLinkedError(ConflictError):
    """Профиль не связан с ФСП ID, а действие этого требует."""

    code = "fsp_not_linked"
    default_message = "ФСП ID не привязан"


class FspDisabledError(AppError):
    """Интеграция с ФСП выключена в настройках стенда."""

    status_code = 404
    code = "fsp_disabled"
    default_message = "Интеграция с ФСП выключена"


class ApplicationStateError(ConflictError):
    """Переход отклика в этот статус невозможен из текущего."""

    code = "application_state"
    default_message = "Отклик уже в другом статусе, обновите страницу"


class VacancyLimitExceededError(AppError):
    """Компания исчерпала лимит одновременно опубликованных вакансий."""

    status_code = 429
    code = "vacancy_limit_exceeded"
    default_message = "Достигнут лимит опубликованных вакансий для вашего уровня доверия"
