from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-jwt-secret-change-me-in-production"
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Настройки приложения. Значения берутся из переменных окружения и файла `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    app_name: str = "Скаут"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://fsp:fsp@localhost:5432/fsp_scout"
    database_echo: bool = False

    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "fsp-scout"
    jwt_audience: str = "fsp-scout-api"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_ttl_days: int = Field(default=14, ge=1, le=90)
    refresh_cookie_name: str = "fsp_scout_refresh"
    refresh_cookie_secure: bool = False

    email_verification_ttl_hours: int = Field(default=24, ge=1, le=168)
    mail_backend: Literal["smtp", "console"] = "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    smtp_timeout_seconds: float = 10.0
    mail_from: str = "Скаут <no-reply@fsp-scout.local>"

    frontend_url: str = "http://localhost:8080"
    cors_origins: list[str] = ["http://localhost:8080", "http://localhost:5173"]

    rate_limit_enabled: bool = True

    assessment_secret: str = "dev-only-assessment-secret-change-me"
    grade_change_cooldown_days: int = Field(default=90, ge=0, le=365)
    upgrade_retry_days: int = Field(default=30, ge=0, le=365)
    onboarding_daily_sessions: int = Field(default=3, ge=1, le=20)
    assessment_session_minutes: int = Field(default=60, ge=10, le=240)
    item_grace_seconds: int = Field(default=5, ge=0, le=60)

    seed_demo_users: bool = True
    demo_password: str = "ScoutDemo2026"

    swagger_assets_dir: Path = BACKEND_ROOT / "static" / "swagger"

    @model_validator(mode="after")
    def forbid_dev_secret_in_production(self) -> Self:
        """Не даёт запустить production с dev-секретом JWT.

        Секрет по умолчанию нужен, чтобы `docker compose up` работал без настройки.
        На боевом стенде такой секрет означал бы, что любой может выпустить себе токен,
        поэтому лучше упасть при старте, чем работать с ним.
        """
        if self.app_env == "production" and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("В production необходимо задать собственный JWT_SECRET")
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET должен быть не короче 32 символов")
        return self

    @property
    def is_production(self) -> bool:
        """Признак боевого окружения: от него зависят флаги cookie и подробность ошибок."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Возвращает единый экземпляр настроек на весь процесс.

    Кеш нужен, чтобы `.env` читался один раз. В тестах значения подменяются через
    переменные окружения до первого импорта приложения.
    """
    return Settings()
