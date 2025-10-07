from app.tasks.worker import celery_app
from app.services.esi import esi_service
from app.database import SessionLocal
from app.models import Region, ItemType, MarketHistory
from app.schemas import RegionCreate, ItemTypeCreate, MarketHistoryCreate
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@celery_app.task
def fetch_and_store_regions(previous_result=None):
    logger.info("Fetching and storing regions...")
    loop = asyncio.get_event_loop()
    regions_data = loop.run_until_complete(esi_service.get_regions())

    db = SessionLocal()
    try:
        for region_id in regions_data:
            details = loop.run_until_complete(esi_service.get_region_details(region_id))
            db_region = db.query(Region).filter(Region.id == region_id).first()

            if db_region:
                # Update existing region if name or description has changed
                if db_region.name != details['name'] or db_region.description != details.get('description'):
                    logger.info(f"Updating region {details['name']}.")
                    db_region.name = details['name']
                    db_region.description = details.get('description')
            else:
                # Add new region
                logger.info(f"Adding new region: {details['name']}")
                region = RegionCreate(id=region_id, name=details['name'], description=details.get('description'))
                db.add(Region(**region.dict()))
        db.commit()
        logger.info("Regions fetched and stored successfully.")
    finally:
        db.close()

@celery_app.task
def fetch_and_store_item_types(previous_result=None):
    logger.info("Fetching and storing item types...")
    loop = asyncio.get_event_loop()
    db = SessionLocal()
    try:
        regions = db.query(Region).all()
        logger.info(f"Found {len(regions)} regions to process.")

        # Concurrently fetch all type IDs from all regions.
        region_tasks = [esi_service.get_type_ids_in_region(region.id) for region in regions]
        all_type_ids_results = loop.run_until_complete(asyncio.gather(*region_tasks))

        # Create a single set of unique type IDs.
        unique_type_ids = set()
        for type_id_list in all_type_ids_results:
            unique_type_ids.update(type_id_list)
        logger.info(f"Found {len(unique_type_ids)} unique marketable item types across all regions.")

        # Fetch all existing item type IDs from the DB in one query.
        existing_type_ids = {item[0] for item in db.query(ItemType.id).all()}
        logger.info(f"Found {len(existing_type_ids)} existing item types in the database.")

        # Determine which type IDs are new.
        new_type_ids = list(unique_type_ids - existing_type_ids)
        logger.info(f"Found {len(new_type_ids)} new item types to fetch details for.")

        if new_type_ids:
            batch_size = 500  # Process in batches to be kind to the API
            total_added = 0
            for i in range(0, len(new_type_ids), batch_size):
                batch_ids = new_type_ids[i:i+batch_size]
                logger.info(f"Processing batch {i//batch_size + 1}/{(len(new_type_ids) + batch_size - 1)//batch_size}...")

                detail_tasks = [esi_service.get_type_details(type_id) for type_id in batch_ids]
                details_results = loop.run_until_complete(asyncio.gather(*detail_tasks, return_exceptions=True))

                items_to_add = []
                for type_id, details in zip(batch_ids, details_results):
                    if isinstance(details, Exception):
                        logger.error(f"Failed to fetch details for type_id {type_id}: {details}")
                        continue

                    if details:
                        item_schema = ItemTypeCreate(
                            id=type_id,
                            name=details['name'],
                            description=details.get('description'),
                            icon_url=details['icon_url']
                        )
                        items_to_add.append(ItemType(**item_schema.dict()))

                if items_to_add:
                    db.add_all(items_to_add)
                    db.commit()
                    total_added += len(items_to_add)
                    logger.info(f"Added {len(items_to_add)} new items in this batch.")

            logger.info(f"Successfully stored a total of {total_added} new item types.")
        else:
            logger.info("No new item types to store.")

        logger.info("Item types fetching task completed.")
    finally:
        db.close()

@celery_app.task
def fetch_and_store_market_history(previous_result=None):
    logger.info("Fetching and storing market history...")
    loop = asyncio.get_event_loop()
    db = SessionLocal()
    try:
        item_types = db.query(ItemType).all()
        regions = db.query(Region).all()
        for region in regions:
            for item_type in item_types:
                history_data = loop.run_until_complete(esi_service.get_market_history(item_type.id, region.id))
                for record in history_data:
                    record_date = datetime.strptime(record['date'], '%Y-%m-%d')
                    if not db.query(MarketHistory).filter(
                        MarketHistory.type_id == item_type.id,
                        MarketHistory.region_id == region.id,
                        MarketHistory.date == record_date
                    ).first():
                        history_create = MarketHistoryCreate(
                            type_id=item_type.id,
                            region_id=region.id,
                            date=record_date,
                            average=record['average'],
                            highest=record['highest'],
                            lowest=record['lowest'],
                            order_count=record['order_count'],
                            volume=record['volume']
                        )
                        db.add(MarketHistory(**history_create.dict()))
        db.commit()
        logger.info("Market history fetched and stored successfully.")
    finally:
        db.close()