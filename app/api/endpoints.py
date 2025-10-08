from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.database import get_db
from app.models.market_data import Region, AnalyzedItem, MarketHistory
from app.schemas.market_data import Region as RegionSchema, AnalyzedItem as AnalyzedItemSchema
from app.tasks.worker import update_all_data_task
from app.core.config import settings

router = APIRouter()

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == settings.API_KEY:
        return api_key_header
    else:
        raise HTTPException(
            status_code=403,
            detail="Could not validate credentials",
        )

@router.get("/regions", response_model=List[RegionSchema])
def get_regions(db: Session = Depends(get_db)):
    """
    Get a list of all available regions.
    """
    regions = db.query(Region).all()
    return regions

@router.get("/top-items", response_model=List[AnalyzedItemSchema])
def get_top_items(region_id: int, limit: int = 100, db: Session = Depends(get_db)):
    """
    Get the top profitable items for a given region, ranked by a profit score.
    """
    # Simple profit score for now: roi_percent * log(1 + avg_daily_volume)
    # A more complex score can be developed later.
    items = db.query(AnalyzedItem).filter(
        AnalyzedItem.region_id == region_id,
        AnalyzedItem.roi_percent.isnot(None),
        AnalyzedItem.avg_daily_volume.isnot(None)
    ).order_by(
        (AnalyzedItem.roi_percent * func.log(1 + AnalyzedItem.avg_daily_volume)).desc()
    ).limit(limit).all()
    return items

@router.get("/item/{type_id}", response_model=AnalyzedItemSchema)
def get_item_details(type_id: int, region_id: int, db: Session = Depends(get_db)):
    """
    Get detailed analysis and statistics for a specific item in a region.
    """
    item = db.query(AnalyzedItem).filter(
        AnalyzedItem.type_id == type_id,
        AnalyzedItem.region_id == region_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in the specified region")
    return item

@router.post("/refresh")
def force_refresh(api_key: str = Depends(get_api_key)):
    """
    Secured endpoint to manually trigger a full data refresh and analysis.
    """
    update_all_data_task.delay()
    return {"message": "Data refresh task initiated."}