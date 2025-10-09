import logging
from typing import List, Set, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from . import models, schemas

logger = logging.getLogger(__name__)

def get_market_history_by_region_and_type(
    db: Session, region_id: int, type_id: int
) -> List[models.MarketHistory]:
    """
    Fetches market history records, ordered by date.
    """
    return (
        db.query(models.MarketHistory)
        .filter(
            models.MarketHistory.region_id == region_id,
            models.MarketHistory.type_id == type_id,
        )
        .order_by(models.MarketHistory.date)
        .all()
    )

def create_bulk_market_history(
    db: Session, history_records: List[schemas.MarketHistoryCreate]
):
    """
    Bulk inserts market history records. This is much more efficient than
    inserting one by one.
    """
    if not history_records:
        return

    record_dicts = [record.model_dump() for record in history_records]

    try:
        db.bulk_insert_mappings(models.MarketHistory, record_dicts)
        db.commit()
    except IntegrityError as e:
        logger.error(f"Integrity error during bulk insert: {e}")
        db.rollback()
        logger.info("Attempting to insert records individually to bypass duplicates.")
        for record in record_dicts:
            db.query(models.MarketHistory).filter_by(**record).one_or_none() or db.add(models.MarketHistory(**record))
        db.commit()

    except Exception as e:
        logger.error(f"Error during bulk insert of market history: {e}")
        db.rollback()
        raise

def get_or_create_region(db: Session, region: schemas.RegionCreate) -> models.Region:
    """
    Retrieves a region from the database or creates it if it does not exist.
    Handles race conditions where another process might create the same region
    concurrently.
    """
    # First, try to fetch the region
    db_region = db.query(models.Region).filter(models.Region.region_id == region.region_id).first()
    if db_region:
        return db_region

    # If it doesn't exist, create it
    db_region = models.Region(**region.model_dump())
    db.add(db_region)
    try:
        db.commit()
        db.refresh(db_region)
        return db_region
    except IntegrityError:
        # The region was created by another worker in the meantime.
        db.rollback()
        # The region must exist now, so we can query for it.
        return db.query(models.Region).filter(models.Region.region_id == region.region_id).one()

def get_or_create_type(db: Session, eve_type: schemas.EveTypeCreate) -> models.EveType:
    """
    Retrieves an EVE type from the database or creates it if it does not exist.
    Handles race conditions where another process might create the same type
    concurrently.
    """
    # First, try to fetch the type
    db_type = db.query(models.EveType).filter(models.EveType.type_id == eve_type.type_id).first()
    if db_type:
        return db_type

    # If it doesn't exist, create it
    db_type = models.EveType(**eve_type.model_dump())
    db.add(db_type)
    try:
        db.commit()
        db.refresh(db_type)
        return db_type
    except IntegrityError:
        # The type was created by another worker in the meantime.
        db.rollback()
        # The type must exist now, so we can query for it.
        return db.query(models.EveType).filter(models.EveType.type_id == eve_type.type_id).one()

def is_database_empty(db: Session) -> bool:
    """
    Checks if the market_history table has any records.
    """
    return db.query(models.MarketHistory).first() is None

def get_existing_region_ids(db: Session, region_ids: List[int]) -> Set[int]:
    """
    Given a list of region IDs, returns the set of IDs that already exist in the database.
    """
    if not region_ids:
        return set()
    existing = db.query(models.Region.region_id).filter(models.Region.region_id.in_(region_ids)).all()
    return {r[0] for r in existing}

def get_existing_type_ids(db: Session, type_ids: List[int]) -> Set[int]:
    """
    Given a list of type IDs, returns the set of IDs that already exist in the database.
    """
    if not type_ids:
        return set()
    existing = db.query(models.EveType.type_id).filter(models.EveType.type_id.in_(type_ids)).all()
    return {t[0] for t in existing}