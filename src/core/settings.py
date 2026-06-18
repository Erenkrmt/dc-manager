# src/core/settings.py
"""
Centralized configuration via Pydantic Settings.
Loads from environment variables and .env files.
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

# Determine the project root (two levels up from this file: src/core/ -> src/ -> /)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings:
    """Application settings. Uses Pydantic-style access but without the dependency."""

    # ── General ──────────────────────────────────────────────────────────
    COMPANY_NAME: str = os.getenv("COMPANY_NAME", "Fishy Business")
    DEBUG: bool = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")

    # ── Database ─────────────────────────────────────────────────────────
    # SQLite by default (data/dc_trade.db) – no setup required.
    # For production, set DATABASE_URL=postgres://user:pass@host/dbname
    # Alembic migrations work with both.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DB_DIR: str = os.getenv("DB_DIR", str(_PROJECT_ROOT / "data"))
    DB_FILE: str = os.path.join(DB_DIR, "dc_trade.db")

    # ── API ──────────────────────────────────────────────────────────────
    DC_API_KEY: str = os.getenv("DC_API_KEY", "")
    API_BASE_URL: str = os.getenv(
        "API_BASE_URL",
        "https://api.democracycraft.net/economy/api/v1/chestshop/items",
    )
    API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", "10"))
    API_RETRIES: int = int(os.getenv("API_RETRIES", "3"))
    API_RETRY_DELAY: int = int(os.getenv("API_RETRY_DELAY", "2"))
    PRICE_DAYS_LOOKBACK: int = int(os.getenv("PRICE_DAYS_LOOKBACK", "30"))

    # ── Trading thresholds ───────────────────────────────────────────────
    MIN_ACCEPTABLE_PERCENT: float = float(os.getenv("MIN_ACCEPTABLE_PERCENT", "0.85"))

    # ── Price cache ──────────────────────────────────────────────────────
    CACHE_DURATION: int = int(os.getenv("CACHE_DURATION", str(6 * 60 * 60)))  # 6h

    # ── Minecraft item units ─────────────────────────────────────────────
    ITEMS_PER_STACK: int = 64
    ITEMS_PER_SHULKER: int = 1728  # 27 * 64
    INGOTS_PER_BLOCK: int = 9
    NUGGETS_PER_INGOT: int = 9

    # ── Server ───────────────────────────────────────────────────────────
    STREAMLIT_PORT: int = int(os.getenv("STREAMLIT_PORT", "8501"))
    API_PORT: int = int(os.getenv("API_PORT", os.getenv("PORT", "8000")))
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")

    # ── Fallback prices ──────────────────────────────────────────────────
    FALLBACK_PRICES: dict[str, float] = {
        "Iron Ingot": 1.20,
        "Gold Ingot": 2.50,
        "Diamond": 15.00,
    }

    # ── Item import mapping ──────────────────────────────────────────────
    IMPORT_ITEM_MAPPING: dict[str, str] = {
        "Block of Raw Iron": "raw_iron_blocks",
        "Block of Iron": "iron_blocks",
        "Iron Ingot": "iron_ingots",
        "Block of Raw Gold": "raw_gold_blocks",
        "Block of Gold": "gold_blocks",
        "Gold Ingot": "gold_ingots",
        "Block of Diamond": "diamond_blocks",
        "Diamond": "diamond_items",
    }
    IMPORT_ITEM_FACTORS: dict[str, float] = {}

    def __init__(self):
        """Ensure data directory exists."""
        os.makedirs(self.DB_DIR, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton pattern)."""
    return Settings()