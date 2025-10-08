import os
from fastapi import FastAPI
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager

from app.database import get_db, Base, engine
from app.models.market_data import MarketHistory
from app.tasks.worker import update_all_data_task
from app.api.endpoints import router as api_router
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # --- Startup ---
    if os.environ.get("ENV") != "test":
        print("Running in non-test mode. Initializing database and services.")
        # Create database tables
        Base.metadata.create_all(bind=engine)

        # Initialize Redis Cache
        redis = aioredis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}", encoding="utf8", decode_responses=True)
        FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")

        # Check for initial data fetch
        db: Session = next(get_db())
        try:
            if db.query(MarketHistory).first() is None:
                print("No market history found. Triggering initial data fetch.")
                update_all_data_task.delay()
        finally:
            db.close()

    yield

    # --- Shutdown ---
    # Clean up resources if needed
    pass

app = FastAPI(
    title="EVE Online Market Analyzer",
    description="An API for analyzing the EVE Online market.",
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to the EVE Online Market Analyzer API"}

@app.get("/api/status")
def get_status():
    """
    Returns the current status of the API.
    """
    return {"status": "ok"}