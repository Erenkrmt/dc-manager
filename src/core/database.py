# src/core/database.py
"""
Database module for the DemocracyCraft Trading Toolbox.
Supports SQLite (default, local dev) and PostgreSQL (production via Cloud SQL).
"""

import os
import logging
from datetime import datetime
from typing import Optional, Union, Any

from src.core.settings import get_settings

_settings = get_settings()

logger = logging.getLogger(__name__)

# ── Detect backend ──────────────────────────────────────────────────────────
_USE_POSTGRES = bool(_settings.DATABASE_URL)

if _USE_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        logger.error(
            "DATABASE_URL is set but psycopg2 is not installed. "
            "Install it with: pip install psycopg2-binary"
        )
        raise
else:
    import sqlite3
    os.makedirs(os.path.dirname(_settings.DB_FILE) or ".", exist_ok=True)


def get_connection():
    """Create and return a database connection (SQLite or PostgreSQL)."""
    if _USE_POSTGRES:
        conn = psycopg2.connect(
            _settings.DATABASE_URL,
            sslmode="require",
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect(_settings.DB_FILE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def _fetchone_as_dict(cursor) -> Optional[dict]:
    """Fetch one row and return as a dict (works with both backends)."""
    if _USE_POSTGRES:
        row = cursor.fetchone()
        return dict(row) if row else None
    else:
        row = cursor.fetchone()
        return dict(row) if row else None


def _fetchall_as_dicts(cursor) -> list[dict]:
    """Fetch all rows and return as a list of dicts."""
    if _USE_POSTGRES:
        return [dict(row) for row in cursor.fetchall()]
    else:
        return [dict(row) for row in cursor.fetchall()]


# ═══════════════════════════════════════════════════════════════════════════
# Schema DDL (SQLite vs PostgreSQL)
# ═══════════════════════════════════════════════════════════════════════════

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    iron_ingots REAL DEFAULT 0,
    gold_ingots REAL DEFAULT 0,
    diamond_items REAL DEFAULT 0,
    iron_price REAL DEFAULT 0,
    gold_price REAL DEFAULT 0,
    diamond_price REAL DEFAULT 0,
    market_value REAL DEFAULT 0,
    offered_price REAL DEFAULT 0,
    status TEXT DEFAULT '',
    profit REAL DEFAULT 0,
    iron_amount REAL DEFAULT 0,
    iron_unit TEXT DEFAULT 'ingot',
    gold_amount REAL DEFAULT 0,
    gold_unit TEXT DEFAULT 'ingot',
    diamond_amount REAL DEFAULT 0,
    diamond_unit TEXT DEFAULT 'ingot'
);

CREATE TABLE IF NOT EXISTS price_cache (
    item_name TEXT PRIMARY KEY,
    price REAL NOT NULL,
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    name TEXT PRIMARY KEY,
    iron_ingots REAL DEFAULT 0,
    gold_ingots REAL DEFAULT 0,
    diamond_items REAL DEFAULT 0,
    offered_price REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    iron_price REAL DEFAULT 0,
    gold_price REAL DEFAULT 0,
    diamond_price REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS item_lookup_deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    total_value REAL NOT NULL,
    offered_price REAL NOT NULL,
    status TEXT DEFAULT '',
    profit REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stash (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT DEFAULT 'Default',
    iron_blocks INTEGER DEFAULT 0,
    iron_ingots INTEGER DEFAULT 0,
    gold_blocks INTEGER DEFAULT 0,
    gold_ingots INTEGER DEFAULT 0,
    diamond_blocks INTEGER DEFAULT 0,
    diamond_items INTEGER DEFAULT 0,
    raw_iron_blocks INTEGER DEFAULT 0,
    raw_gold_blocks INTEGER DEFAULT 0,
    auto_subtract INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    id SERIAL PRIMARY KEY,
    timestamp TEXT NOT NULL,
    iron_ingots REAL DEFAULT 0,
    gold_ingots REAL DEFAULT 0,
    diamond_items REAL DEFAULT 0,
    iron_price REAL DEFAULT 0,
    gold_price REAL DEFAULT 0,
    diamond_price REAL DEFAULT 0,
    market_value REAL DEFAULT 0,
    offered_price REAL DEFAULT 0,
    status TEXT DEFAULT '',
    profit REAL DEFAULT 0,
    iron_amount REAL DEFAULT 0,
    iron_unit TEXT DEFAULT 'ingot',
    gold_amount REAL DEFAULT 0,
    gold_unit TEXT DEFAULT 'ingot',
    diamond_amount REAL DEFAULT 0,
    diamond_unit TEXT DEFAULT 'ingot'
);

CREATE TABLE IF NOT EXISTS price_cache (
    item_name TEXT PRIMARY KEY,
    price REAL NOT NULL,
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    name TEXT PRIMARY KEY,
    iron_ingots REAL DEFAULT 0,
    gold_ingots REAL DEFAULT 0,
    diamond_items REAL DEFAULT 0,
    offered_price REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS price_history (
    id SERIAL PRIMARY KEY,
    timestamp TEXT NOT NULL,
    iron_price REAL DEFAULT 0,
    gold_price REAL DEFAULT 0,
    diamond_price REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS item_lookup_deals (
    id SERIAL PRIMARY KEY,
    timestamp TEXT NOT NULL,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    total_value REAL NOT NULL,
    offered_price REAL NOT NULL,
    status TEXT DEFAULT '',
    profit REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stash (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT DEFAULT 'Default',
    iron_blocks INTEGER DEFAULT 0,
    iron_ingots INTEGER DEFAULT 0,
    gold_blocks INTEGER DEFAULT 0,
    gold_ingots INTEGER DEFAULT 0,
    diamond_blocks INTEGER DEFAULT 0,
    diamond_items INTEGER DEFAULT 0,
    raw_iron_blocks INTEGER DEFAULT 0,
    raw_gold_blocks INTEGER DEFAULT 0,
    auto_subtract INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""


def init_db() -> None:
    """Initialize the database schema if it doesn't exist."""
    conn = get_connection()
    try:
        if _USE_POSTGRES:
            cursor = conn.cursor()
            cursor.execute(_PG_SCHEMA)
            conn.commit()
            # Check and add missing columns in stash table for PostgreSQL
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'stash' AND column_name = 'auto_subtract'
            """)
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE stash ADD COLUMN auto_subtract INTEGER DEFAULT 0")
                logger.debug("Migration: added auto_subtract column.")
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'stash' AND column_name = 'raw_iron_blocks'
            """)
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE stash ADD COLUMN raw_iron_blocks INTEGER DEFAULT 0")
                logger.debug("Migration: added raw_iron_blocks column.")
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'stash' AND column_name = 'raw_gold_blocks'
            """)
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE stash ADD COLUMN raw_gold_blocks INTEGER DEFAULT 0")
                logger.debug("Migration: added raw_gold_blocks column.")
            conn.commit()
        else:
            # SQLite: executescript() handles multiple statements
            conn.executescript(_SQLITE_SCHEMA)
            conn.commit()
            # SQLite migration (ALTER TABLE IF NOT EXISTS via try/except)
            for col in ["auto_subtract", "raw_iron_blocks", "raw_gold_blocks"]:
                try:
                    conn.execute(f"ALTER TABLE stash ADD COLUMN {col} INTEGER DEFAULT 0")
                    conn.commit()
                    logger.debug("Migration: added %s column.", col)
                except sqlite3.OperationalError:
                    pass

        logger.info("Database initialized (%s).", "PostgreSQL" if _USE_POSTGRES else "SQLite")
    except Exception as exc:
        logger.error("Failed to initialize database: %s", exc)
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Price cache operations
# ---------------------------------------------------------------------------
def load_cache() -> dict:
    """Load cached prices from database, returning an empty dict on failure."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT item_name, price, timestamp FROM price_cache")
        rows = cursor.fetchall()
        conn.close()
        return {
            row["item_name"] if hasattr(row, "keys") else row[0]: {
                "price": row["price"] if hasattr(row, "keys") else row[1],
                "timestamp": row["timestamp"] if hasattr(row, "keys") else row[2],
            }
            for row in rows
        }
    except Exception as exc:
        logger.warning("Failed to load cache from DB: %s", exc)
        return {}


def save_cache(cache_data: dict) -> None:
    """Persist cached prices to database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        for item_name, entry in cache_data.items():
            if _USE_POSTGRES:
                cursor.execute(
                    """INSERT INTO price_cache (item_name, price, timestamp)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (item_name) DO UPDATE SET
                         price = EXCLUDED.price,
                         timestamp = EXCLUDED.timestamp""",
                    (item_name, entry["price"], entry["timestamp"]),
                )
            else:
                cursor.execute(
                    """INSERT OR REPLACE INTO price_cache (item_name, price, timestamp)
                       VALUES (?, ?, ?)""",
                    (item_name, entry["price"], entry["timestamp"]),
                )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("Failed to save cache to DB: %s", exc)


# ---------------------------------------------------------------------------
# Deal logging
# ---------------------------------------------------------------------------
def log_deal(
    iron_ingots: float,
    gold_ingots: float,
    diamonds: float,
    market_value: float,
    offered_val: float,
    status: str,
    iron_price: float = 0.0,
    gold_price: float = 0.0,
    diamond_price: float = 0.0,
) -> None:
    """Insert a deal record into the database."""
    profit = offered_val - market_value
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ph = "%s" if _USE_POSTGRES else "?"
    sql = f"""INSERT INTO deals
           (timestamp, iron_ingots, gold_ingots, diamond_items,
            iron_price, gold_price, diamond_price,
            market_value, offered_price, status, profit)
           VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            sql,
            (date_str, iron_ingots, gold_ingots, diamonds,
             iron_price, gold_price, diamond_price,
             market_value, offered_val, status, profit),
        )
        conn.commit()
        conn.close()
        logger.info("Deal logged to database: %s | %s", status, date_str)
    except Exception as exc:
        logger.error("Failed to log deal to database: %s", exc)


def update_deal(deal_id: int, status: str, offered_price: float) -> bool:
    """Update a deal's status and/or offered price. Returns True on success."""
    ph = "%s" if _USE_POSTGRES else "?"
    sql = f"""UPDATE deals SET status = {ph}, offered_price = {ph},
               profit = {ph} - market_value WHERE id = {ph}"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (status, offered_price, offered_price, deal_id))
        conn.commit()
        conn.close()
        logger.info("Deal %d updated: %s | $%.2f", deal_id, status, offered_price)
        return True
    except Exception as exc:
        logger.error("Failed to update deal %d: %s", deal_id, exc)
        return False


def delete_deal(deal_id: int) -> bool:
    """Delete a deal by ID. Returns True on success."""
    ph = "%s" if _USE_POSTGRES else "?"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM deals WHERE id = {ph}", (deal_id,))
        conn.commit()
        conn.close()
        logger.info("Deal %d deleted.", deal_id)
        return True
    except Exception as exc:
        logger.error("Failed to delete deal %d: %s", deal_id, exc)
        return False


# ---------------------------------------------------------------------------
# Deal Templates
# ---------------------------------------------------------------------------
def save_template(name: str, iron_ingots: float, gold_ingots: float,
                  diamond_items: float, offered_price: float) -> bool:
    """Save a deal template. Returns True on success."""
    if _USE_POSTGRES:
        sql = """INSERT INTO templates (name, iron_ingots, gold_ingots, diamond_items, offered_price)
                 VALUES (%s, %s, %s, %s, %s)
                 ON CONFLICT (name) DO UPDATE SET
                   iron_ingots = EXCLUDED.iron_ingots,
                   gold_ingots = EXCLUDED.gold_ingots,
                   diamond_items = EXCLUDED.diamond_items,
                   offered_price = EXCLUDED.offered_price"""
    else:
        sql = """INSERT OR REPLACE INTO templates
                 (name, iron_ingots, gold_ingots, diamond_items, offered_price)
                 VALUES (?, ?, ?, ?, ?)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (name, iron_ingots, gold_ingots, diamond_items, offered_price))
        conn.commit()
        conn.close()
        logger.info("Template '%s' saved.", name)
        return True
    except Exception as exc:
        logger.error("Failed to save template: %s", exc)
        return False


def load_templates() -> list:
    """Return all saved templates."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM templates ORDER BY name")
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        return rows
    except Exception as exc:
        logger.error("Failed to load templates: %s", exc)
        return []


def delete_template(name: str) -> bool:
    """Delete a template by name. Returns True on success."""
    ph = "%s" if _USE_POSTGRES else "?"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM templates WHERE name = {ph}", (name,))
        conn.commit()
        conn.close()
        logger.info("Template '%s' deleted.", name)
        return True
    except Exception as exc:
        logger.error("Failed to delete template: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Price History
# ---------------------------------------------------------------------------
def save_price_snapshot(iron_price: float, gold_price: float, diamond_price: float) -> None:
    """Record current prices to the price_history table."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ph = "%s" if _USE_POSTGRES else "?"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""INSERT INTO price_history (timestamp, iron_price, gold_price, diamond_price)
               VALUES ({ph}, {ph}, {ph}, {ph})""",
            (date_str, iron_price, gold_price, diamond_price),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("Failed to save price snapshot: %s", exc)


def get_price_history(days: int = 30) -> list:
    """Return price history for the last N days."""
    if _USE_POSTGRES:
        wh = "WHERE timestamp >= (NOW() - INTERVAL '%s days')::text"
    else:
        wh = "WHERE timestamp >= datetime('now', '-' || ? || ' days')"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM price_history {wh} ORDER BY timestamp ASC",
            (str(days),),
        )
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        return rows
    except Exception as exc:
        logger.error("Failed to fetch price history: %s", exc)
        return []


# ---------------------------------------------------------------------------
# History queries
# ---------------------------------------------------------------------------
def get_all_deals(limit: int = 100) -> list:
    """Return the most recent deals."""
    ph = "%s" if _USE_POSTGRES else "?"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM deals ORDER BY id DESC LIMIT {ph}",
            (limit,),
        )
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        return rows
    except Exception as exc:
        logger.error("Failed to fetch deals: %s", exc)
        return []


def get_deal_stats() -> dict:
    """Return aggregate statistics from the deals table."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) AS total_deals,
                COALESCE(SUM(CASE WHEN status LIKE 'ACCEPTED%%' THEN 1 ELSE 0 END), 0) AS accepted,
                COALESCE(SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END), 0) AS rejected,
                COALESCE(SUM(profit), 0) AS total_profit,
                COALESCE(AVG(profit), 0) AS avg_profit,
                COALESCE(SUM(market_value), 0) AS total_market_value
            FROM deals
        """)
        row = _fetchone_as_dict(cursor)
        conn.close()
        return row or {
            "total_deals": 0, "accepted": 0, "rejected": 0,
            "total_profit": 0, "avg_profit": 0, "total_market_value": 0,
        }
    except Exception as exc:
        logger.error("Failed to fetch deal stats: %s", exc)
        return {
            "total_deals": 0, "accepted": 0, "rejected": 0,
            "total_profit": 0, "avg_profit": 0, "total_market_value": 0,
        }


# ---------------------------------------------------------------------------
# Item Lookup Deal logging
# ---------------------------------------------------------------------------
def log_item_deal(
    item_name: str,
    quantity: int,
    unit_price: float,
    total_value: float,
    offered_price: float,
    status: str,
    profit: float,
) -> None:
    """Insert a lookup-item deal into the database."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ph = "%s" if _USE_POSTGRES else "?"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""INSERT INTO item_lookup_deals
               (timestamp, item_name, quantity, unit_price, total_value, offered_price, status, profit)
               VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
            (date_str, item_name, quantity, unit_price, total_value, offered_price, status, profit),
        )
        conn.commit()
        conn.close()
        logger.info("Item lookup deal logged: %s | %s | %s", item_name, status, date_str)
    except Exception as exc:
        logger.error("Failed to log item lookup deal: %s", exc)


def get_item_lookup_deals(limit: int = 100) -> list:
    """Return the most recent item lookup deals."""
    ph = "%s" if _USE_POSTGRES else "?"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM item_lookup_deals ORDER BY id DESC LIMIT {ph}",
            (limit,),
        )
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        return rows
    except Exception as exc:
        logger.error("Failed to fetch item lookup deals: %s", exc)
        return []


def get_item_lookup_stats() -> dict:
    """Return aggregate statistics from the item_lookup_deals table."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) AS total_deals,
                COALESCE(SUM(CASE WHEN status LIKE 'ACCEPTED%%' THEN 1 ELSE 0 END), 0) AS accepted,
                COALESCE(SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END), 0) AS rejected,
                COALESCE(SUM(profit), 0) AS total_profit,
                COALESCE(AVG(profit), 0) AS avg_profit,
                COALESCE(SUM(total_value), 0) AS total_market_value
            FROM item_lookup_deals
        """)
        row = _fetchone_as_dict(cursor)
        conn.close()
        return row or {
            "total_deals": 0, "accepted": 0, "rejected": 0,
            "total_profit": 0, "avg_profit": 0, "total_market_value": 0,
        }
    except Exception as exc:
        logger.error("Failed to fetch item lookup stats: %s", exc)
        return {
            "total_deals": 0, "accepted": 0, "rejected": 0,
            "total_profit": 0, "avg_profit": 0, "total_market_value": 0,
        }


def delete_item_lookup_deal(deal_id: int) -> bool:
    """Delete an item lookup deal by ID. Returns True on success."""
    ph = "%s" if _USE_POSTGRES else "?"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM item_lookup_deals WHERE id = {ph}", (deal_id,))
        conn.commit()
        conn.close()
        logger.info("Item lookup deal %d deleted.", deal_id)
        return True
    except Exception as exc:
        logger.error("Failed to delete item lookup deal %d: %s", deal_id, exc)
        return False


# ---------------------------------------------------------------------------
# Stash (inventory) operations
# ---------------------------------------------------------------------------
DEFAULT_STASH = {
    "id": 1,
    "name": "Default",
    "iron_blocks": 0,
    "iron_ingots": 0,
    "gold_blocks": 0,
    "gold_ingots": 0,
    "diamond_blocks": 0,
    "diamond_items": 0,
    "raw_iron_blocks": 0,
    "raw_gold_blocks": 0,
    "auto_subtract": 0,
    "updated_at": "never",
}


def load_stash() -> dict:
    """Load the current stash from the database. Returns default values if none exists."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM stash WHERE id = 1")
        row = _fetchone_as_dict(cursor)
        conn.close()
        if row:
            # Ensure new fields exist (databases created before the migration)
            row.setdefault("raw_iron_blocks", 0)
            row.setdefault("raw_gold_blocks", 0)
            return row
        return dict(DEFAULT_STASH)
    except Exception as exc:
        logger.warning("Failed to load stash from DB: %s", exc)
        return dict(DEFAULT_STASH)


def save_stash(data: dict) -> None:
    """Insert or replace the stash row with the given data."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if _USE_POSTGRES:
        sql = """INSERT INTO stash
               (id, name, iron_blocks, iron_ingots, gold_blocks, gold_ingots,
                diamond_blocks, diamond_items, raw_iron_blocks, raw_gold_blocks,
                auto_subtract, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 name = EXCLUDED.name,
                 iron_blocks = EXCLUDED.iron_blocks,
                 iron_ingots = EXCLUDED.iron_ingots,
                 gold_blocks = EXCLUDED.gold_blocks,
                 gold_ingots = EXCLUDED.gold_ingots,
                 diamond_blocks = EXCLUDED.diamond_blocks,
                 diamond_items = EXCLUDED.diamond_items,
                 raw_iron_blocks = EXCLUDED.raw_iron_blocks,
                 raw_gold_blocks = EXCLUDED.raw_gold_blocks,
                 auto_subtract = EXCLUDED.auto_subtract,
                 updated_at = EXCLUDED.updated_at"""
    else:
        sql = """INSERT OR REPLACE INTO stash
               (id, name, iron_blocks, iron_ingots, gold_blocks, gold_ingots,
                diamond_blocks, diamond_items, raw_iron_blocks, raw_gold_blocks,
                auto_subtract, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            sql,
            (
                1,
                data.get("name", "Default"),
                int(data.get("iron_blocks", 0)),
                int(data.get("iron_ingots", 0)),
                int(data.get("gold_blocks", 0)),
                int(data.get("gold_ingots", 0)),
                int(data.get("diamond_blocks", 0)),
                int(data.get("diamond_items", 0)),
                int(data.get("raw_iron_blocks", 0)),
                int(data.get("raw_gold_blocks", 0)),
                int(data.get("auto_subtract", 0)),
                date_str,
            ),
        )
        conn.commit()
        conn.close()
        logger.info("Stash saved to database.")
    except Exception as exc:
        logger.error("Failed to save stash to database: %s", exc)


def add_to_stash(
    iron_blocks: int = 0,
    iron_ingots: int = 0,
    gold_blocks: int = 0,
    gold_ingots: int = 0,
    diamond_blocks: int = 0,
    diamond_items: int = 0,
) -> dict:
    """Add materials to the existing stash. Returns the updated stash dict."""
    stash = load_stash()
    stash["iron_blocks"] = int(stash.get("iron_blocks", 0)) + iron_blocks
    stash["iron_ingots"] = int(stash.get("iron_ingots", 0)) + iron_ingots
    stash["gold_blocks"] = int(stash.get("gold_blocks", 0)) + gold_blocks
    stash["gold_ingots"] = int(stash.get("gold_ingots", 0)) + gold_ingots
    stash["diamond_blocks"] = int(stash.get("diamond_blocks", 0)) + diamond_blocks
    stash["diamond_items"] = int(stash.get("diamond_items", 0)) + diamond_items
    save_stash(stash)
    return load_stash()


def clear_stash() -> None:
    """Reset the stash to all zeros."""
    save_stash(dict(DEFAULT_STASH))


def import_items_to_stash(raw_text: str) -> tuple[dict, list[str], list[str]]:
    """
    Parse a raw item dump (e.g. pasted from the game) and replace the entire stash
    with the recognised materials.

    Handles two input formats:
      - Plain: "Iron Ingot:  95"
      - Game log: "[19:28:03] [Render thread/INFO]: [CHAT] Iron Ingot:  95"

    Returns (updated_stash, recognised_lines, skipped_lines).
    """
    import re

    parsed: dict[str, int] = {}
    recognised_lines: list[str] = []
    skipped_lines: list[str] = []

    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue

        # Strip game log prefix: "[timestamp] [thread/LEVEL]: [CHAT] " or similar
        clean = re.sub(r'^\[.*?\]\s*\[.*?\]\s*:\s*\[CHAT\]\s*', '', line)
        # Also handle lines without [CHAT] but with timestamps like "[timestamp] text: count"
        clean = re.sub(r'^\[.*?\]\s*', '', clean)

        # Parse "Item Name:  Count"  (handles multiple spaces)
        if ":" not in clean:
            skipped_lines.append(line)
            continue
        parts = clean.split(":", 1)
        item_name = parts[0].strip()
        try:
            count = int(parts[1].strip().replace(",", ""))
        except (ValueError, IndexError):
            skipped_lines.append(line)
            continue

        # Check if this item name matches a mapped field
        stash_field = _settings.IMPORT_ITEM_MAPPING.get(item_name)
        if stash_field is None:
            skipped_lines.append(line)
            continue

        # Apply any factor (e.g. nugget -> ingot conversion)
        for suffix, factor in _settings.IMPORT_ITEM_FACTORS.items():
            if item_name.lower().endswith(suffix.lower()):
                count = int(count * factor)
                break

        parsed[stash_field] = parsed.get(stash_field, 0) + count
        recognised_lines.append(line)

    # Build new stash: start with all defaults, then overwrite with parsed values
    new_stash = dict(DEFAULT_STASH)
    new_stash["id"] = 1
    new_stash["name"] = "Default"
    for field, count in parsed.items():
        new_stash[field] = count
    new_stash["auto_subtract"] = 0
    new_stash["updated_at"] = "never"

    save_stash(new_stash)
    return load_stash(), recognised_lines, skipped_lines


def get_auto_subtract() -> bool:
    """Return whether auto-subtract is enabled in the stash."""
    stash = load_stash()
    return bool(stash.get("auto_subtract", 0))


def set_auto_subtract(enabled: bool) -> None:
    """Enable or disable the auto-subtract setting in the stash."""
    stash = load_stash()
    stash["auto_subtract"] = 1 if enabled else 0
    save_stash(stash)


def subtract_from_stash(
    iron_ingots: int,
    gold_ingots: int,
    diamond_items: int,
) -> dict:
    """
    Intelligently subtract materials from the stash after a deal.

    Converts ingot amounts back to blocks/items, subtracting from blocks first,
    then from ingots/items. If there aren't enough blocks, the remainder is
    subtracted from ingots. Allows negative results (overdraft).

    Returns a dict describing what was subtracted:
    { "iron_blocks": int, "iron_ingots": int, ... }
    """
    stash = load_stash()

    def _subtract_material(
        stash_blocks: int,
        stash_ingots: int,
        total_ingot_amount: int,
        ingots_per_block: int,
    ) -> tuple:
        total_available = stash_blocks * ingots_per_block + stash_ingots
        amount = total_ingot_amount
        blocks_to_use = min(stash_blocks, amount // ingots_per_block)
        remaining = amount - (blocks_to_use * ingots_per_block)
        ingots_to_use = min(stash_ingots, remaining)
        remaining -= ingots_to_use
        if remaining > 0:
            ingots_to_use += remaining
        new_blocks = stash_blocks - blocks_to_use
        new_ingots = stash_ingots - ingots_to_use
        return new_blocks, new_ingots, blocks_to_use, ingots_to_use

    new_ir_b, new_ir_i, ir_b_used, ir_i_used = _subtract_material(
        stash["iron_blocks"], stash["iron_ingots"],
        int(iron_ingots), _settings.INGOTS_PER_BLOCK,
    )
    new_go_b, new_go_i, go_b_used, go_i_used = _subtract_material(
        stash["gold_blocks"], stash["gold_ingots"],
        int(gold_ingots), _settings.INGOTS_PER_BLOCK,
    )
    new_di_b, new_di_i, di_b_used, di_i_used = _subtract_material(
        stash["diamond_blocks"], stash["diamond_items"],
        int(diamond_items), _settings.INGOTS_PER_BLOCK,
    )

    stash["iron_blocks"] = new_ir_b
    stash["iron_ingots"] = new_ir_i
    stash["gold_blocks"] = new_go_b
    stash["gold_ingots"] = new_go_i
    stash["diamond_blocks"] = new_di_b
    stash["diamond_items"] = new_di_i
    save_stash(stash)

    return {
        "iron_blocks": ir_b_used,
        "iron_ingots": ir_i_used,
        "gold_blocks": go_b_used,
        "gold_ingots": go_i_used,
        "diamond_blocks": di_b_used,
        "diamond_items": di_i_used,
    }
