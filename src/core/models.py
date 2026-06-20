# src/core/models.py
"""
SQLAlchemy ORM models for the DC Trade Toolbox.
Used by Alembic for migrations, and can replace raw SQL in database.py.
"""

from sqlalchemy import (
    Column, Integer, Float, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Company(Base):
    """Multi-company registration via Discord OAuth."""
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    discord_id = Column(Text, unique=True, nullable=False)
    discord_username = Column(Text, nullable=False)
    discord_avatar = Column(Text, default="")
    api_key = Column(Text, unique=True, nullable=False)
    company_name = Column(Text, default="")
    access_expires_at = Column(Text, nullable=True)  # NULL = never expires
    is_active = Column(Integer, default=1)
    trial_used = Column(Integer, default=0)
    session_token = Column(Text, default="")
    public_stash_token = Column(Text, default="")
    tier = Column(Text, default="free")  # "free" or "premium"
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=False)


class Deal(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, default=1)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, default=1)
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
        UniqueConstraint("company_id", name="uq_stash_company"),
    )


class Template(Base):
    __tablename__ = "templates"

    name = Column(Text, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, default=1)
    iron_ingots = Column(Float, default=0)
    gold_ingots = Column(Float, default=0)
    diamond_items = Column(Float, default=0)
    offered_price = Column(Float, default=0)


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, default=1)
    timestamp = Column(Text, nullable=False)
    iron_price = Column(Float, default=0)
    gold_price = Column(Float, default=0)
    diamond_price = Column(Float, default=0)


class ItemLookupDeal(Base):
    __tablename__ = "item_lookup_deals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, default=1)
    timestamp = Column(Text, nullable=False)
    item_name = Column(Text, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_value = Column(Float, nullable=False)
    offered_price = Column(Float, nullable=False)
    status = Column(Text, default="")
    profit = Column(Float, default=0)
