import bz2
import io
import logging
from datetime import datetime, timedelta

import backoff
import httpx
import pandas as pd
from celery import shared_task
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import SessionLocal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ESI API base URL
ESI_API_BASE_URL = "https://esi.evetech.net/latest"
# EVEref data URL
EVEREF_DATA_URL = "https://data.everef.net/market-history"


@backoff.on_exception(backoff.expo, httpx.RequestError, max_tries=5)
def _fetch_esi_url(url: str):
    """Synchronous URL fetcher with backoff for ESI calls."""
    with httpx.Client() as client:
        response = client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.json()

def _ensure_region_exists(db: Session, region_id: int):
    """
    Fetches and stores region info if it doesn't already exist.
    Relies on an atomic CRUD operation to handle race conditions.
    """
    # First, check if the region exists to avoid unnecessary API calls.
    if db.query(models.Region).filter(models.Region.region_id == region_id).first():
        return

    # If not, fetch from API and use the atomic get_or_create function.
    url = f"{ESI_API_BASE_URL}/universe/regions/{region_id}/"
    logger.info(f"Fetching region info for {region_id}")
    data = _fetch_esi_url(url)

    region_create = schemas.RegionCreate(
        region_id=region_id,
        name=data.get('name'),
        description=data.get('description', '')
    )
    crud.get_or_create_region(db, region_create)

def _ensure_type_exists(db: Session, type_id: int):
    """
    Fetches and stores type info if it doesn't already exist.
    Relies on an atomic CRUD operation to handle race conditions.
    """
    if db.query(models.EveType).filter(models.EveType.type_id == type_id).first():
        return

    url = f"{ESI_API_BASE_URL}/universe/types/{type_id}/"
    logger.info(f"Fetching type info for {type_id}")
    data = _fetch_esi_url(url)

    icon_url = f"https://images.evetech.net/types/{type_id}/icon"

    type_create = schemas.EveTypeCreate(
        type_id=type_id,
        name=data.get('name'),
        description=data.get('description', ''),
        icon_url=icon_url
    )
    crud.get_or_create_type(db, type_create)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_and_store_market_history(self, date_str: str):
    db: Session = SessionLocal()
    try:
        url = f"{EVEREF_DATA_URL}/{date_str[:4]}/market-history-{date_str}.csv.bz2"
        logger.info(f"Fetching market history from {url}")

        response = httpx.get(url, follow_redirects=True)
        response.raise_for_status()

        decompressed_data = bz2.decompress(response.content)
        df = pd.read_csv(io.BytesIO(decompressed_data))

        all_region_ids = {int(rid) for rid in df['region_id'].unique()}
        all_type_ids = {int(tid) for tid in df['type_id'].unique()}

        # Ensure all required regions and types exist, creating them if necessary.
        for region_id in all_region_ids:
            _ensure_region_exists(db, region_id)

        for type_id in all_type_ids:
            _ensure_type_exists(db, type_id)

        # Now that dependencies are met, bulk insert market data
        history_records = [
            schemas.MarketHistoryCreate(**row) for row in df.to_dict('records')
        ]
        crud.create_bulk_market_history(db, history_records)
        logger.info(f"Successfully stored {len(history_records)} market history records for {date_str}")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching {date_str}: {e}")
        if e.response.status_code == 404:
            return
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"An error occurred while processing market history for {date_str}: {e}")
        self.retry(exc=e)
    finally:
        db.close()


@shared_task
def initial_data_load():
    """
    Fetches market history for the last 365 days.
    """
    today = datetime.utcnow().date()
    for i in range(365):
        date_to_fetch = today - timedelta(days=i + 1)
        date_str = date_to_fetch.strftime("%Y-%m-%d")
        fetch_and_store_market_history.delay(date_str)
    logger.info("Initial data load task dispatched for the last 365 days.")


@shared_task
def daily_update_task():
    """
    Fetches market history for the previous day.
    """
    yesterday = datetime.utcnow().date() - timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")
    fetch_and_store_market_history.delay(date_str)
    logger.info(f"Daily update task dispatched for {date_str}.")