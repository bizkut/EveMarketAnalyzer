from pydantic import BaseModel
from datetime import date
from typing import Optional

# Market History Schemas
class MarketHistoryBase(BaseModel):
    average: float
    date: date
    highest: float
    lowest: float
    order_count: int
    volume: int
    region_id: int
    type_id: int

class MarketHistoryCreate(MarketHistoryBase):
    pass

class MarketHistory(BaseModel):
    average: float
    date: date
    highest: float
    lowest: float
    order_count: int
    volume: int

    class Config:
        orm_mode = True

# Region Schemas
class RegionBase(BaseModel):
    region_id: int
    name: str
    description: Optional[str] = None

class RegionCreate(RegionBase):
    pass

class Region(RegionBase):
    class Config:
        orm_mode = True

# EveType Schemas
class EveTypeBase(BaseModel):
    type_id: int
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None

class EveTypeCreate(EveTypeBase):
    pass

class EveType(EveTypeBase):
    class Config:
        orm_mode = True