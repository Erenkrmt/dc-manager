# src/core/database.py
"""
Database module for the DemocracyCraft Trading Toolbox.
Supports SQLite (default, local dev) and PostgreSQL (production via Cloud SQL).
Multi-company: most queries are scoped by company_id.
"""

import os
import logging
import secrets
import hashlib
from datetime import datetime, timezone
from typing import Optional

from src.core.settings import get_settings

_settings = get_settings()

# ── Allowed column names for safe dynamic migration queries ──
_ALLOWED_STASH_COLUMNS = frozenset(
    {"auto_subtract", "raw_iron_blocks", "raw_gold_blocks"}
)
_ALLOWED_COMPANY_COLUMNS = frozenset(
    {"session_token", "session_created_at", "tier", "public_stash_token", "invite_code"}
)

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
        # Determine sslmode: explicit env var wins, else auto-detect
        _sslmode = _settings.DATABASE_SSLMODE
        if not _sslmode:
            # Auto-detect: require for remote hosts, disable for local ones
            _host = _settings.DATABASE_URL.split("@")[-1].split(":")[0]
            _sslmode = (
                "require"
                if _host not in ("postgres", "localhost", "127.0.0.1")
                else "disable"
            )
        conn = psycopg2.connect(
            _settings.DATABASE_URL,
            sslmode=_sslmode,
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
    row = cursor.fetchone()
    return dict(row) if row else None


def _fetchall_as_dicts(cursor) -> list[dict]:
    """Fetch all rows and return as a list of dicts."""
    return [dict(row) for row in cursor.fetchall()]


def _ph() -> str:
    """Return the placeholder for the current backend."""
    return "%s" if _USE_POSTGRES else "?"


# ═══════════════════════════════════════════════════════════════════════════
# Schema DDL (SQLite vs PostgreSQL) — unchanged, migrations handle companies
# ═══════════════════════════════════════════════════════════════════════════

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key TEXT NOT NULL UNIQUE,
    company_name TEXT DEFAULT '',
    access_expires_at TEXT,
    is_active INTEGER DEFAULT 1,
    trial_used INTEGER DEFAULT 0,
    tier TEXT DEFAULT 'free',
    public_stash_token TEXT DEFAULT '',
    invite_code TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    discord_id TEXT NOT NULL,
    discord_username TEXT NOT NULL,
    discord_avatar TEXT DEFAULT '',
    role TEXT DEFAULT 'member',
    session_token TEXT DEFAULT '',
    session_created_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(company_id, discord_id)
);

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER DEFAULT 1,
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
    name TEXT,
    company_id INTEGER DEFAULT 1,
    iron_ingots REAL DEFAULT 0,
    gold_ingots REAL DEFAULT 0,
    diamond_items REAL DEFAULT 0,
    offered_price REAL DEFAULT 0,
    PRIMARY KEY (name, company_id)
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER DEFAULT 1,
    timestamp TEXT NOT NULL,
    iron_price REAL DEFAULT 0,
    gold_price REAL DEFAULT 0,
    diamond_price REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS item_lookup_deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER DEFAULT 1,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER UNIQUE DEFAULT 1,
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
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    api_key TEXT NOT NULL UNIQUE,
    company_name TEXT DEFAULT '',
    access_expires_at TEXT,
    is_active INTEGER DEFAULT 1,
    trial_used INTEGER DEFAULT 0,
    tier TEXT DEFAULT 'free',
    public_stash_token TEXT DEFAULT '',
    invite_code TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_members (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    discord_id TEXT NOT NULL,
    discord_username TEXT NOT NULL,
    discord_avatar TEXT DEFAULT '',
    role TEXT DEFAULT 'member',
    session_token TEXT DEFAULT '',
    session_created_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(company_id, discord_id)
);

CREATE TABLE IF NOT EXISTS deals (
    id SERIAL PRIMARY KEY,
    company_id INTEGER DEFAULT 1,
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
    name TEXT,
    company_id INTEGER DEFAULT 1,
    iron_ingots REAL DEFAULT 0,
    gold_ingots REAL DEFAULT 0,
    diamond_items REAL DEFAULT 0,
    offered_price REAL DEFAULT 0,
    PRIMARY KEY (name, company_id)
);

CREATE TABLE IF NOT EXISTS price_history (
    id SERIAL PRIMARY KEY,
    company_id INTEGER DEFAULT 1,
    timestamp TEXT NOT NULL,
    iron_price REAL DEFAULT 0,
    gold_price REAL DEFAULT 0,
    diamond_price REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS item_lookup_deals (
    id SERIAL PRIMARY KEY,
    company_id INTEGER DEFAULT 1,
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
    id SERIAL PRIMARY KEY,
    company_id INTEGER UNIQUE DEFAULT 1,
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
            # Run migration checks
            _run_pg_migrations(cursor, conn)
        else:
            conn.executescript(_SQLITE_SCHEMA)
            conn.commit()
            _run_sqlite_migrations(conn)

        logger.info(
            "Database initialized (%s).", "PostgreSQL" if _USE_POSTGRES else "SQLite"
        )
    except Exception:
        logger.exception("Failed to initialize database")
        raise
    finally:
        conn.close()


def _run_pg_migrations(cursor, conn) -> None:
    """PostgreSQL-specific column additions — safe dynamic SQL with allowlist."""
    # Allowed column names — validated against allowlist to prevent SQL injection
    for col in ["auto_subtract", "raw_iron_blocks", "raw_gold_blocks"]:
        if col not in _ALLOWED_STASH_COLUMNS:
            logger.warning("Skipping disallowed column '%s' in PG migration.", col)
            continue
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'stash' AND column_name = %s",
            (col,),
        )
        if cursor.fetchone() is None:
            cursor.execute(f"ALTER TABLE stash ADD COLUMN {col} INTEGER DEFAULT 0")
            logger.debug("Migration: added %s column.", col)
    for col in ["session_token", "session_created_at", "tier", "public_stash_token", "invite_code"]:
        if col not in _ALLOWED_COMPANY_COLUMNS:
            logger.warning("Skipping disallowed column '%s' in PG migration.", col)
            continue
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'companies' AND column_name = %s",
            (col,),
        )
        if cursor.fetchone() is None:
            default_val = (
                "''" if col in ("session_token", "public_stash_token", "invite_code") else "'free'"
            )
            cursor.execute(
                f"ALTER TABLE companies ADD COLUMN {col} TEXT DEFAULT {default_val}"
            )
            logger.debug("Migration: added %s column to companies table.", col)
    conn.commit()


def _run_sqlite_migrations(conn) -> None:
    """SQLite-specific column additions — safe dynamic SQL with allowlist."""
    for col in ["auto_subtract", "raw_iron_blocks", "raw_gold_blocks"]:
        if col not in _ALLOWED_STASH_COLUMNS:
            logger.warning("Skipping disallowed column '%s' in SQLite migration.", col)
            continue
        try:
            conn.execute(f"ALTER TABLE stash ADD COLUMN {col} INTEGER DEFAULT 0")
            conn.commit()
            logger.debug("Migration: added %s column.", col)
        except sqlite3.OperationalError:
            pass
    for col in ["session_token", "session_created_at", "tier", "public_stash_token", "invite_code"]:
        if col not in _ALLOWED_COMPANY_COLUMNS:
            logger.warning("Skipping disallowed column '%s' in SQLite migration.", col)
            continue
        try:
            if col == "session_created_at":
                conn.execute(
                    f"ALTER TABLE companies ADD COLUMN {col} TEXT DEFAULT NULL"
                )
            else:
                conn.execute(f"ALTER TABLE companies ADD COLUMN {col} TEXT DEFAULT ''")
            conn.commit()
            logger.debug("Migration: added %s column to companies table.", col)
        except sqlite3.OperationalError:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Company management
# ═══════════════════════════════════════════════════════════════════════════


def _hash_api_key(raw_key: str) -> str:
    """Hash an API key with SHA-256 so it's never stored in plaintext."""
    salt = secrets.token_hex(8)
    hashed = hashlib.sha256(f"{salt}:{raw_key}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def _check_api_key(raw_key: str, stored_hash: str) -> bool:
    """Check a raw API key against the stored hash (salt:hex format)."""
    if ":" not in stored_hash:
        return False
    salt, expected_hash = stored_hash.split(":", 1)
    actual_hash = hashlib.sha256(f"{salt}:{raw_key}".encode()).hexdigest()
    return actual_hash == expected_hash


def _generate_api_key() -> str:
    """Generate a short API key in the format dc_XXXXX."""
    raw_key = f"{_settings.API_KEY_PREFIX}{secrets.token_hex(8)}"
    return raw_key


# ═══════════════════════════════════════════════════════════════════════════
# Company Members (multi-user per company)
# ═══════════════════════════════════════════════════════════════════════════


def _generate_invite_code() -> str:
    """Generate a random invite code."""
    return f"INV-{secrets.token_hex(8)}"


def get_or_create_company_by_discord(
    discord_id: str,
    discord_username: str,
    discord_avatar: str = "",
) -> tuple[dict, dict]:
    """
    Find user's membership OR create a new company + owner membership.
    Returns (company_dict, member_dict).
    """
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # 1. Check if user already has a membership
        cursor.execute(
            f"""SELECT cm.*, c.company_name, c.access_expires_at, c.is_active, c.tier, c.trial_used, c.api_key, c.invite_code
                FROM company_members cm
                JOIN companies c ON c.id = cm.company_id
                WHERE cm.discord_id = {ph}
                ORDER BY cm.role = 'owner' DESC, cm.id ASC
                LIMIT 1""",
            (discord_id,),
        )
        row = _fetchone_as_dict(cursor)

        if row:
            # Update username/avatar
            cursor.execute(
                f"UPDATE company_members SET discord_username = {ph}, discord_avatar = {ph}, updated_at = {ph} WHERE id = {ph}",
                (discord_username, discord_avatar, now, row["id"]),
            )
            conn.commit()

            company = {
                "id": row["company_id"],
                "company_name": row["company_name"],
                "access_expires_at": row["access_expires_at"],
                "is_active": row["is_active"],
                "tier": row["tier"],
                "trial_used": row.get("trial_used", 0),
                "api_key": "",
                "invite_code": row.get("invite_code", ""),
            }
            member = {
                "id": row["id"],
                "company_id": row["company_id"],
                "discord_id": row["discord_id"],
                "discord_username": discord_username,
                "discord_avatar": discord_avatar,
                "role": row["role"],
                "session_token": row.get("session_token", ""),
            }
            return company, member

        # 2. No membership — create new company + owner member
        raw_api_key = _generate_api_key()
        hashed_api_key = _hash_api_key(raw_api_key)
        invite_code = _generate_invite_code()
        trial_end = None
        if _settings.TRIAL_DAYS > 0:
            from datetime import timedelta

            trial_end = (
                datetime.now(timezone.utc) + timedelta(days=_settings.TRIAL_DAYS)
            ).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            f"""INSERT INTO companies (api_key, company_name, access_expires_at, is_active, trial_used, tier, public_stash_token, invite_code, created_at, updated_at)
                VALUES ({ph}, {ph}, {ph}, 1, 1, 'free', '', {ph}, {ph}, {ph})""",
            (hashed_api_key, "", trial_end, invite_code, now, now),
        )
        company_id = cursor.lastrowid if not _USE_POSTGRES else cursor.fetchone()

        # Get the new company ID for PostgreSQL
        if _USE_POSTGRES:
            cursor.execute("SELECT LASTVAL()")
            company_id = cursor.fetchone()["lastval"]

        # Create owner member
        cursor.execute(
            f"""INSERT INTO company_members (company_id, discord_id, discord_username, discord_avatar, role, session_token, session_created_at, created_at, updated_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, 'owner', '', NULL, {ph}, {ph})""",
            (company_id, discord_id, discord_username, discord_avatar, now, now),
        )
        member_id = cursor.lastrowid if not _USE_POSTGRES else 0
        if _USE_POSTGRES:
            cursor.execute("SELECT LASTVAL()")
            member_id = cursor.fetchone()["lastval"]

        conn.commit()

        company = {
            "id": company_id,
            "company_name": "",
            "access_expires_at": trial_end,
            "is_active": True,
            "tier": "free",
            "trial_used": 1,
            "api_key": raw_api_key,
            "invite_code": invite_code,
        }
        member = {
            "id": member_id,
            "company_id": company_id,
            "discord_id": discord_id,
            "discord_username": discord_username,
            "discord_avatar": discord_avatar,
            "role": "owner",
            "session_token": "",
        }
        logger.info("New company created via Discord: %s (%s)", discord_username, discord_id)
        return company, member

    except Exception:
        logger.exception("Failed to get/create company")
        raise
    finally:
        conn.close()


def get_user_companies(discord_id: str) -> list[dict]:
    """
    Return all companies a Discord user belongs to (via company_members).
    Each dict contains company info + member role.
    """
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""SELECT c.id AS company_id, c.company_name, c.is_active, c.access_expires_at, c.tier,
                       cm.id AS member_id, cm.role, cm.discord_username, cm.discord_avatar
                FROM company_members cm
                JOIN companies c ON c.id = cm.company_id
                WHERE cm.discord_id = {ph}
                ORDER BY cm.role = 'owner' DESC, c.company_name ASC""",
            (discord_id,),
        )
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        # Format the responses
        result = []
        for row in rows:
            result.append({
                "company_id": row["company_id"],
                "company_name": row["company_name"] or f"Company #{row['company_id']}",
                "is_active": bool(row["is_active"]),
                "access_expires_at": row["access_expires_at"],
                "tier": row["tier"],
                "member_id": row["member_id"],
                "role": row["role"],
                "discord_username": row["discord_username"],
                "discord_avatar": row["discord_avatar"],
            })
        return result
    except Exception:
        logger.exception("Failed to get user companies")
        return []


def get_company_members(company_id: int) -> list[dict]:
    """Return all members of a company."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""SELECT cm.* FROM company_members cm WHERE cm.company_id = {ph} ORDER BY cm.role = 'owner' DESC, cm.role = 'admin' DESC, cm.discord_username ASC""",
            (company_id,),
        )
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        return rows
    except Exception:
        logger.exception("Failed to get company members")
        return []


def add_company_member(
    company_id: int,
    discord_id: str,
    discord_username: str,
    discord_avatar: str = "",
    role: str = "member",
) -> Optional[dict]:
    """
    Add a new member to a company. Returns the member dict or None if duplicate/failure.
    """
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if already a member
        cursor.execute(
            f"SELECT id FROM company_members WHERE company_id = {ph} AND discord_id = {ph}",
            (company_id, discord_id),
        )
        if cursor.fetchone():
            conn.close()
            return None  # Already a member

        cursor.execute(
            f"""INSERT INTO company_members (company_id, discord_id, discord_username, discord_avatar, role, session_token, session_created_at, created_at, updated_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, '', NULL, {ph}, {ph})""",
            (company_id, discord_id, discord_username, discord_avatar, role, now, now),
        )
        conn.commit()

        # Fetch newly created member
        member_id = cursor.lastrowid if not _USE_POSTGRES else 0
        if _USE_POSTGRES:
            cursor.execute("SELECT LASTVAL()")
            member_id = cursor.fetchone()["lastval"]

        cursor.execute(
            f"SELECT * FROM company_members WHERE id = {ph}",
            (member_id,),
        )
        member = _fetchone_as_dict(cursor)
        conn.close()
        logger.info("Member %s added to company %d as %s", discord_username, company_id, role)
        return member
    except Exception:
        logger.exception("Failed to add company member")
        return None


def remove_company_member(company_id: int, member_id: int) -> bool:
    """
    Remove a member from a company. Cannot remove the last owner.
    """
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if this member is an owner
        cursor.execute(
            f"SELECT role FROM company_members WHERE id = {ph} AND company_id = {ph}",
            (member_id, company_id),
        )
        row = _fetchone_as_dict(cursor)
        if not row:
            conn.close()
            return False

        if row["role"] == "owner":
            # Check if this is the last owner
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM company_members WHERE company_id = {ph} AND role = 'owner'",
                (company_id,),
            )
            owner_count = cursor.fetchone()
            owner_cnt = dict(owner_count)["cnt"] if owner_count else 1
            if owner_cnt <= 1:
                conn.close()
                return False  # Can't remove the last owner

        cursor.execute(
            f"DELETE FROM company_members WHERE id = {ph} AND company_id = {ph}",
            (member_id, company_id),
        )
        conn.commit()
        conn.close()
        logger.info("Member %d removed from company %d", member_id, company_id)
        return True
    except Exception:
        logger.exception("Failed to remove company member")
        return False


def transfer_ownership(company_id: int, current_owner_member_id: int, new_owner_member_id: int) -> bool:
    """
    Transfer company ownership from one member to another.
    The old owner becomes an admin.
    """
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Verify current owner
        cursor.execute(
            f"SELECT id FROM company_members WHERE id = {ph} AND company_id = {ph} AND role = 'owner'",
            (current_owner_member_id, company_id),
        )
        if not cursor.fetchone():
            conn.close()
            return False

        # Verify new owner is a member
        cursor.execute(
            f"SELECT id FROM company_members WHERE id = {ph} AND company_id = {ph}",
            (new_owner_member_id, company_id),
        )
        if not cursor.fetchone():
            conn.close()
            return False

        # Demote old owner to admin
        cursor.execute(
            f"UPDATE company_members SET role = 'admin', updated_at = {ph} WHERE id = {ph}",
            (now, current_owner_member_id),
        )
        # Promote new owner
        cursor.execute(
            f"UPDATE company_members SET role = 'owner', updated_at = {ph} WHERE id = {ph}",
            (now, new_owner_member_id),
        )
        conn.commit()
        conn.close()
        logger.info("Ownership of company %d transferred to member %d", company_id, new_owner_member_id)
        return True
    except Exception:
        logger.exception("Failed to transfer ownership")
        return False


def generate_company_invite_code(company_id: int) -> Optional[str]:
    """Generate a new invite code for a company. Returns the code or None on failure."""
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    invite_code = _generate_invite_code()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE companies SET invite_code = {ph}, updated_at = {ph} WHERE id = {ph}",
            (invite_code, now, company_id),
        )
        conn.commit()
        conn.close()
        logger.info("Invite code regenerated for company %d", company_id)
        return invite_code
    except Exception:
        logger.exception("Failed to generate invite code")
        return None


def get_company_by_invite_code(invite_code: str) -> Optional[dict]:
    """Look up a company by its invite code. Returns None if not found or inactive."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM companies WHERE invite_code = {ph} AND is_active = 1",
            (invite_code,),
        )
        row = _fetchone_as_dict(cursor)
        conn.close()
        return row
    except Exception:
        logger.exception("Failed to look up company by invite code")
        return None


def add_member_by_invite(invite_code: str, discord_id: str, discord_username: str, discord_avatar: str = "") -> Optional[dict]:
    """
    Accept an invite code and add the user as a member to that company.
    Returns the member dict, or None if invalid/already a member.
    """
    company = get_company_by_invite_code(invite_code)
    if not company:
        return None
    return add_company_member(
        company_id=company["id"],
        discord_id=discord_id,
        discord_username=discord_username,
        discord_avatar=discord_avatar,
        role="member",
    )


def update_company_member_role(company_id: int, member_id: int, new_role: str) -> bool:
    """Update a member's role. Cannot change the last owner to a non-owner role."""
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if new_role not in ("owner", "admin", "member"):
        return False
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # If demoting owner, ensure there's another owner
        cursor.execute(
            f"SELECT role FROM company_members WHERE id = {ph} AND company_id = {ph}",
            (member_id, company_id),
        )
        row = _fetchone_as_dict(cursor)
        if not row:
            conn.close()
            return False
        if row["role"] == "owner" and new_role != "owner":
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM company_members WHERE company_id = {ph} AND role = 'owner'",
                (company_id,),
            )
            owner_count = dict(cursor.fetchone())["cnt"]
            if owner_count <= 1:
                conn.close()
                return False

        cursor.execute(
            f"UPDATE company_members SET role = {ph}, updated_at = {ph} WHERE id = {ph} AND company_id = {ph}",
            (new_role, now, member_id, company_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        logger.exception("Failed to update member role")
        return False


def get_company_by_api_key(api_key: str) -> Optional[dict]:
    """Look up a company by hashed API key. Iterates all active companies and checks hash."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM companies WHERE is_active = 1")
        for row in cursor.fetchall():
            stored_hash = dict(row).get("api_key", "")
            if _check_api_key(api_key, stored_hash):
                conn.close()
                return dict(row)
        conn.close()
        return None
    except Exception:
        logger.exception("Failed to lookup company by API key")
        return None


def get_company_by_id(company_id: int) -> Optional[dict]:
    """Return a company by its database ID."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM companies WHERE id = {ph}",
            (company_id,),
        )
        row = _fetchone_as_dict(cursor)
        conn.close()
        return row
    except Exception:
        logger.exception("Failed to get company by ID")
        return None


def list_all_companies() -> list[dict]:
    """Return all companies (admin use)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM companies ORDER BY id ASC")
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        return rows
    except Exception:
        logger.exception("Failed to list companies")
        return []


def update_company_access(company_id: int, days: int) -> bool:
    """
    Extend a company's access by N days from now.
    If currently NULL (permanent), set to now + days.
    If expired, set to now + days.
    Returns True on success.
    """
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    from datetime import timedelta

    new_expiry = (datetime.now(timezone.utc) + timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE companies SET access_expires_at = {ph}, updated_at = {ph} WHERE id = {ph}",
            (new_expiry, now, company_id),
        )
        conn.commit()
        conn.close()
        logger.info(
            "Company %d access extended by %d days to %s", company_id, days, new_expiry
        )
        return True
    except Exception:
        logger.exception("Failed to update company access")
        return False


def update_company_name(company_id: int, name: str) -> bool:
    """Update a company's display name."""
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE companies SET company_name = {ph}, updated_at = {ph} WHERE id = {ph}",
            (name.strip(), now, company_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        logger.exception("Failed to update company name")
        return False


def regenerate_api_key(company_id: int) -> Optional[str]:
    """Generate a new API key for a company. Returns the new key. Stores only the hash in DB."""
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    raw_key = _generate_api_key()
    hashed_key = _hash_api_key(raw_key)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE companies SET api_key = {ph}, updated_at = {ph} WHERE id = {ph}",
            (hashed_key, now, company_id),
        )
        conn.commit()
        conn.close()
        logger.info("API key regenerated for company %d", company_id)
        return raw_key
    except Exception:
        logger.exception("Failed to regenerate API key")
        return None


def deactivate_company(company_id: int) -> bool:
    """Mark a company as inactive."""
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE companies SET is_active = 0, updated_at = {ph} WHERE id = {ph}",
            (now, company_id),
        )
        conn.commit()
        conn.close()
        logger.info("Company %d deactivated.", company_id)
        return True
    except Exception:
        logger.exception("Failed to deactivate company")
        return False


def check_company_access(company_id: int) -> tuple[bool, bool]:
    """
    Check a company's access status.
    Returns (is_active, is_read_only).
    - is_active: company account is active
    - is_read_only: access has expired (can view, cannot modify)
    """
    company = get_company_by_id(company_id)
    if not company or not company.get("is_active"):
        return False, True  # not active = read-only (actually blocked)

    expires_at = company.get("access_expires_at")
    if expires_at is None:
        return True, False  # no expiry = full access (admin)

    try:
        expiry = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
        # Use naive UTC datetime for comparison since stored dates are naive
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if now_utc > expiry:
            return True, True  # active but expired = read-only
        return True, False  # active and not expired = full access
    except (ValueError, TypeError):
        return True, False


def get_company_tier(company_id: int) -> str:
    """Return the tier of a company ('free' or 'premium')."""
    company = get_company_by_id(company_id)
    if company:
        return company.get("tier", "free")
    return "free"


def set_company_tier(company_id: int, tier: str) -> bool:
    """Set a company's tier ('free' or 'premium'). Returns True on success."""
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE companies SET tier = {ph}, updated_at = {ph} WHERE id = {ph}",
            (tier, now, company_id),
        )
        conn.commit()
        conn.close()
        logger.info("Company %d tier set to '%s'.", company_id, tier)
        return True
    except Exception:
        logger.exception("Failed to set company tier")
        return False


def get_company_by_public_token(token: str) -> Optional[dict]:
    """Look up a company by its public stash token. Returns None if not found or inactive."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM companies WHERE public_stash_token = {ph} AND is_active = 1",
            (token,),
        )
        row = _fetchone_as_dict(cursor)
        conn.close()
        return row
    except Exception:
        logger.exception("Failed to look up company by public token")
        return None


def cleanup_expired_sessions(max_age_seconds: int) -> int:
    """
    Remove (clear) session tokens that are older than `max_age_seconds` seconds.
    Sessions are stored per-member in company_members.
    Returns the number of sessions cleaned up.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if _USE_POSTGRES:
            cursor.execute(
                """UPDATE company_members
                   SET session_token = '', session_created_at = NULL, updated_at = %s
                   WHERE session_token != ''
                     AND session_created_at IS NOT NULL
                     AND (EXTRACT(EPOCH FROM %s::timestamp) - EXTRACT(EPOCH FROM session_created_at::timestamp)) > %s""",
                (now, now, max_age_seconds),
            )
        else:
            cursor.execute(
                """UPDATE company_members
                   SET session_token = '', session_created_at = NULL, updated_at = ?
                   WHERE session_token != ''
                     AND session_created_at IS NOT NULL
                     AND (strftime('%s', ?) - strftime('%s', session_created_at)) > ?""",
                (now, now, max_age_seconds),
            )
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        if affected:
            logger.info("Cleaned up %d expired session(s).", affected)
        return affected
    except Exception:
        logger.exception("Failed to cleanup expired sessions")
        return 0


def generate_public_stash_token(company_id: int) -> Optional[str]:
    """Generate a new public stash token for a company. Returns the token string."""
    ph = _ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    token = f"pub_{secrets.token_hex(12)}"  # e.g. pub_abc123... (24 hex chars)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE companies SET public_stash_token = {ph}, updated_at = {ph} WHERE id = {ph}",
            (token, now, company_id),
        )
        conn.commit()
        conn.close()
        logger.info("Public stash token generated for company %d", company_id)
        return token
    except Exception:
        logger.exception("Failed to generate public stash token")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Price cache operations (shared across all companies)
# ═══════════════════════════════════════════════════════════════════════════


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
    except Exception:
        logger.exception("Failed to save cache to DB")


# ═══════════════════════════════════════════════════════════════════════════
# Deal logging
# ═══════════════════════════════════════════════════════════════════════════


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
    company_id: int = 1,
) -> None:
    """Insert a deal record into the database."""
    profit = offered_val - market_value
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ph = _ph()
    sql = f"""INSERT INTO deals
           (company_id, timestamp, iron_ingots, gold_ingots, diamond_items,
            iron_price, gold_price, diamond_price,
            market_value, offered_price, status, profit)
           VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            sql,
            (
                company_id,
                date_str,
                iron_ingots,
                gold_ingots,
                diamonds,
                iron_price,
                gold_price,
                diamond_price,
                market_value,
                offered_val,
                status,
                profit,
            ),
        )
        conn.commit()
        conn.close()
        logger.info("Deal logged to database: %s | %s", status, date_str)
    except Exception:
        logger.exception("Failed to log deal to database")


def update_deal(
    deal_id: int, status: str, offered_price: float, company_id: int = 1
) -> bool:
    """Update a deal's status and/or offered price. Scoped by company_id."""
    ph = _ph()
    sql = f"""UPDATE deals SET status = {ph}, offered_price = {ph},
               profit = {ph} - market_value WHERE id = {ph} AND company_id = {ph}"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (status, offered_price, offered_price, deal_id, company_id))
        conn.commit()
        conn.close()
        logger.info("Deal %d updated: %s | $%.2f", deal_id, status, offered_price)
        return True
    except Exception:
        logger.exception("Failed to update deal %d", deal_id)
        return False


def delete_deal(deal_id: int, company_id: int = 1) -> bool:
    """Delete a deal by ID. Scoped by company_id."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM deals WHERE id = {ph} AND company_id = {ph}",
            (deal_id, company_id),
        )
        conn.commit()
        conn.close()
        logger.info("Deal %d deleted.", deal_id)
        return True
    except Exception:
        logger.exception("Failed to delete deal %d", deal_id)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Deal Templates
# ═══════════════════════════════════════════════════════════════════════════


def save_template(
    name: str,
    iron_ingots: float,
    gold_ingots: float,
    diamond_items: float,
    offered_price: float,
    company_id: int = 1,
) -> bool:
    """Save a deal template. Scoped by company_id."""
    ph = _ph()
    if _USE_POSTGRES:
        sql = f"""INSERT INTO templates (name, company_id, iron_ingots, gold_ingots, diamond_items, offered_price)
                  VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                  ON CONFLICT (name, company_id) DO UPDATE SET
                    iron_ingots = EXCLUDED.iron_ingots,
                    gold_ingots = EXCLUDED.gold_ingots,
                    diamond_items = EXCLUDED.diamond_items,
                    offered_price = EXCLUDED.offered_price"""
    else:
        sql = """INSERT OR REPLACE INTO templates
                 (name, company_id, iron_ingots, gold_ingots, diamond_items, offered_price)
                 VALUES (?, ?, ?, ?, ?, ?)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            sql,
            (name, company_id, iron_ingots, gold_ingots, diamond_items, offered_price),
        )
        conn.commit()
        conn.close()
        logger.info("Template '%s' saved.", name)
        return True
    except Exception:
        logger.exception("Failed to save template")
        return False


def load_templates(company_id: int = 1) -> list:
    """Return all saved templates for a company."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM templates WHERE company_id = {ph} ORDER BY name",
            (company_id,),
        )
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        return rows
    except Exception:
        logger.exception("Failed to load templates")
        return []


def delete_template(name: str, company_id: int = 1) -> bool:
    """Delete a template by name (scoped by company_id)."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM templates WHERE name = {ph} AND company_id = {ph}",
            (name, company_id),
        )
        conn.commit()
        conn.close()
        logger.info("Template '%s' deleted.", name)
        return True
    except Exception:
        logger.exception("Failed to delete template")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Price History
# ═══════════════════════════════════════════════════════════════════════════


def save_price_snapshot(
    iron_price: float,
    gold_price: float,
    diamond_price: float,
    company_id: int = 1,
) -> None:
    """Record current prices to the price_history table."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""INSERT INTO price_history (company_id, timestamp, iron_price, gold_price, diamond_price)
               VALUES ({ph}, {ph}, {ph}, {ph}, {ph})""",
            (company_id, date_str, iron_price, gold_price, diamond_price),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("Failed to save price snapshot")


def get_price_history(days: int = 30, company_id: int = 1) -> list:
    """Return price history for the last N days for a company."""
    ph = _ph()
    if _USE_POSTGRES:
        wh = f"WHERE company_id = {ph} AND timestamp >= (NOW() - INTERVAL '%s days')::text"
    else:
        wh = f"WHERE company_id = {ph} AND timestamp >= datetime('now', '-' || ? || ' days')"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM price_history {wh} ORDER BY timestamp ASC",
            (company_id, str(days)),
        )
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        return rows
    except Exception:
        logger.exception("Failed to fetch price history")
        return []


# ═══════════════════════════════════════════════════════════════════════════
# History queries
# ═══════════════════════════════════════════════════════════════════════════


def get_all_deals(limit: int = 100, company_id: int = 1) -> list:
    """Return the most recent deals for a company. Use company_id=0 for admin (all)."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if company_id == 0:
            cursor.execute(
                f"SELECT * FROM deals ORDER BY id DESC LIMIT {ph}",
                (limit,),
            )
        else:
            cursor.execute(
                f"SELECT * FROM deals WHERE company_id = {ph} ORDER BY id DESC LIMIT {ph}",
                (company_id, limit),
            )
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        return rows
    except Exception:
        logger.exception("Failed to fetch deals")
        return []


def get_deal_stats(company_id: int = 1) -> dict:
    """Return aggregate statistics from the deals table for a company. company_id=0 = all."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if company_id == 0:
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_deals,
                    COALESCE(SUM(CASE WHEN status LIKE 'ACCEPTED%' THEN 1 ELSE 0 END), 0) AS accepted,
                    COALESCE(SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END), 0) AS rejected,
                    COALESCE(SUM(profit), 0) AS total_profit,
                    COALESCE(AVG(profit), 0) AS avg_profit,
                    COALESCE(SUM(market_value), 0) AS total_market_value
                FROM deals
            """)
        else:
            cursor.execute(
                f"""SELECT
                        COUNT(*) AS total_deals,
                        COALESCE(SUM(CASE WHEN status LIKE 'ACCEPTED%' THEN 1 ELSE 0 END), 0) AS accepted,
                        COALESCE(SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END), 0) AS rejected,
                        COALESCE(SUM(profit), 0) AS total_profit,
                        COALESCE(AVG(profit), 0) AS avg_profit,
                        COALESCE(SUM(market_value), 0) AS total_market_value
                    FROM deals WHERE company_id = {ph}""",
                (company_id,),
            )
        row = _fetchone_as_dict(cursor)
        conn.close()
        return row or {
            "total_deals": 0,
            "accepted": 0,
            "rejected": 0,
            "total_profit": 0,
            "avg_profit": 0,
            "total_market_value": 0,
        }
    except Exception:
        logger.exception("Failed to fetch deal stats")
        return {
            "total_deals": 0,
            "accepted": 0,
            "rejected": 0,
            "total_profit": 0,
            "avg_profit": 0,
            "total_market_value": 0,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Item Lookup Deal logging
# ═══════════════════════════════════════════════════════════════════════════


def log_item_deal(
    item_name: str,
    quantity: int,
    unit_price: float,
    total_value: float,
    offered_price: float,
    status: str,
    profit: float,
    company_id: int = 1,
) -> None:
    """Insert a lookup-item deal into the database."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""INSERT INTO item_lookup_deals
               (company_id, timestamp, item_name, quantity, unit_price, total_value, offered_price, status, profit)
               VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
            (
                company_id,
                date_str,
                item_name,
                quantity,
                unit_price,
                total_value,
                offered_price,
                status,
                profit,
            ),
        )
        conn.commit()
        conn.close()
        logger.info(
            "Item lookup deal logged: %s | %s | %s", item_name, status, date_str
        )
    except Exception:
        logger.exception("Failed to log item lookup deal")


def get_item_lookup_deals(limit: int = 100, company_id: int = 1) -> list:
    """Return the most recent item lookup deals for a company. company_id=0 = all."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if company_id == 0:
            cursor.execute(
                f"SELECT * FROM item_lookup_deals ORDER BY id DESC LIMIT {ph}",
                (limit,),
            )
        else:
            cursor.execute(
                f"SELECT * FROM item_lookup_deals WHERE company_id = {ph} ORDER BY id DESC LIMIT {ph}",
                (company_id, limit),
            )
        rows = _fetchall_as_dicts(cursor)
        conn.close()
        return rows
    except Exception:
        logger.exception("Failed to fetch item lookup deals")
        return []


def get_item_lookup_stats(company_id: int = 1) -> dict:
    """Return aggregate statistics from the item_lookup_deals table. company_id=0 = all."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if company_id == 0:
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_deals,
                    COALESCE(SUM(CASE WHEN status LIKE 'ACCEPTED%' THEN 1 ELSE 0 END), 0) AS accepted,
                    COALESCE(SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END), 0) AS rejected,
                    COALESCE(SUM(profit), 0) AS total_profit,
                    COALESCE(AVG(profit), 0) AS avg_profit,
                    COALESCE(SUM(total_value), 0) AS total_market_value
                FROM item_lookup_deals
            """)
        else:
            cursor.execute(
                f"""SELECT
                        COUNT(*) AS total_deals,
                        COALESCE(SUM(CASE WHEN status LIKE 'ACCEPTED%' THEN 1 ELSE 0 END), 0) AS accepted,
                        COALESCE(SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END), 0) AS rejected,
                        COALESCE(SUM(profit), 0) AS total_profit,
                        COALESCE(AVG(profit), 0) AS avg_profit,
                        COALESCE(SUM(total_value), 0) AS total_market_value
                    FROM item_lookup_deals WHERE company_id = {ph}""",
                (company_id,),
            )
        row = _fetchone_as_dict(cursor)
        conn.close()
        return row or {
            "total_deals": 0,
            "accepted": 0,
            "rejected": 0,
            "total_profit": 0,
            "avg_profit": 0,
            "total_market_value": 0,
        }
    except Exception:
        logger.exception("Failed to fetch item lookup stats")
        return {
            "total_deals": 0,
            "accepted": 0,
            "rejected": 0,
            "total_profit": 0,
            "avg_profit": 0,
            "total_market_value": 0,
        }


def delete_item_lookup_deal(deal_id: int, company_id: int = 1) -> bool:
    """Delete an item lookup deal by ID. Scoped by company_id."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM item_lookup_deals WHERE id = {ph} AND company_id = {ph}",
            (deal_id, company_id),
        )
        conn.commit()
        conn.close()
        logger.info("Item lookup deal %d deleted.", deal_id)
        return True
    except Exception:
        logger.exception("Failed to delete item lookup deal %d", deal_id)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Stash (inventory) operations — scoped by company_id
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_STASH = {
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


def load_stash(company_id: int = 1) -> dict:
    """Load the stash for a company. Returns default values if none exists."""
    ph = _ph()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM stash WHERE company_id = {ph}",
            (company_id,),
        )
        row = _fetchone_as_dict(cursor)
        conn.close()
        if row:
            row.setdefault("raw_iron_blocks", 0)
            row.setdefault("raw_gold_blocks", 0)
            return row
        stash = dict(DEFAULT_STASH)
        stash["company_id"] = company_id
        return stash
    except Exception as exc:
        logger.warning("Failed to load stash from DB: %s", exc)
        stash = dict(DEFAULT_STASH)
        stash["company_id"] = company_id
        return stash


def save_stash(data: dict, company_id: int = 1) -> None:
    """Insert or replace the stash row for the given company."""
    ph = _ph()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if _USE_POSTGRES:
        sql = f"""INSERT INTO stash
               (company_id, name, iron_blocks, iron_ingots, gold_blocks, gold_ingots,
                diamond_blocks, diamond_items, raw_iron_blocks, raw_gold_blocks,
                auto_subtract, updated_at)
               VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
               ON CONFLICT (company_id) DO UPDATE SET
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
        sql = f"""INSERT OR REPLACE INTO stash
               (company_id, name, iron_blocks, iron_ingots, gold_blocks, gold_ingots,
                diamond_blocks, diamond_items, raw_iron_blocks, raw_gold_blocks,
                auto_subtract, updated_at)
               VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            sql,
            (
                company_id,
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
        logger.info("Stash saved for company %d.", company_id)
    except Exception:
        logger.exception("Failed to save stash to database")


def add_to_stash(
    iron_blocks: int = 0,
    iron_ingots: int = 0,
    gold_blocks: int = 0,
    gold_ingots: int = 0,
    diamond_blocks: int = 0,
    diamond_items: int = 0,
    company_id: int = 1,
) -> dict:
    """Add materials to the existing stash for a company. Returns the updated stash dict."""
    stash = load_stash(company_id=company_id)
    stash["iron_blocks"] = int(stash.get("iron_blocks", 0)) + iron_blocks
    stash["iron_ingots"] = int(stash.get("iron_ingots", 0)) + iron_ingots
    stash["gold_blocks"] = int(stash.get("gold_blocks", 0)) + gold_blocks
    stash["gold_ingots"] = int(stash.get("gold_ingots", 0)) + gold_ingots
    stash["diamond_blocks"] = int(stash.get("diamond_blocks", 0)) + diamond_blocks
    stash["diamond_items"] = int(stash.get("diamond_items", 0)) + diamond_items
    save_stash(stash, company_id=company_id)
    return load_stash(company_id=company_id)


def clear_stash(company_id: int = 1) -> None:
    """Reset the stash to all zeros for a company."""
    stash = dict(DEFAULT_STASH)
    stash["auto_subtract"] = 0
    save_stash(stash, company_id=company_id)


def import_items_to_stash(
    raw_text: str, company_id: int = 1
) -> tuple[dict, list[str], list[str]]:
    """
    Parse a raw item dump (e.g. pasted from the game) and replace the entire stash
    with the recognised materials for a given company.

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

        clean = re.sub(r"^\[[^\]]*\]\s*\[[^\]]*\]\s*:\s*\[CHAT\]\s*", "", line)
        clean = re.sub(r"^\[[^\]]*\]\s*", "", clean)

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

        stash_field = _settings.IMPORT_ITEM_MAPPING.get(item_name)
        if stash_field is None:
            skipped_lines.append(line)
            continue

        for suffix, factor in _settings.IMPORT_ITEM_FACTORS.items():
            if item_name.lower().endswith(suffix.lower()):
                count = int(count * factor)
                break

        parsed[stash_field] = parsed.get(stash_field, 0) + count
        recognised_lines.append(line)

    new_stash = dict(DEFAULT_STASH)
    new_stash["company_id"] = company_id
    new_stash["name"] = "Default"
    for field, count in parsed.items():
        new_stash[field] = count
    new_stash["auto_subtract"] = 0
    new_stash["updated_at"] = "never"

    save_stash(new_stash, company_id=company_id)
    return load_stash(company_id=company_id), recognised_lines, skipped_lines


def get_auto_subtract(company_id: int = 1) -> bool:
    """Return whether auto-subtract is enabled in the stash for a company."""
    stash = load_stash(company_id=company_id)
    return bool(stash.get("auto_subtract", 0))


def set_auto_subtract(enabled: bool, company_id: int = 1) -> None:
    """Enable or disable the auto-subtract setting in the stash."""
    stash = load_stash(company_id=company_id)
    stash["auto_subtract"] = 1 if enabled else 0
    save_stash(stash, company_id=company_id)


def subtract_from_stash(
    iron_ingots: int,
    gold_ingots: int,
    diamond_items: int,
    company_id: int = 1,
) -> dict:
    """
    Intelligently subtract materials from the stash after a deal, scoped by company.

    Converts ingot amounts back to blocks/items, subtracting from blocks first,
    then from ingots/items. If there aren't enough blocks, the remainder is
    subtracted from ingots. Allows negative results (overdraft).

    Returns a dict describing what was subtracted:
    { "iron_blocks": int, "iron_ingots": int, ... }
    """
    stash = load_stash(company_id=company_id)

    def _subtract_material(
        stash_blocks: int,
        stash_ingots: int,
        total_ingot_amount: int,
        ingots_per_block: int,
    ) -> tuple:
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
        stash["iron_blocks"],
        stash["iron_ingots"],
        int(iron_ingots),
        _settings.INGOTS_PER_BLOCK,
    )
    new_go_b, new_go_i, go_b_used, go_i_used = _subtract_material(
        stash["gold_blocks"],
        stash["gold_ingots"],
        int(gold_ingots),
        _settings.INGOTS_PER_BLOCK,
    )
    new_di_b, new_di_i, di_b_used, di_i_used = _subtract_material(
        stash["diamond_blocks"],
        stash["diamond_items"],
        int(diamond_items),
        _settings.INGOTS_PER_BLOCK,
    )

    stash["iron_blocks"] = new_ir_b
    stash["iron_ingots"] = new_ir_i
    stash["gold_blocks"] = new_go_b
    stash["gold_ingots"] = new_go_i
    stash["diamond_blocks"] = new_di_b
    stash["diamond_items"] = new_di_i
    save_stash(stash, company_id=company_id)

    return {
        "iron_blocks": ir_b_used,
        "iron_ingots": ir_i_used,
        "gold_blocks": go_b_used,
        "gold_ingots": go_i_used,
        "diamond_blocks": di_b_used,
        "diamond_items": di_i_used,
    }
