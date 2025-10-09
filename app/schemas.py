from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import Optional, List

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

    model_config = ConfigDict(from_attributes=True)

# Region Schemas
class RegionBase(BaseModel):
    region_id: int
    name: str
    description: Optional[str] = None

class RegionCreate(RegionBase):
    pass

class Region(RegionBase):
    model_config = ConfigDict(from_attributes=True)

# Dogma Attribute Schemas
class TypeDogmaAttributeBase(BaseModel):
    attribute_id: int
    value: float

class TypeDogmaAttributeCreate(TypeDogmaAttributeBase):
    pass

class TypeDogmaAttribute(TypeDogmaAttributeBase):
    id: int
    type_id: int
    model_config = ConfigDict(from_attributes=True)

# EveType Schemas
class EveTypeBase(BaseModel):
    type_id: int
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None

class EveTypeCreate(EveTypeBase):
    dogma_attributes: List[TypeDogmaAttributeCreate] = []

class EveType(EveTypeBase):
    dogma_attributes: List[TypeDogmaAttribute] = []
    model_config = ConfigDict(from_attributes=True)