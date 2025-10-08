from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Date,
    BigInteger,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Region(Base):
    __tablename__ = "regions"
    id = Column(Integer, primary_key=True, index=True)
    region_id = Column(BigInteger, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)

class ItemType(Base):
    __tablename__ = "item_types"
    id = Column(Integer, primary_key=True, index=True)
    type_id = Column(BigInteger, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)

class MarketHistory(Base):
    __tablename__ = "market_history"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    average = Column(Float, nullable=False)
    highest = Column(Float, nullable=False)
    lowest = Column(Float, nullable=False)
    order_count = Column(BigInteger, nullable=False)
    volume = Column(BigInteger, nullable=False)
    region_id = Column(BigInteger, nullable=False, index=True)
    type_id = Column(BigInteger, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("date", "region_id", "type_id", name="_date_region_type_uc"),
    )

class AnalyzedItem(Base):
    __tablename__ = "analyzed_items"
    id = Column(Integer, primary_key=True, index=True)
    type_id = Column(BigInteger, nullable=False, index=True)
    region_id = Column(BigInteger, nullable=False, index=True)
    item_name = Column(String)
    avg_buy_price = Column(Float)
    avg_sell_price = Column(Float)
    predicted_buy_price = Column(Float)
    predicted_sell_price = Column(Float)
    profit_per_unit = Column(Float)
    roi_percent = Column(Float)
    avg_daily_volume = Column(Float)
    volatility_30d = Column(Float)
    trend_direction = Column(Integer)
    last_updated = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("type_id", "region_id", name="_type_region_uc"),
    )