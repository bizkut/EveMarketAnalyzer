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
async def fetch_url(url: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response


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

        # Pre-fetch existing regions and types to reduce DB queries inside the loop
        all_region_ids = {int(rid) for rid in df['region_id'].unique()}
        all_type_ids = {int(tid) for tid in df['type_id'].unique()}

        existing_regions = crud.get_existing_region_ids(db, list(all_region_ids))
        existing_types = crud.get_existing_type_ids(db, list(all_type_ids))

        new_regions_to_fetch = all_region_ids - existing_regions
        new_types_to_fetch = all_type_ids - existing_types

        for region_id in new_regions_to_fetch:
            fetch_region_info.delay(region_id)

        for type_id in new_types_to_fetch:
            fetch_type_info.delay(type_id)

        # Bulk insert market data
        history_records = [
            schemas.MarketHistoryCreate(**row) for row in df.to_dict('records')
        ]
        crud.create_bulk_market_history(db, history_records)
        logger.info(f"Successfully stored {len(history_records)} market history records for {date_str}")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching {date_str}: {e}")
        # Don't retry for 404 Not Found, as the data for the day may not exist
        if e.response.status_code == 404:
            return
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"An error occurred while processing market history for {date_str}: {e}")
        self.retry(exc=e)
    finally:
        db.close()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_region_info(self, region_id: int):
    db: Session = SessionLocal()
    try:
        if crud.get_region(db, region_id):
            logger.info(f"Region {region_id} already exists. Skipping.")
            return

        url = f"{ESI_API_BASE_URL}/universe/regions/{region_id}/"
        logger.info(f"Fetching region info for {region_id}")
        response = httpx.get(url)
        response.raise_for_status()
        data = response.json()

        region_create = schemas.RegionCreate(
            region_id=region_id,
            name=data.get('name'),
            description=data.get('description', '')
        )
        crud.get_or_create_region(db, region_create)
        logger.info(f"Successfully stored region {region_id}")

    except httpx.RequestError as exc:
        logger.error(f"Error fetching region {region_id}: {exc}")
        self.retry(exc=exc)
    finally:
        db.close()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_type_info(self, type_id: int):
    db: Session = SessionLocal()
    try:
        if crud.get_type(db, type_id):
            logger.info(f"Type {type_id} already exists. Skipping.")
            return

        url = f"{ESI_API_BASE_URL}/universe/types/{type_id}/"
        logger.info(f"Fetching type info for {type_id}")
        response = httpx.get(url)
        response.raise_for_status()
        data = response.json()

        icon_url = f"https://images.evetech.net/types/{type_id}/icon"

        type_create = schemas.EveTypeCreate(
            type_id=type_id,
            name=data.get('name'),
            description=data.get('description', ''),
            icon_url=icon_url
        )
        crud.get_or_create_type(db, type_create)
        logger.info(f"Successfully stored type {type_id}")

    except httpx.RequestError as exc:
        logger.error(f"Error fetching type {type_id}: {exc}")
        self.retry(exc=exc)
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