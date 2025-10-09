from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    API_KEY: str
    LOG_LEVEL: str = "INFO"
    TESTING: bool = False

    class Config:
        env_file = ".env"

settings = Settings()