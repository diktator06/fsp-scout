from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, PersonalDataServiceDep, SettingsDep
from app.api.errors import error_responses
from app.api.rate_limit import RateLimiter
from app.api.v1.auth import clear_refresh_cookie
from app.schemas.personal_data import AccountDeletionRequest, PersonalDataExport

router = APIRouter(prefix="/account", tags=["account"])

export_limiter = RateLimiter(limit=10, window_seconds=3600)
deletion_limiter = RateLimiter(limit=5, window_seconds=3600)


@router.get(
    "/personal-data",
    response_model=PersonalDataExport,
    responses=error_responses(401, 429),
    summary="Выгрузка моих персональных данных",
    dependencies=[Depends(export_limiter)],
)
async def export_personal_data(user: CurrentUser, service: PersonalDataServiceDep) -> JSONResponse:
    """Все данные о пользователе одним JSON-файлом (ст. 14 152-ФЗ)."""
    export = await service.export(user)
    filename = f"scout-personal-data-{datetime.now(UTC).date().isoformat()}.json"
    return JSONResponse(
        content=export.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 422, 429),
    summary="Удалить аккаунт и все данные",
    dependencies=[Depends(deletion_limiter)],
)
async def delete_account(
    payload: AccountDeletionRequest,
    user: CurrentUser,
    service: PersonalDataServiceDep,
    settings: SettingsDep,
) -> Response:
    """Необратимое удаление: отзыв согласия на обработку ПДн и уничтожение данных."""
    await service.delete_account(user, payload)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response, settings)
    return response
