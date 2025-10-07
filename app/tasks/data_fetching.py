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
def fetch_and_store_regions():
    logger.info("Fetching and storing regions...")
    loop = asyncio.get_event_loop()
    regions_data = loop.run_until_complete(esi_service.get_regions())

    db = SessionLocal()
    try:
        for region_id in regions_data:
            if not db.query(Region).filter(Region.id == region_id).first():
                details = loop.run_until_complete(esi_service.get_region_details(region_id))
                region = RegionCreate(id=region_id, name=details['name'], description=details.get('description'))
                db.add(Region(**region.dict()))
        db.commit()
        logger.info("Regions fetched and stored successfully.")
    finally:
        db.close()

@celery_app.task
def fetch_and_store_item_types():
    logger.info("Fetching and storing item types...")
    loop = asyncio.get_event_loop()
    db = SessionLocal()
    try:
        regions = db.query(Region).all()
        for region in regions:
            type_ids = loop.run_until_complete(esi_service.get_type_ids_in_region(region.id))
            for type_id in type_ids:
                if not db.query(ItemType).filter(ItemType.id == type_id).first():
                    details = loop.run_until_complete(esi_service.get_type_details(type_id))
                    item_type = ItemTypeCreate(
                        id=type_id,
                        name=details['name'],
                        description=details.get('description'),
                        icon_url=details['icon_url']
                    )
                    db.add(ItemType(**item_type.dict()))
        db.commit()
        logger.info("Item types fetched and stored successfully.")
    finally:
        db.close()

@celery_app.task
def fetch_and_store_market_history():
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