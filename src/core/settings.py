# src/core/settings.py
"""
Centralized configuration via Pydantic Settings.
Loads from environment variables and .env files.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from functools import lru_cache
from dotenv import load_dotenv

# Determine the project root (two levels up from this file: src/core/ -> src/ -> /)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"
_ENCRYPTED_ENV_FILE = _PROJECT_ROOT / ".env.encrypted"


def _auto_decrypt_env() -> None:
    """
    Auto-decrypt .env.encrypted → .env at startup if .env is missing.
    
    This is a safety net for scenarios where the post-merge hook wasn't
    installed or didn't fire (e.g., first clone, Docker build).
    Requires sops CLI and age key to be available; fails gracefully otherwise.
    """
    if _ENV_FILE.exists():
        return  # Already have a decrypted .env, nothing to do

    if not _ENCRYPTED_ENV_FILE.exists():
        return  # Nothing encrypted to decrypt

    sops_path = shutil.which("sops")
    if not sops_path:
        return  # sops not installed; settings will use defaults

    # Resolve age key file
    key_file_env = os.environ.get("SOPS_AGE_KEY_FILE")
    key_file = Path(key_file_env) if key_file_env else Path.home() / ".config" / "sops" / "age" / "keys.txt"
    if not key_file.exists():
        return  # No age key found; settings will use defaults

    env = os.environ.copy()
    env["SOPS_AGE_KEY_FILE"] = str(key_file)

    result = subprocess.run(
        [sops_path, "--decrypt", "--input-type", "dotenv", "--output-type", "dotenv", str(_ENCRYPTED_ENV_FILE)],
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        return  # Decryption failed; settings will use defaults

    _ENV_FILE.write_text(result.stdout, encoding="utf-8")


# Try to auto-decrypt before loading .env
_auto_decrypt_env()

# Load .env file from the project root (explicit path to avoid CWD issues)
load_dotenv(_ENV_FILE)


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

    # ── Multi-company / Auth ────────────────────────────────────────────
    # Discord OAuth 2.0 — set these in .env for production
    DISCORD_CLIENT_ID: str = os.getenv("DISCORD_CLIENT_ID", "")
    DISCORD_CLIENT_SECRET: str = os.getenv("DISCORD_CLIENT_SECRET", "")
    DISCORD_REDIRECT_URI: str = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8501/")
    # Comma-separated list of Discord user IDs that have admin access
    ADMIN_DISCORD_IDS: list[str] = [
        x.strip() for x in os.getenv("ADMIN_DISCORD_IDS", "").split(",") if x.strip()
    ]
    # Trial duration in days (immediate on first Discord login)
    TRIAL_DAYS: int = int(os.getenv("TRIAL_DAYS", "3"))
    # Session secret for signing cookies (auto-generated if empty)
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
    # API key prefix format
    API_KEY_PREFIX: str = "dc_"

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