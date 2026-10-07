from fastapi import FastAPI

from app import oidc, registry_api


def create_app() -> FastAPI:
    """Эмулятор ФСП ID и реестра достижений.

    Реализует тот же протокол, что Keycloak: OIDC с PKCE и RS256, client credentials для
    сервисного доступа. Чтобы подключить настоящий ФСП ID, бэкенду «Скаута» достаточно
    поменять адреса и секрет клиента.
    """
    app = FastAPI(
        title="ФСП ID и реестр достижений (эмулятор)",
        version="0.1.0",
        description="Демонстрационный провайдер для стенда «Скаута». Данные участников вымышлены.",
    )
    app.include_router(oidc.router)
    app.include_router(registry_api.router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Проверка живости для docker compose."""
        return {"status": "ok"}

    return app


app = create_app()
