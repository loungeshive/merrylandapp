from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    jwt_secret: str = "local-development-secret-change-before-deploying"
    access_token_minutes: int = 30
    web_origins: str = "http://localhost:3000"
    google_client_ids: str = ""
    admin_username: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_USERNAME", "ADMIN_EMAIL"),
    )
    admin_password: str = ""
    upload_directory: str = "uploads"
    demo_payment_enabled: bool = True

    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.web_origins.split(",") if origin.strip()]

    @property
    def google_allowed_client_ids(self) -> list[str]:
        return [client_id.strip() for client_id in self.google_client_ids.split(",") if client_id.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
