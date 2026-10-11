from typing import Literal

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import SessionDep, SettingsDep
from app.api.errors import error_responses
from app.crud.system import ping_database

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Состояние сервиса."""

    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        **error_responses(),
        503: {"model": HealthResponse, "description": "База данных недоступна"},
    },
    summary="Проверка работоспособности",
)
async def health(session: SessionDep, settings: SettingsDep) -> HealthResponse | JSONResponse:
    """Отвечает 200, если сервис и база работают. Используется healthcheck'ом Docker."""
    try:
        database_ok = await ping_database(session)
    except (SQLAlchemyError, OSError):
        database_ok = False
    if database_ok:
        return HealthResponse(status="ok", database="ok", version=settings.app_version)
    payload = HealthResponse(
        status="degraded", database="unavailable", version=settings.app_version
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload.model_dump()
    )
