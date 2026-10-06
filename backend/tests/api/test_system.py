from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.seed.seeders import seed_reference_data


async def test_health_reports_database_status(client: AsyncClient) -> None:
    """`/health` отвечает 200 и сообщает, что база доступна."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"


async def test_unknown_route_uses_common_error_format(client: AsyncClient) -> None:
    """Даже для несуществующего маршрута ошибка приходит в едином формате."""
    response = await client.get("/api/v1/no-such-route")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Объект не найден", "details": {}}
    }


async def test_openapi_and_docs_are_available(client: AsyncClient) -> None:
    """Спецификация OpenAPI и Swagger UI доступны, у эндпоинтов есть описания на русском."""
    spec = (await client.get("/api/openapi.json")).json()
    assert spec["info"]["title"] == "Скаут API"
    register = spec["paths"]["/api/v1/auth/register"]["post"]
    assert register["summary"] == "Регистрация кандидата или работодателя"
    assert "409" in register["responses"]

    assert "HTTPValidationError" not in spec["components"]["schemas"]
    skills_422 = spec["paths"]["/api/v1/dictionaries/skills"]["get"]["responses"]["422"]
    assert skills_422["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }

    docs = await client.get("/api/docs")
    assert docs.status_code == 200
    assert "swagger-ui" in docs.text


async def test_seeding_is_idempotent(db_session: AsyncSession) -> None:
    """Повторное сидирование поверх уже наполненной базы ничего не создаёт и не меняет."""
    report = await seed_reference_data(db_session)
    assert report.created == {}
    assert report.updated == {}
