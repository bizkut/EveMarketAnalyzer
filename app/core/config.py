from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Explicitly load variables from .env file into the environment
load_dotenv()

class Settings(BaseSettings):
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str
    REDIS_HOST: str
    REDIS_PORT: int
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    API_KEY: str
    LOG_LEVEL: str
    ESI_BASE_URL: str
    USER_AGENT: str

    # Pydantic will now read the variables from the environment,
    # which have been loaded by the load_dotenv() call above.
    model_config = SettingsConfigDict(extra='ignore')

settings = Settings()