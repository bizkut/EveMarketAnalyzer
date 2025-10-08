from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from typing import Optional

# Region Schemas
class RegionBase(BaseModel):
    region_id: int
    name: Optional[str] = None

class RegionCreate(RegionBase):
    pass

class Region(RegionBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ItemType Schemas
class ItemTypeBase(BaseModel):
    type_id: int
    name: Optional[str] = None

class ItemTypeCreate(ItemTypeBase):
    pass

class ItemType(ItemTypeBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# MarketHistory Schemas
class MarketHistoryBase(BaseModel):
    date: date
    average: float
    highest: float
    lowest: float
    order_count: int
    volume: int
    region_id: int
    type_id: int

class MarketHistoryCreate(MarketHistoryBase):
    pass

class MarketHistory(MarketHistoryBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# AnalyzedItem Schemas
class AnalyzedItemBase(BaseModel):
    type_id: int
    region_id: int
    item_name: Optional[str] = None
    avg_buy_price: Optional[float] = None
    avg_sell_price: Optional[float] = None
    predicted_buy_price: Optional[float] = None
    predicted_sell_price: Optional[float] = None
    profit_per_unit: Optional[float] = None
    roi_percent: Optional[float] = None
    avg_daily_volume: Optional[float] = None
    volatility_30d: Optional[float] = None
    trend_direction: Optional[int] = None
    last_updated: datetime

class AnalyzedItem(AnalyzedItemBase):
    id: int
    model_config = ConfigDict(from_attributes=True)