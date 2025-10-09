from sqlalchemy import Column, Integer, String, Float, Date, Text, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class MarketHistory(Base):
    __tablename__ = "market_history"

    id = Column(Integer, primary_key=True, index=True)
    average = Column(Float)
    date = Column(Date)
    highest = Column(Float)
    lowest = Column(Float)
    order_count = Column(Integer)
    volume = Column(Integer)
    region_id = Column(Integer, ForeignKey("regions.region_id"))
    type_id = Column(Integer, ForeignKey("eve_types.type_id"))

    region = relationship("Region", back_populates="history")
    eve_type = relationship("EveType", back_populates="history")

class Region(Base):
    __tablename__ = "regions"

    region_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)

    history = relationship("MarketHistory", back_populates="region")

class EveType(Base):
    __tablename__ = "eve_types"

    type_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    icon_url = Column(String)

    history = relationship("MarketHistory", back_populates="eve_type")
    dogma_attributes = relationship(
        "TypeDogmaAttribute", back_populates="eve_type", cascade="all, delete-orphan"
    )


class TypeDogmaAttribute(Base):
    __tablename__ = "type_dogma_attributes"

    id = Column(Integer, primary_key=True, index=True)
    type_id = Column(Integer, ForeignKey("eve_types.type_id"))
    attribute_id = Column(Integer)
    value = Column(Float)

    eve_type = relationship("EveType", back_populates="dogma_attributes")