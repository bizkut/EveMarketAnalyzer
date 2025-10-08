import asyncio
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
from app.services import market_data, analysis
from app.database import Base, engine, SessionLocal

celery_app = Celery(
    "tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

@celery_app.task(name="tasks.update_all_data")
def update_all_data_task():
    """
    Chain together all data update tasks.
    """
    asyncio.run(market_data.update_regions())
    asyncio.run(market_data.update_all_item_types())
    asyncio.run(market_data.update_market_history())
    # After updating data, trigger analysis
    analyze_market_data_task.delay()


@celery_app.task(name="tasks.analyze_market_data")
def analyze_market_data_task():
    """
    Analyzes the market data.
    """
    db = SessionLocal()
    try:
        analysis.analyze_and_store_market_data(db)
    finally:
        db.close()


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Schedule daily data fetching at 11:15 UTC
    sender.add_periodic_task(
        crontab(hour=11, minute=15),
        update_all_data_task.s(),
        name='update all market data daily',
    )
    # Schedule daily analysis at a slightly later time
    sender.add_periodic_task(
        crontab(hour=11, minute=45), # Run analysis after data fetching should have completed
        analyze_market_data_task.s(),
        name='analyze market data daily',
    )

if __name__ == "__main__":
    celery_app.start()