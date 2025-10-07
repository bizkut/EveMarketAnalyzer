from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_api_key
from app.tasks.scheduler import run_daily_tasks
from app.schemas import RefreshResponse
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/refresh", response_model=RefreshResponse)
def force_refresh_and_analysis(api_key: str = Depends(get_api_key)):
    """
    Forces an immediate refresh of the dataset and re-analysis.
    This is a secured endpoint.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        logger.info("Manual refresh triggered via API.")
        run_daily_tasks.delay()
        return {"message": "Data refresh and analysis has been initiated."}
    except Exception as e:
        logger.error(f"Failed to trigger refresh task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initiate the refresh task.")