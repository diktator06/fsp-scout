from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from app.oidc import SERVICE_SCOPE, ClaimsDep, RegistryDep

router = APIRouter(prefix="/participants", tags=["registry"])


def _scopes(claims: dict[str, Any]) -> set[str]:
    """Набор scope из access-токена."""
    return set(str(claims.get("scope", "")).split())


def _summary(participant: dict[str, Any]) -> dict[str, Any]:
    """Краткая сводка участника для сервисного списка."""
    achievements = participant["achievements"]
    return {
        "id": participant["id"],
        "region": participant["region"],
        "sport_rank": participant["sport_rank"],
        "events": len(achievements),
        "results": sum(1 for item in achievements if item["result_status"] in {"winner", "prize"}),
        "finals": sum(1 for item in achievements if item["result_status"] == "finalist"),
        "demo_persona": bool(participant.get("persona")),
    }


@router.get("")
def list_participants(
    claims: ClaimsDep,
    registry: RegistryDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Список участников для сервисного клиента (scope registry:read)."""
    if SERVICE_SCOPE not in _scopes(claims):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужен сервисный доступ к реестру")
    page = registry.participants[offset : offset + limit]
    return {"items": [_summary(item) for item in page], "total": len(registry.participants)}


@router.get("/{participant_id}/achievements")
def achievements(participant_id: str, claims: ClaimsDep, registry: RegistryDep) -> dict[str, Any]:
    """Участия и результаты участника.

    Доступно сервису с scope registry:read или самому участнику по его токену. Имя
    участника в ответ не входит: платформе достаточно идентификатора и результатов
    (минимизация персональных данных).
    """
    own = claims.get("sub") == participant_id and "achievements" in _scopes(claims)
    if not own and SERVICE_SCOPE not in _scopes(claims):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к достижениям участника")
    participant = registry.by_id(participant_id)
    if participant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Участник не найден")
    return {
        "participant_id": participant["id"],
        "region": participant["region"],
        "sport_rank": participant["sport_rank"],
        "generated_at": datetime.now(UTC).isoformat(),
        "achievements": participant["achievements"],
    }
