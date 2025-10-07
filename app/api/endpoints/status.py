from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AnalyzedItem
from app.schemas import StatusResponse
from datetime import datetime, time, timedelta

router = APIRouter()

@router.get("/status", response_model=StatusResponse)
def get_system_status(db: Session = Depends(get_db)):
    """
    Returns the system health, dataset timestamps, and update status.
    """
    last_update = db.query(AnalyzedItem).order_by(AnalyzedItem.last_updated.desc()).first()

    last_update_timestamp = last_update.last_updated if last_update else None

    now_utc = datetime.utcnow()
    next_update_time = time(11, 10)

    next_update_timestamp = now_utc.replace(hour=next_update_time.hour, minute=next_update_time.minute, second=0, microsecond=0)
    if now_utc.time() > next_update_time:
        next_update_timestamp = next_update_timestamp + timedelta(days=1)

    return {
        "status": "online",
        "last_update_timestamp": last_update_timestamp,
        "next_update_timestamp": next_update_timestamp
    }