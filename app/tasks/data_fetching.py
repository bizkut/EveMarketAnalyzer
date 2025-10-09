import bz2
import io
import logging
from datetime import datetime, timedelta

import backoff
import httpx
import pandas as pd
from celery import shared_task, group, chain, chord
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


@shared_task(max_retries=3, default_retry_delay=60)
def create_region(region_id: int):
    """Fetches and creates a single region if it doesn't exist."""
    db: Session = SessionLocal()
    try:
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
        logger.error(f"Failed to create region {region_id}: {e}")
    finally:
        db.close()


@shared_task(max_retries=3, default_retry_delay=60)
def create_type(type_id: int):
    """Fetches and creates a single type if it doesn't exist."""
    db: Session = SessionLocal()
    try:
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
        logger.error(f"Failed to create type {type_id}: {e}")
    finally:
        db.close()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_market_history(self, date_str: str):
    """Fetches and stores market history for a given date."""
    db: Session = SessionLocal()
    try:
        url = f"{EVEREF_DATA_URL}/{date_str[:4]}/market-history-{date_str}.csv.bz2"
        logger.info(f"Processing market history from {url}")

        response = httpx.get(url, follow_redirects=True)
        response.raise_for_status()

        decompressed_data = bz2.decompress(response.content)
        df = pd.read_csv(io.BytesIO(decompressed_data))

        history_records = [
            schemas.MarketHistoryCreate(**row) for row in df.to_dict("records")
        ]
        crud.create_bulk_market_history(db, history_records)
        logger.info(
            f"Successfully stored {len(history_records)} market history records for {date_str}"
        )

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error processing {date_str}: {e}")
        if e.response.status_code == 404:
            return
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"An error occurred while processing market history for {date_str}: {e}")
        self.retry(exc=e)
    finally:
        db.close()


@shared_task
def get_ids_from_date_file(date_str: str) -> dict:
    """
    Downloads a market history file for a given date, extracts unique
    region and type IDs, and returns them as JSON-serializable lists.
    """
    try:
        url = f"{EVEREF_DATA_URL}/{date_str[:4]}/market-history-{date_str}.csv.bz2"
        logger.info(f"Gathering IDs from {url}")
        response = httpx.get(url, follow_redirects=True)
        response.raise_for_status()
        decompressed_data = bz2.decompress(response.content)
        df = pd.read_csv(io.BytesIO(decompressed_data), usecols=["region_id", "type_id"])
        # Ensure NumPy types are converted to standard Python types for JSON serialization
        region_ids = [int(rid) for rid in df["region_id"].unique()]
        type_ids = [int(tid) for tid in df["type_id"].unique()]
        return {"region_ids": region_ids, "type_ids": type_ids}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"Market history not found for {date_str}. Skipping.")
            return {"region_ids": [], "type_ids": []}
        raise e
    except Exception as e:
        logger.error(f"Failed to process file for {date_str}: {e}")
        return {"region_ids": [], "type_ids": []}


@shared_task
def dispatch_market_history_tasks(dates: list[str]):
    """Dispatches the market history processing tasks in a group."""
    market_history_tasks = group(process_market_history.si(date) for date in dates)
    market_history_tasks.delay()
    logger.info(f"Dispatched market history processing for {len(dates)} dates.")


@shared_task
def aggregate_and_dispatch_dependencies(id_results: list, dates: list[str]):
    """
    Receives results from ID gathering, determines missing dependencies,
    and uses a chord to ensure dependencies are created before history is processed.
    """
    db: Session = SessionLocal()
    try:
        all_region_ids = set()
        all_type_ids = set()
        for result in id_results:
            all_region_ids.update(result.get("region_ids", []))
            all_type_ids.update(result.get("type_ids", []))

        # Determine missing regions and types
        existing_region_ids = crud.get_existing_region_ids(db, list(all_region_ids))
        missing_region_ids = all_region_ids - existing_region_ids
        logger.info(f"Found {len(missing_region_ids)} new regions to create.")

        existing_type_ids = crud.get_existing_type_ids(db, list(all_type_ids))
        missing_type_ids = all_type_ids - existing_type_ids
        logger.info(f"Found {len(missing_type_ids)} new types to create.")

        # Combine all dependency creation tasks into a single group
        dependency_creation_tasks = group(
            *[create_region.si(rid) for rid in sorted(list(missing_region_ids))],
            *[create_type.si(tid) for tid in sorted(list(missing_type_ids))]
        )

        if dependency_creation_tasks:
            # Use a chord to ensure all dependencies are created before processing history
            callback = dispatch_market_history_tasks.si(dates=dates)
            workflow = chord(header=dependency_creation_tasks, body=callback)
            workflow.delay()
            logger.info("Dependency creation workflow started with a chord.")
        else:
            # If there are no dependencies to create, just dispatch the history tasks directly
            logger.info("No new dependencies to create. Proceeding directly to market history processing.")
            dispatch_market_history_tasks.delay(dates=dates)

    except Exception as e:
        logger.error(f"An error occurred during dependency aggregation: {e}")
    finally:
        db.close()


@shared_task
def orchestrate_market_data_load(dates: list[str]):
    """
    Orchestrates the entire data loading process using a non-blocking chord.
    1. Gathers all required region and type IDs in parallel.
    2. A callback task then creates missing dependencies and processes history.
    """
    id_gathering_tasks = group(get_ids_from_date_file.s(date) for date in dates)

    # Create a chord: when all ID gathering tasks are done, call the aggregator
    # The aggregator also needs the original list of dates for the final step.
    callback = aggregate_and_dispatch_dependencies.s(dates=dates)

    workflow = chord(header=id_gathering_tasks, body=callback)
    workflow.delay()
    logger.info("Orchestration workflow started with a chord.")


@shared_task
def initial_data_load():
    """
    Dispatches orchestration for the last 365 days.
    """
    today = datetime.utcnow().date()
    dates_to_fetch = [
        (today - timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(365)
    ]
    orchestrate_market_data_load.delay(dates=dates_to_fetch)
    logger.info("Initial data load orchestrated for the last 365 days.")


@shared_task
def daily_update_task():
    """
    Dispatches orchestration for the previous day.
    """
    yesterday_str = (datetime.utcnow().date() - timedelta(days=1)).strftime("%Y-%m-%d")
    orchestrate_market_data_load.delay(dates=[yesterday_str])
    logger.info(f"Daily update orchestrated for {yesterday_str}.")