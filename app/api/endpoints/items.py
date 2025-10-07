from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models import AnalyzedItem, MarketHistory
from app.schemas import TopItemResponse, ItemDetailResponse

router = APIRouter()

@router.get("/top-items", response_model=List[TopItemResponse])
def get_top_items(
    limit: int = Query(100, ge=1, le=1000),
    region_id: Optional[int] = Query(None, description="Filter by region ID"),
    db: Session = Depends(get_db)
):
    """
    Returns a list of top profitable items based on ROI, with filtering options.
    """
    query = db.query(AnalyzedItem)

    if region_id:
        query = query.filter(AnalyzedItem.region_id == region_id)

    top_items = query.order_by(AnalyzedItem.roi_percent.desc()).limit(limit).all()

    if not top_items:
        raise HTTPException(status_code=404, detail="No analyzed items found for the given criteria.")

    return top_items

@router.get("/item/{type_id}", response_model=ItemDetailResponse)
def get_item_details(
    type_id: int,
    region_id: Optional[int] = Query(None, description="Specify region ID for more accurate history"),
    db: Session = Depends(get_db)
):
    """
    Returns detailed stats and trend data for a specific item.
    """
    query = db.query(AnalyzedItem).filter(AnalyzedItem.type_id == type_id)
    if region_id:
        query = query.filter(AnalyzedItem.region_id == region_id)

    item_analysis = query.first()

    if not item_analysis:
        raise HTTPException(status_code=404, detail=f"No analysis found for item type ID {type_id}")

    history_query = db.query(MarketHistory).filter(MarketHistory.type_id == type_id)
    if region_id:
        history_query = history_query.filter(MarketHistory.region_id == region_id)

    item_history = history_query.order_by(MarketHistory.date.desc()).limit(90).all() # Last 90 days

    response = ItemDetailResponse(
        **item_analysis.__dict__,
        history=item_history
    )

    return response