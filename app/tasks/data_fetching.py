import bz2
import io
import logging
from datetime import datetime, timedelta

import backoff
import httpx
import pandas as pd
from celery import shared_task
from sqlalchemy.orm import Session

import redis
from .. import crud, schemas, models
from ..database import SessionLocal
from ..config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ESI API base URL
ESI_API_BASE_URL = "https://esi.evetech.net/latest"
# EVEref data URL
EVEREF_DATA_URL = "https://data.everef.net/market-history"
# Redis lock timeout (in seconds)
LOCK_TIMEOUT = 60 * 5  # 5 minutes


@backoff.on_exception(backoff.expo, httpx.RequestError, max_tries=5)
def _fetch_esi_url(url: str):
    """Synchronous URL fetcher with backoff for ESI calls."""
    with httpx.Client() as client:
        response = client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.json()

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_and_store_market_history(self, date_str: str):
    db: Session = SessionLocal()
    redis_client = redis.from_url(settings.REDIS_URL)
    try:
        url = f"{EVEREF_DATA_URL}/{date_str[:4]}/market-history-{date_str}.csv.bz2"
        logger.info(f"Fetching market history from {url}")

        response = httpx.get(url, follow_redirects=True)
        response.raise_for_status()

        decompressed_data = bz2.decompress(response.content)
        df = pd.read_csv(io.BytesIO(decompressed_data))

        all_region_ids = {int(rid) for rid in df["region_id"].unique()}
        all_type_ids = {int(tid) for tid in df["type_id"].unique()}

        # Efficiently determine which regions and types are missing from the database
        existing_region_ids = crud.get_existing_region_ids(db, list(all_region_ids))
        missing_region_ids = all_region_ids - existing_region_ids
        if missing_region_ids:
            logger.info(f"Found {len(missing_region_ids)} new regions to process.")
            for region_id in missing_region_ids:
                lock_key = f"lock:region:{region_id}"
                if redis_client.set(lock_key, "1", nx=True, ex=LOCK_TIMEOUT):
                    try:
                        # Double-check if region was created while waiting for the lock
                        if db.query(models.Region).filter(models.Region.region_id == region_id).first():
                            logger.info(f"Region {region_id} was created by another worker. Skipping.")
                            continue

                        region_url = f"{ESI_API_BASE_URL}/universe/regions/{region_id}/"
                        logger.info(f"Fetching region info for {region_id}")
                        data = _fetch_esi_url(region_url)
                        region_create = schemas.RegionCreate(
                            region_id=region_id,
                            name=data.get("name"),
                            description=data.get("description", ""),
                        )
                        crud.get_or_create_region(db, region_create)
                    except Exception as e:
                        logger.error(f"Skipping region {region_id} due to fetch/create error: {e}")
                    finally:
                        redis_client.delete(lock_key)
                else:
                    logger.info(f"Region {region_id} is being processed by another worker. Skipping.")

        existing_type_ids = crud.get_existing_type_ids(db, list(all_type_ids))
        missing_type_ids = all_type_ids - existing_type_ids
        if missing_type_ids:
            logger.info(f"Found {len(missing_type_ids)} new types to process.")
            for type_id in missing_type_ids:
                lock_key = f"lock:type:{type_id}"
                if redis_client.set(lock_key, "1", nx=True, ex=LOCK_TIMEOUT):
                    try:
                         # Double-check if type was created while waiting for the lock
                        if db.query(models.EveType).filter(models.EveType.type_id == type_id).first():
                            logger.info(f"Type {type_id} was created by another worker. Skipping.")
                            continue

                        type_url = f"{ESI_API_BASE_URL}/universe/types/{type_id}/"
                        logger.info(f"Fetching type info for {type_id}")
                        data = _fetch_esi_url(type_url)
                        icon_url = f"https://images.evetech.net/types/{type_id}/icon?size=64"

                        dogma_attributes = [
                            schemas.TypeDogmaAttributeCreate(
                                attribute_id=attr["attribute_id"], value=attr["value"]
                            )
                            for attr in data.get("dogma_attributes", [])
                        ]

                        type_create = schemas.EveTypeCreate(
                            type_id=type_id,
                            name=data.get("name"),
                            description=data.get("description", ""),
                            icon_url=icon_url,
                            capacity=data.get("capacity"),
                            group_id=data.get("group_id"),
                            market_group_id=data.get("market_group_id"),
                            mass=data.get("mass"),
                            packaged_volume=data.get("packaged_volume"),
                            portion_size=data.get("portion_size"),
                            published=data.get("published", False),
                            radius=data.get("radius"),
                            volume=data.get("volume"),
                            dogma_attributes=dogma_attributes,
                        )
                        crud.get_or_create_type(db, type_create)
                    except Exception as e:
                        logger.error(f"Skipping type {type_id} due to fetch/create error: {e}")
                    finally:
                        redis_client.delete(lock_key)
                else:
                    logger.info(f"Type {type_id} is being processed by another worker. Skipping.")

        # Now that dependencies are met, bulk insert market data
        history_records = [
            schemas.MarketHistoryCreate(**row) for row in df.to_dict("records")
        ]
        crud.create_bulk_market_history(db, history_records)
        logger.info(
            f"Successfully stored {len(history_records)} market history records for {date_str}"
        )

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