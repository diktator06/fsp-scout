import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_exception_handlers
from app.api.openapi import install_openapi
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import SessionFactory, engine
from app.services.integrations.dispatcher import WebhookDispatcher

OPENAPI_URL = "/api/openapi.json"
DOCS_URL = "/api/docs"
SWAGGER_ASSETS_URL = "/api/docs-assets"

API_DESCRIPTION = """
API платформы «Скаут» — подбор ИТ-специалистов с обратной механикой:
работодатель сам находит кандидата в категоризированной базе и приглашает его
с обязательной вилкой зарплаты.

**Аутентификация.** `POST /api/v1/auth/login` возвращает access-токен (15 минут) и ставит
refresh-токен в httpOnly-cookie. Access-токен передаётся в заголовке
`Authorization: Bearer <token>`. Claims совместимы с Keycloak (`realm_access.roles`).

**Ошибки** приходят в едином формате `{"error": {"code", "message", "details"}}`:
по `code` фронтенд выбирает реакцию, `message` можно показывать пользователю.
"""

OPENAPI_TAGS = [
    {"name": "system", "description": "Служебные методы: проверка работоспособности"},
    {
        "name": "auth",
        "description": "Регистрация с подтверждением email, вход, обновление и завершение сессии",
    },
    {
        "name": "dictionaries",
        "description": "Справочники: специализации, грейды, категории, отрасли, навыки. "
        "Чтение открыто всем, изменение доступно только методисту",
    },
    {
        "name": "candidate",
        "description": "Кабинет кандидата: профиль, PDF-профиль, приватность и согласия",
    },
    {
        "name": "assessment",
        "description": "Опрос и адаптивное тестирование: уникальные экземпляры заданий из "
        "калиброванного банка, оценка θ по IRT, присвоение категории",
    },
    {
        "name": "trust",
        "description": "Жалобы кандидатов на недобросовестных работодателей",
    },
    {
        "name": "moderation",
        "description": "Модерация: решения по жалобам, ограничение компаний, уровень доверия",
    },
    {
        "name": "integrations",
        "description": "Интеграция с ATS работодателя: подписанные вебхуки (HMAC-SHA256) "
        "с повторами, журнал доставок, песочница-получатель и выгрузка кандидатов в CSV/JSON",
    },
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Жизненный цикл приложения.

    При старте запускается фоновый диспетчер вебхуков для ATS работодателей, при
    остановке он доотправляет текущую пачку, и пул соединений с БД закрывается.
    """
    settings = get_settings()
    stop = asyncio.Event()
    dispatcher_task: asyncio.Task[None] | None = None
    if settings.webhook_dispatcher_enabled:
        dispatcher = WebhookDispatcher(SessionFactory, settings)
        dispatcher_task = asyncio.create_task(dispatcher.run_forever(stop))
    yield
    stop.set()
    if dispatcher_task is not None:
        await dispatcher_task
    await engine.dispose()


def _mount_offline_docs(app: FastAPI, settings: Settings) -> None:
    """Подключает Swagger UI так, чтобы он работал без интернета.

    По умолчанию FastAPI грузит Swagger UI с CDN, а стенд должен быть полностью
    автономным. Docker-образ кладёт статику `swagger-ui-dist` в `static/swagger`. Если
    её нет (локальный запуск без сборки образа), используем CDN, чтобы документация
    всё равно открывалась.
    """
    assets_dir = settings.swagger_assets_dir
    local_assets = (assets_dir / "swagger-ui-bundle.js").is_file()
    if local_assets:
        app.mount(SWAGGER_ASSETS_URL, StaticFiles(directory=assets_dir), name="swagger-assets")

    async def swagger_ui() -> HTMLResponse:
        """Страница Swagger UI."""
        if local_assets:
            return get_swagger_ui_html(
                openapi_url=OPENAPI_URL,
                title=f"{settings.app_name} — API",
                swagger_js_url=f"{SWAGGER_ASSETS_URL}/swagger-ui-bundle.js",
                swagger_css_url=f"{SWAGGER_ASSETS_URL}/swagger-ui.css",
                swagger_favicon_url=f"{SWAGGER_ASSETS_URL}/favicon-32x32.png",
                swagger_ui_parameters={
                    "persistAuthorization": True,
                    "displayRequestDuration": True,
                },
            )
        return get_swagger_ui_html(
            openapi_url=OPENAPI_URL,
            title=f"{settings.app_name} — API",
            swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True},
        )

    app.add_api_route(DOCS_URL, swagger_ui, include_in_schema=False, methods=["GET"])


def create_app() -> FastAPI:
    """Собирает приложение: роутеры, CORS, обработчики ошибок и документацию."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.app_version,
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        openapi_url=OPENAPI_URL,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    _mount_offline_docs(app, settings)
    install_openapi(app)
    return app


app = create_app()
