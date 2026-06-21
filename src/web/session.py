"""
Session token infrastructure for the DC Trade Toolbox.

Provides HMAC-signed, expiry-enforced session tokens for Streamlit and
API authentication. Token format (URL-safe base64):

    base64url(member_id:company_id:created_at:expires_at:hmac_signature)

- Stateless verification: can check validity without a DB hit
- Configurable max age via ``SESSION_MAX_AGE`` in settings
- ``SESSION_SECRET`` auto-generated if not configured
- Sessions are per-member (not per-company), so 1 user with multiple companies
  has independent sessions for each membership.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from src.core.settings import get_settings
from src.core import database as db

logger = logging.getLogger(__name__)

_settings = get_settings()

# ── Derived config ──────────────────────────────────────────────────────────

_SESSION_SECRET: str = (
    _settings.SESSION_SECRET or secrets.token_hex(32)
)
"""If no SESSION_SECRET is configured, generate one per process.
This means sessions are invalidated on server restart — but that's fine
for dev. In production, set a fixed SESSION_SECRET in .env."""

_MAX_AGE: int = _settings.SESSION_MAX_AGE
"""Session token max age in seconds (default 604800 = 7 days)."""


# ── Token helpers ───────────────────────────────────────────────────────────


def _encode_token(payload: dict) -> str:
    """Serialize + base64url-encode a dict payload."""
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode_token(token: str) -> Optional[dict]:
    """Decode a base64url-encoded dict payload. Returns None on failure."""
    try:
        # Add padding back if needed
        padded = token + "=" * (4 - len(token) % 4) if len(token) % 4 else token
        raw = base64.urlsafe_b64decode(padded)
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def _sign_payload(payload: dict) -> str:
    """Return an HMAC-SHA256 hex signature for *payload*."""
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return hmac.new(
        _SESSION_SECRET.encode(), raw, hashlib.sha256
    ).hexdigest()


def _verify_signature(payload: dict, signature: str) -> bool:
    """Constant-time comparison of *signature* against HMAC of *payload*."""
    expected = _sign_payload(payload)
    return hmac.compare_digest(expected, signature)


# ── Public API ──────────────────────────────────────────────────────────────


def generate_session_token(member_id: int, company_id: int) -> str:
    """
    Generate an HMAC-signed session token for the given member/company.

    The token embeds ``mid`` (member_id), ``cid`` (company_id),
    ``iat`` (epoch float), and ``exp`` (epoch float).
    """
    now = time.time()
    payload = {
        "mid": member_id,
        "cid": company_id,
        "iat": now,
        "exp": now + _MAX_AGE,
    }
    sig = _sign_payload(payload)
    token_body = _encode_token(payload)
    return f"{token_body}.{sig}"


def parse_session_token(
    token: str,
) -> Optional[dict]:
    """
    Verify and parse an HMAC-signed session token.

    Returns a dict with keys ``mid``, ``cid``, ``iat``, ``exp`` on success, or
    ``None`` if the token is malformed, tampered with, or expired.
    """
    if "." not in token:
        return None
    token_body, sig = token.rsplit(".", 1)

    payload = _decode_token(token_body)
    if not payload:
        return None

    # Verify signature (tamper detection)
    if not _verify_signature(payload, sig):
        logger.warning("Session token signature mismatch (tampered?)")
        return None

    # Check expiry
    now = time.time()
    exp = payload.get("exp", 0)
    if now > exp:
        logger.debug("Session token expired (age=%.0fs)", now - payload.get("iat", 0))
        return None

    return payload


def store_session(member_id: int) -> str:
    """
    Generate a new session token for this member, persist it in the database,
    and return it.

    The ``company_id`` is read from the member row.
    Also records ``session_created_at`` for cleanup sweeps.
    """
    ph = db._ph()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Look up the member's company_id
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT company_id FROM company_members WHERE id = {ph}",
            (member_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            logger.warning("store_session: member %d not found", member_id)
            return ""
        company_id = dict(row)["company_id"]
        conn.close()
    except Exception:
        logger.exception("Failed to look up member %d", member_id)
        return ""

    token = generate_session_token(member_id, company_id)
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE company_members SET session_token = {ph}, session_created_at = {ph}, "
            f"updated_at = {ph} WHERE id = {ph}",
            (token, now, now, member_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("Failed to persist session token for member %d", member_id)
    return token


def clear_session(member_id: int) -> None:
    """Clear the stored session token from the database for a member."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ph = db._ph()
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE company_members SET session_token = {ph}, session_created_at = NULL, "
            f"updated_at = {ph} WHERE id = {ph}",
            ("", now, member_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("Failed to clear session token for member %d", member_id)


def validate_session(member_id: int, token: str) -> bool:
    """
    Validate a session token against the stored token in the DB.

    Returns True if:
    1. The member has a stored session_token matching this one (constant-time compare).
    2. The token's HMAC signature is intact.
    3. The token hasn't expired.
    """
    ph = db._ph()
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT session_token FROM company_members WHERE id = {ph}",
            (member_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return False
        stored_token = dict(row).get("session_token", "")
        if not stored_token:
            return False
        if not hmac.compare_digest(stored_token, token):
            return False
        # Parse & check expiry
        parsed = parse_session_token(token)
        if not parsed:
            return False
        if parsed.get("mid") != member_id:
            return False
        return True
    except Exception:
        logger.exception("Failed to validate session for member %d", member_id)
        return False


def restore_from_url_param(
    session_param: str,
) -> Optional[dict]:
    """
    Restore a session from a URL query parameter (``mid:cid:token`` format).

    The token is parsed, verified, and then **rotated** (old one consumed,
    new one generated and stored).  Returns a dict of session state fields
    to set, or ``None`` if the token is invalid/expired.

    This is the main entry point for Streamlit's ``?session=...`` flow.
    """
    try:
        parts = session_param.split(":", 2)
        if len(parts) != 3:
            return None
        mid_str, cid_str, token = parts
        mid = int(mid_str)
        cid = int(cid_str)
    except (ValueError, IndexError):
        return None

    # Validate the token
    if not validate_session(mid, token):
        return None

    # Fetch company info
    company = db.get_company_by_id(cid)
    if not company:
        return None

    # Fetch member info
    ph = db._ph()
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM company_members WHERE id = {ph} AND company_id = {ph}",
            (mid, cid),
        )
        member = db._fetchone_as_dict(cursor)
        conn.close()
    except Exception:
        member = None

    if not member:
        return None

    # Token is valid — rotate it (generate new one, consume old)
    new_token = store_session(mid)

    # Check admin & access status
    is_active, is_read_only = db.check_company_access(cid)
    discord_id = member.get("discord_id", "")

    return {
        "company_id": cid,
        "company_name": company.get("company_name", ""),
        "member_id": mid,
        "discord_id": discord_id,
        "discord_username": member.get("discord_username", ""),
        "discord_avatar_url": member.get("discord_avatar", ""),
        "member_role": member.get("role", "member"),
        "session_token": new_token,
        "is_admin": discord_id in _settings.ADMIN_DISCORD_IDS,
        "is_read_only": is_read_only,
        "is_active": is_active,
    }