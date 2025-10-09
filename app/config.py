from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    API_KEY: str
    LOG_LEVEL: str = "INFO"
    TESTING: bool = False

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()