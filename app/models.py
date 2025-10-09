from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Date,
    Text,
    ForeignKey,
    Boolean,
    BigInteger,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .database import Base


class MarketHistory(Base):
    __tablename__ = "market_history"

    id = Column(Integer, primary_key=True, index=True)
    average = Column(Float)
    date = Column(Date)
    highest = Column(Float)
    lowest = Column(Float)
    order_count = Column(BigInteger)
    volume = Column(BigInteger)
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
    analysis = relationship("MarketAnalysis", back_populates="region")


class EveType(Base):
    __tablename__ = "eve_types"

    type_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    icon_url = Column(String)
    capacity = Column(Float, nullable=True)
    group_id = Column(Integer, nullable=True)
    market_group_id = Column(Integer, nullable=True)
    mass = Column(Float, nullable=True)
    packaged_volume = Column(Float, nullable=True)
    portion_size = Column(Integer, nullable=True)
    published = Column(Boolean)
    radius = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)

    history = relationship("MarketHistory", back_populates="eve_type")
    dogma_attributes = relationship(
        "TypeDogmaAttribute", back_populates="eve_type", cascade="all, delete-orphan"
    )
    analysis = relationship("MarketAnalysis", back_populates="eve_type")


class TypeDogmaAttribute(Base):
    __tablename__ = "type_dogma_attributes"

    id = Column(Integer, primary_key=True, index=True)
    type_id = Column(Integer, ForeignKey("eve_types.type_id"))
    attribute_id = Column(Integer)
    value = Column(Float)

    eve_type = relationship("EveType", back_populates="dogma_attributes")


class MarketAnalysis(Base):
    __tablename__ = "market_analysis"
    __table_args__ = (
        UniqueConstraint("type_id", "region_id", name="uq_type_region_analysis"),
    )

    id = Column(Integer, primary_key=True, index=True)
    type_id = Column(Integer, ForeignKey("eve_types.type_id"), index=True)
    region_id = Column(Integer, ForeignKey("regions.region_id"), index=True)
    demand = Column(Float)
    profit_margin = Column(Float)

    eve_type = relationship("EveType", back_populates="analysis")
    region = relationship("Region", back_populates="analysis")

    @property
    def type_name(self):
        return self.eve_type.name

    @property
    def region_name(self):
        return self.region.name