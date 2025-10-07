from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Region
from app.schemas import Region as RegionSchema

router = APIRouter()

@router.get("/regions", response_model=List[RegionSchema])
def get_regions_list(db: Session = Depends(get_db)):
    """
    Returns a list of all available regions.
    """
    regions = db.query(Region).all()
    return regions