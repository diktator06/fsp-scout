from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки эмулятора. Адреса и секрет клиента совпадают с настройками бэкенда «Скаута»."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    public_url: str = "http://localhost:8090"
    client_id: str = "fsp-scout"
    client_secret: str = "dev-only-fsp-client-secret"
    redirect_uris: list[str] = [
        "http://localhost:8080/c/fsp/callback",
        "http://localhost:8080/auth/fsp/callback",
        "http://localhost:5173/c/fsp/callback",
        "http://localhost:5173/auth/fsp/callback",
    ]
    demo_password: str = "FspDemo2026"
    code_ttl_seconds: int = 120
    token_ttl_seconds: int = 600

    @property
    def issuer(self) -> str:
        """Идентификатор провайдера без завершающего слеша: он попадает в claim `iss`."""
        return self.public_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Единый экземпляр настроек на процесс."""
    return Settings()
