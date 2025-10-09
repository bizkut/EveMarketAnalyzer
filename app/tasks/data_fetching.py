import bz2
import io
import logging
import os
from datetime import datetime, timedelta

import backoff
import httpx
import pandas as pd
from celery import shared_task, group, chord
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import SessionLocal
from ..config import settings
from .analysis import perform_market_analysis

# Configure logging
logging.basicConfig(level=settings.LOG_LEVEL.upper())
logger = logging.getLogger(__name__)

# ESI API base URL
ESI_API_BASE_URL = "https://esi.evetech.net/latest"
# EVEref data URL
EVEREF_DATA_URL = "https://data.everef.net/market-history"
# Path for temporary data files
TEMP_DATA_DIR = "/app/tmp/market_data"


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
def process_market_history(self, file_path: str, date_str: str):
    """Reads a temporary market history file, stores its data, and cleans up."""
    if not file_path or not os.path.exists(file_path):
        logger.warning(f"File path {file_path} not valid for date {date_str}, skipping.")
        return

    db: Session = SessionLocal()
    try:
        logger.info(f"Processing market history from local file: {file_path}")

        with bz2.open(file_path, "rt") as bz2f:
            df = pd.read_csv(bz2f)

        history_records = [
            schemas.MarketHistoryCreate(**row) for row in df.to_dict("records")
        ]
        crud.create_bulk_market_history(db, history_records)
        logger.info(
            f"Successfully stored {len(history_records)} market history records for {date_str}"
        )
    except Exception as e:
        logger.error(
            f"An error occurred while processing market history for {date_str} from {file_path}: {e}"
        )
        self.retry(exc=e)
    finally:
        db.close()
        # Clean up the temporary file
        try:
            os.remove(file_path)
            logger.info(f"Removed temporary file: {file_path}")
        except OSError as e:
            logger.error(f"Error removing temporary file {file_path}: {e}")


@shared_task
def download_and_extract_ids(date_str: str) -> dict:
    """
    Downloads a market history file, saves it temporarily, extracts unique
    IDs, and returns them along with the file path.
    """
    os.makedirs(TEMP_DATA_DIR, exist_ok=True)
    file_path = os.path.join(TEMP_DATA_DIR, f"market-history-{date_str}.csv.bz2")

    try:
        url = f"{EVEREF_DATA_URL}/{date_str[:4]}/market-history-{date_str}.csv.bz2"
        logger.info(f"Downloading {url} to {file_path}")

        with httpx.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)

        with bz2.open(file_path, "rt") as bz2f:
            df = pd.read_csv(bz2f, usecols=["region_id", "type_id"])

        region_ids = [int(rid) for rid in df["region_id"].unique()]
        type_ids = [int(tid) for tid in df["type_id"].unique()]

        return {
            "region_ids": region_ids,
            "type_ids": type_ids,
            "file_path": file_path,
            "date": date_str,
        }

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"Market history not found for {date_str}. Skipping.")
            return {"region_ids": [], "type_ids": [], "file_path": None, "date": date_str}
        raise e
    except Exception as e:
        logger.error(f"Failed to process file for {date_str}: {e}")
        # Clean up failed download
        if os.path.exists(file_path):
            os.remove(file_path)
        return {"region_ids": [], "type_ids": [], "file_path": None, "date": date_str}


@shared_task
def dispatch_market_history_tasks(processing_info: list):
    """
    Dispatches market history processing tasks and chains the market analysis
    task to run upon their completion.
    """
    if not processing_info:
        logger.info("No market history tasks to dispatch.")
        return

    # Create a group of tasks to process each market history file
    header = group(
        process_market_history.si(info["file_path"], info["date"])
        for info in processing_info
    )

    # Define the market analysis task as the callback
    callback = perform_market_analysis.si()

    # Use a chord to execute the analysis after all history tasks are done
    workflow = chord(header, callback)
    workflow.delay()
    logger.info(
        f"Dispatched market history processing for {len(processing_info)} files, "
        f"with market analysis chained as a callback."
    )


@shared_task
def aggregate_and_dispatch_dependencies(results: list):
    """
    Receives download results, determines missing dependencies, and uses a
    chord to ensure dependencies are created before history is processed from local files.
    """
    db: Session = SessionLocal()
    try:
        all_region_ids = set()
        all_type_ids = set()
        # Filter out failed downloads and collect file paths
        valid_results = [res for res in results if res and res.get("file_path")]
        processing_info = [
            {"file_path": res["file_path"], "date": res["date"]} for res in valid_results
        ]

        for res in valid_results:
            all_region_ids.update(res.get("region_ids", []))
            all_type_ids.update(res.get("type_ids", []))

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
            *[create_type.si(tid) for tid in sorted(list(missing_type_ids))],
        )

        if dependency_creation_tasks:
            # Use a chord to ensure all dependencies are created before processing history
            callback = dispatch_market_history_tasks.si(processing_info=processing_info)
            workflow = chord(header=dependency_creation_tasks, body=callback)
            workflow.delay()
            logger.info("Dependency creation workflow started with a chord.")
        else:
            # If there are no dependencies to create, just dispatch the history tasks directly
            logger.info(
                "No new dependencies to create. Proceeding directly to market history processing."
            )
            dispatch_market_history_tasks.delay(processing_info=processing_info)

    except Exception as e:
        logger.error(f"An error occurred during dependency aggregation: {e}")
    finally:
        db.close()


@shared_task
def orchestrate_market_data_load(dates: list[str]):
    """
    Orchestrates the data loading process: download, find dependencies,
    create them, then process from local files.
    """
    download_tasks = group(download_and_extract_ids.s(date) for date in dates)

    # After all downloads and ID extractions are done, aggregate the results
    # and create the processing workflow.
    callback = aggregate_and_dispatch_dependencies.s()

    workflow = chord(header=download_tasks, body=callback)
    workflow.delay()
    logger.info("Orchestration workflow started with download and aggregation.")


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