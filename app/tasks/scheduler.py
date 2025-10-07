from celery import chain
from celery.schedules import crontab
from app.tasks.worker import celery_app
from app.tasks.data_fetching import fetch_and_store_regions, fetch_and_store_item_types, fetch_and_store_market_history
from app.tasks.analysis import analyze_market_data
from app.database import SessionLocal
from app.models import Region, ItemType, AnalyzedItem
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
    Initializes data fetching on startup if the database is empty.
    Checks for regions, item types, and analyzed data to determine if
    the initial data fetch should run.
    """
    logger.info("Checking if initial data fetch is needed...")
    db = SessionLocal()
    try:
        # Check if any of the essential tables are empty
        no_regions = db.query(Region).first() is None
        no_item_types = db.query(ItemType).first() is None
        no_analyzed_data = db.query(AnalyzedItem).first() is None

        if no_regions and no_item_types and no_analyzed_data:
            logger.info("No data found in the database. Starting initial data fetch.")
            run_daily_tasks.delay()
        else:
            logger.info("Data already exists. Skipping initial fetch.")
    finally:
        db.close()