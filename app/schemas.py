from pydantic import BaseModel
from typing import List, Optional
import datetime

# Region Schemas
class RegionBase(BaseModel):
    id: int
    name: str

class RegionCreate(RegionBase):
    pass

class Region(RegionBase):
    description: Optional[str] = None

    class Config:
        orm_mode = True

# ItemType Schemas
class ItemTypeBase(BaseModel):
    id: int
    name: str

class ItemTypeCreate(ItemTypeBase):
    description: Optional[str] = None
    icon_url: Optional[str] = None

class ItemType(ItemTypeBase):
    description: Optional[str] = None
    icon_url: Optional[str] = None

    class Config:
        orm_mode = True

# MarketHistory Schemas
class MarketHistoryBase(BaseModel):
    date: datetime.datetime
    average: float
    highest: float
    lowest: float
    order_count: int
    volume: int

class MarketHistoryCreate(MarketHistoryBase):
    type_id: int
    region_id: int

class MarketHistory(MarketHistoryBase):
    id: int
    type_id: int
    region_id: int

    class Config:
        orm_mode = True

# AnalyzedItem Schemas
class AnalyzedItemBase(BaseModel):
    type_id: int
    region_id: int
    item_name: str
    avg_buy_price: float
    avg_sell_price: float
    predicted_buy_price: float
    predicted_sell_price: float
    profit_per_unit: float
    roi_percent: float
    avg_daily_volume: float
    volatility_30d: float
    trend_direction: int
    last_updated: datetime.datetime

class AnalyzedItemCreate(AnalyzedItemBase):
    pass

class AnalyzedItem(AnalyzedItemBase):
    id: int

    class Config:
        orm_mode = True

# API Response Schemas
class TopItemResponse(BaseModel):
    type_id: int
    region_id: int
    item_name: str
    avg_buy_price: float
    avg_sell_price: float
    predicted_buy_price: float
    predicted_sell_price: float
    profit_per_unit: float
    roi_percent: float
    avg_daily_volume: float
    volatility_30d: float
    trend_direction: int
    last_updated: datetime.datetime

class ItemDetailResponse(AnalyzedItem):
    history: List[MarketHistory] = []

class StatusResponse(BaseModel):
    status: str
    last_update_timestamp: Optional[datetime.datetime] = None
    next_update_timestamp: Optional[datetime.datetime] = None

class RefreshResponse(BaseModel):
    message: str