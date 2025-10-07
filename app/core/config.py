from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra='ignore'
    )

    PROJECT_NAME: str = "EVE Online Market Analysis"
    API_V1_STR: str = "/api"

    # Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    @field_validator("DATABASE_URL", mode='before')
    @classmethod
    def assemble_db_connection(cls, v: Any, values) -> Any:
        if isinstance(v, str):
            return v

        data = values.data
        user = data.get("POSTGRES_USER")
        password = data.get("POSTGRES_PASSWORD")
        host = data.get("POSTGRES_HOST")
        port = data.get("POSTGRES_PORT")
        db = data.get("POSTGRES_DB")
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int = 6379

    # Celery
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    @field_validator("CELERY_BROKER_URL", mode='before')
    @classmethod
    def assemble_celery_broker(cls, v: Any, values) -> Any:
        if isinstance(v, str):
            return v
        data = values.data
        host = data.get("REDIS_HOST")
        port = data.get("REDIS_PORT")
        return f"redis://{host}:{port}/0"

    @field_validator("CELERY_RESULT_BACKEND", mode='before')
    @classmethod
    def assemble_celery_backend(cls, v: Any, values) -> Any:
        if isinstance(v, str):
            return v
        data = values.data
        host = data.get("REDIS_HOST")
        port = data.get("REDIS_PORT")
        return f"redis://{host}:{port}/0"

    # API Security
    API_KEY: str

    # Logging
    LOG_LEVEL: str = "INFO"

settings = Settings()