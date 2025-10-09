import logging
from contextlib import asynccontextmanager

from celery.schedules import crontab
from fastapi import FastAPI

from . import crud, models
from .api import endpoints
from .celery_worker import celery
from .config import settings
from .database import SessionLocal, engine
from .tasks.data_fetching import initial_data_load
from .tasks.analysis import perform_market_analysis

# Configure logging
logging.basicConfig(level=settings.LOG_LEVEL.upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    # Create database tables
    models.Base.metadata.create_all(bind=engine)

    if not settings.TESTING:
        db = SessionLocal()
        try:
            # Check if the database is empty and trigger initial data load if it is
            if crud.is_database_empty(db):
                logger.info("Database is empty. Triggering initial data load.")
                initial_data_load.delay()

            # Check if the analysis table is empty and trigger analysis if it is
            if crud.is_analysis_table_empty(db):
                logger.info("Market analysis table is empty. Triggering analysis.")
                perform_market_analysis.delay()
        finally:
            db.close()

    yield

    logger.info("Shutting down...")


app = FastAPI(title="Eve Market Analyzer", lifespan=lifespan)

# Include API router
app.include_router(endpoints.router)


# Add Celery Beat schedule
@app.on_event("startup")
def startup_event():
    # Schedule daily updates at 11:10 UTC
    celery.add_periodic_task(
        crontab(hour=11, minute=10),
        "app.tasks.data_fetching.daily_update_task",
        name="daily market data update",
    )


@app.get("/")
def read_root():
    return {"message": "Welcome to the EVE Online Market Analyzer API"}