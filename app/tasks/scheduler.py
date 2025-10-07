from celery import chain
from celery.schedules import crontab
from app.tasks.worker import celery_app
from app.tasks.data_fetching import fetch_and_store_regions, fetch_and_store_item_types, fetch_and_store_market_history
from app.tasks.analysis import analyze_market_data
from app.database import SessionLocal
from app.models import Region, AnalyzedItem
import logging

logger = logging.getLogger(__name__)

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Schedule daily data fetching and analysis at 11:10 UTC
    sender.add_periodic_task(
        crontab(hour=11, minute=10),
        run_daily_tasks.s(),
        name='daily data fetch and analysis'
    )

@celery_app.task
def run_daily_tasks():
    """Chain of tasks to be run daily."""
    task_chain = chain(
        fetch_and_store_regions.s(),
        fetch_and_store_item_types.s(),
        fetch_and_store_market_history.s(),
        analyze_market_data.s()
    )
    task_chain()
    logger.info("Daily tasks scheduled.")

async def init_scheduler():
    """
    Initializes data fetching on startup if there is no analyzed data.
    This is a more reliable check than looking for regions, as it ensures
    that the entire data pipeline has completed at least once.
    """
    logger.info("Checking if initial data fetch is needed...")
    db = SessionLocal()
    try:
        # Check if there is any data in the analyzed_items table
        if db.query(AnalyzedItem).first() is None:
            logger.info("No analyzed data found. Starting initial data fetch.")
            # Run the tasks sequentially
            run_daily_tasks.delay()
        else:
            logger.info("Analyzed data already exists. Skipping initial fetch.")
    finally:
        db.close()