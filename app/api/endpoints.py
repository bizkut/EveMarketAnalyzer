from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..config import settings
from ..database import get_db
from ..tasks.data_fetching import initial_data_load, daily_update_task

router = APIRouter()

API_KEY_HEADER = APIKeyHeader(name="X-API-KEY", auto_error=False)


async def get_api_key(api_key_header: str = Security(API_KEY_HEADER)):
    if api_key_header == settings.API_KEY:
        return api_key_header
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )


@router.get(
    "/markets/{region_id}/history",
    response_model=List[schemas.MarketHistory],
    summary="Get Market History for a Region and Type",
)
def get_market_history(region_id: int, type_id: int, db: Session = Depends(get_db)):
    """
    Retrieves the market history for a specific region and item type.
    """
    history = crud.get_market_history_by_region_and_type(
        db, region_id=region_id, type_id=type_id
    )
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No market history found for the specified region and type.",
        )
    return history


@router.post(
    "/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a full refresh of market data",
    dependencies=[Depends(get_api_key)],
)
async def refresh_market_data():
    """
    Triggers a background task to perform a full refresh of the market data,
    fetching the last year of history. This is a long-running process.
    Requires a valid API key.
    """
    initial_data_load.delay()
    return {"message": "Market data refresh initiated."}


@router.post(
    "/refresh/daily",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a daily refresh of market data",
    dependencies=[Depends(get_api_key)],
)
async def refresh_daily_market_data():
    """
    Triggers a background task to perform a daily refresh of the market data.
    Requires a valid API key.
    """
    daily_update_task.delay()
    return {"message": "Daily market data refresh initiated."}


@router.get(
    "/analysis",
    response_model=schemas.MarketAnalysisResult,
    summary="Get pre-calculated market analysis",
)
def get_market_analysis(
    sort: str = Query(
        "profit_margin",
        description="Sort by 'profit_margin' or 'demand'",
        pattern="^(profit_margin|demand)$",
    ),
    type_id: Optional[int] = Query(None, description="Filter by type ID"),
    type_name: Optional[str] = Query(
        None, description="Filter by type name (case-insensitive, partial match)"
    ),
    region_id: Optional[int] = Query(None, description="Filter by region ID"),
    region_name: Optional[str] = Query(
        None, description="Filter by region name (case-insensitive, partial match)"
    ),
    db: Session = Depends(get_db),
):
    """
    Retrieves the pre-calculated market analysis, which is updated daily.
    The results can be sorted by either profit margin or demand in descending order,
    and can be filtered by type and region attributes.
    """
    analysis_results = crud.get_market_analysis(
        db,
        sort=sort,
        limit=100,
        type_id=type_id,
        type_name=type_name,
        region_id=region_id,
        region_name=region_name,
    )
    return schemas.MarketAnalysisResult(results=analysis_results)