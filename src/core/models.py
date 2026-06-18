# src/core/models.py
"""
SQLAlchemy ORM models for the DC Trade Toolbox.
Used by Alembic for migrations, and can replace raw SQL in database.py.
"""

from sqlalchemy import (
    Column, Integer, Float, Text, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Deal(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Text, nullable=False)
    iron_ingots = Column(Float, default=0)
    gold_ingots = Column(Float, default=0)
    diamond_items = Column(Float, default=0)
    iron_price = Column(Float, default=0)
    gold_price = Column(Float, default=0)
    diamond_price = Column(Float, default=0)
    market_value = Column(Float, default=0)
    offered_price = Column(Float, default=0)
    status = Column(Text, default="")
    profit = Column(Float, default=0)
    iron_amount = Column(Float, default=0)
    iron_unit = Column(Text, default="ingot")
    gold_amount = Column(Float, default=0)
    gold_unit = Column(Text, default="ingot")
    diamond_amount = Column(Float, default=0)
    diamond_unit = Column(Text, default="ingot")


class PriceCache(Base):
    __tablename__ = "price_cache"

    item_name = Column(Text, primary_key=True)
    price = Column(Float, nullable=False)
    timestamp = Column(Float, nullable=False)


class Stash(Base):
    __tablename__ = "stash"

    id = Column(Integer, primary_key=True)
    name = Column(Text, default="Default")
    iron_blocks = Column(Integer, default=0)
    iron_ingots = Column(Integer, default=0)
    gold_blocks = Column(Integer, default=0)
    gold_ingots = Column(Integer, default=0)
    diamond_blocks = Column(Integer, default=0)
    diamond_items = Column(Integer, default=0)
    raw_iron_blocks = Column(Integer, default=0)
    raw_gold_blocks = Column(Integer, default=0)
    auto_subtract = Column(Integer, default=0)
    updated_at = Column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("id = 1", name="stash_single_row"),
    )


class Template(Base):
    __tablename__ = "templates"

    name = Column(Text, primary_key=True)
    iron_ingots = Column(Float, default=0)
    gold_ingots = Column(Float, default=0)
    diamond_items = Column(Float, default=0)
    offered_price = Column(Float, default=0)


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Text, nullable=False)
    iron_price = Column(Float, default=0)
    gold_price = Column(Float, default=0)
    diamond_price = Column(Float, default=0)