import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)

_ERROR_DESCRIPTIONS: dict[int, str] = {
    400: "Некорректный запрос",
    401: "Требуется вход или токен недействителен",
    403: "Недостаточно прав",
    404: "Объект не найден",
    409: "Конфликт с текущим состоянием данных",
    422: "Ошибка валидации входных данных",
    429: "Превышен лимит запросов",
}

_HTTP_ERROR_CODES: dict[int, str] = {
    404: "not_found",
    405: "method_not_allowed",
    401: "authentication_required",
    403: "permission_denied",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Описание ошибок эндпоинта для OpenAPI: все они приходят в формате `ErrorResponse`."""
    return {
        code: {"model": ErrorResponse, "description": _ERROR_DESCRIPTIONS.get(code, "Ошибка")}
        for code in status_codes
    }


def _error_payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    """Тело ответа с ошибкой в едином формате."""
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _humanize_validation_message(message: str) -> str:
    """Убирает служебный префикс Pydantic у сообщений собственных валидаторов.

    Наши валидаторы пишут понятный русский текст, а Pydantic добавляет к нему
    «Value error, ». Пользователю этот префикс не нужен.
    """
    return message.removeprefix("Value error, ")


async def handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    """Превращает доменное исключение в ответ с его кодом и статусом."""
    assert isinstance(exc, AppError)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(exc.code, exc.message, exc.details),
    )


async def handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    """Ошибки валидации запроса: список полей с сообщениями, удобный для подсветки в форме."""
    assert isinstance(exc, RequestValidationError)
    fields = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body"),
            "message": _humanize_validation_message(str(error["msg"])),
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_error_payload(
            "request_validation_error", "Проверьте правильность заполнения полей", fields
        ),
    )


async def handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    """Стандартные HTTP-ошибки Starlette (неизвестный маршрут, неверный метод) в нашем формате."""
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_ERROR_CODES.get(exc.status_code, "http_error")
    message = _ERROR_DESCRIPTIONS.get(exc.status_code, str(exc.detail))
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(code, message),
        headers=getattr(exc, "headers", None),
    )


async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    """Непредвиденная ошибка: подробности только в лог, клиенту нейтральный текст."""
    logger.exception("Необработанная ошибка", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_payload("internal_error", "Внутренняя ошибка сервиса, попробуйте позже"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Подключает обработчики ошибок к приложению."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
