from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class Region(Base):
    __tablename__ = "regions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text, nullable=True)

class ItemType(Base):
    __tablename__ = "item_types"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text, nullable=True)
    icon_url = Column(String, nullable=True)
    market_history = relationship("MarketHistory", back_populates="item_type")

class MarketHistory(Base):
    __tablename__ = "market_history"
    id = Column(Integer, primary_key=True, index=True)
    type_id = Column(Integer, ForeignKey("item_types.id"))
    region_id = Column(Integer, ForeignKey("regions.id"))
    date = Column(DateTime, default=datetime.datetime.utcnow)
    average = Column(Float)
    highest = Column(Float)
    lowest = Column(Float)
    order_count = Column(Integer)
    volume = Column(Integer)
    item_type = relationship("ItemType", back_populates="market_history")

class AnalyzedItem(Base):
    __tablename__ = "analyzed_items"
    id = Column(Integer, primary_key=True, index=True)
    type_id = Column(Integer, ForeignKey("item_types.id"))
    region_id = Column(Integer, ForeignKey("regions.id"))
    item_name = Column(String)
    avg_buy_price = Column(Float)
    avg_sell_price = Column(Float)
    predicted_buy_price = Column(Float)
    predicted_sell_price = Column(Float)
    profit_per_unit = Column(Float)
    roi_percent = Column(Float)
    avg_daily_volume = Column(Float)
    volatility_30d = Column(Float)
    trend_direction = Column(Integer) # 1 for up, -1 for down, 0 for stable
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)