from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

_ERROR_REF = {"$ref": "#/components/schemas/ErrorResponse"}
_FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")


def build_openapi_schema(app: FastAPI) -> dict[str, Any]:
    """Строит OpenAPI и приводит описание ошибок валидации к фактическому формату.

    FastAPI по умолчанию описывает 422 своей схемой `HTTPValidationError`, а наш
    обработчик отвечает `ErrorResponse` (`{"error": {...}}`). Документация обязана
    совпадать с поведением, иначе сгенерированный клиент фронтенда ошибётся в типах.
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            validation = operation.get("responses", {}).get("422")
            if validation is None:
                continue
            validation["description"] = "Ошибка валидации входных данных"
            validation["content"] = {"application/json": {"schema": _ERROR_REF}}

    components = schema.get("components", {}).get("schemas", {})
    for name in _FASTAPI_VALIDATION_SCHEMAS:
        components.pop(name, None)

    app.openapi_schema = schema
    return schema


def install_openapi(app: FastAPI) -> None:
    """Подменяет генератор OpenAPI приложения на исправленный."""

    def openapi() -> dict[str, Any]:
        """Отдаёт кешированную спецификацию."""
        return build_openapi_schema(app)

    app.openapi = openapi  # type: ignore[method-assign]
