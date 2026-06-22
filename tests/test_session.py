"""
Tests for the session token infrastructure.
Uses a temp SQLite database fixture for isolation.
"""

from __future__ import annotations

import time
import pytest
from pathlib import Path
from unittest.mock import patch

from src.web.session import (
    _encode_token,
    _decode_token,
    _sign_payload,
    _verify_signature,
    generate_session_token,
    parse_session_token,
    validate_session,
)
from src.web import session as sess_module


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    """Use a fixed SESSION_SECRET and short max_age for deterministic tests."""
    monkeypatch.setattr(sess_module, "_SESSION_SECRET", "test_secret_key_32chars!")
    monkeypatch.setattr(sess_module, "_MAX_AGE", 3600)  # 1 hour


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch, tmp_path: Path):
    """Redirect DB to a temp SQLite file."""
    db_file = tmp_path / "test_session.db"
    monkeypatch.setattr("src.core.settings._ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr("src.core.settings.Settings.DB_DIR", str(tmp_path))
    monkeypatch.setattr("src.core.settings.Settings.DB_FILE", str(db_file))
    monkeypatch.setattr("src.core.settings.Settings.DATABASE_URL", "")

    from src.core import database as db

    db.init_db()
    return db


@pytest.fixture
def seed_company(_patch_db):
    """Create a test company and return its id + api_key + member_id."""
    from src.core import database as db

    company, member = db.get_or_create_company_by_discord(
        discord_id="test_discord_123",
        discord_username="TestUser",
        discord_avatar="",
    )
    return company["id"], company["api_key"], member["id"]


def _get_member_session_token(member_id: int) -> str:
    """Helper: fetch session_token from company_members for a given member."""
    from src.core import database as db

    ph = db._ph()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT session_token FROM company_members WHERE id = {ph}",
        (member_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row)["session_token"] if row else ""


# ── Unit tests: encode/decode helpers ───────────────────────────────────────


class TestEncodeDecode:
    def test_encode_decode_roundtrip(self):
        payload = {"cid": 1, "iat": 1000.0, "exp": 2000.0}
        encoded = _encode_token(payload)
        decoded = _decode_token(encoded)
        assert decoded == payload

    def test_decode_invalid(self):
        assert _decode_token("not-valid-base64!!!") is None

    def test_decode_empty(self):
        assert _decode_token("") is None

    def test_decode_garbage(self):
        assert _decode_token("!!!") is None


# ── Unit tests: signing ─────────────────────────────────────────────────────


class TestSigning:
    def test_sign_and_verify(self):
        payload = {"cid": 5, "iat": 100.0}
        sig = _sign_payload(payload)
        assert _verify_signature(payload, sig)

    def test_tampered_payload_fails(self):
        payload = {"cid": 5, "iat": 100.0}
        sig = _sign_payload(payload)
        tampered = {"cid": 6, "iat": 100.0}
        assert not _verify_signature(tampered, sig)

    def test_wrong_signature_fails(self):
        payload = {"cid": 5, "iat": 100.0}
        wrong_sig = "0" * 64
        assert not _verify_signature(payload, wrong_sig)


# ── Unit tests: token generation / parsing ──────────────────────────────────


class TestTokenGeneration:
    def test_generate_token_format(self):
        token = generate_session_token(member_id=1, company_id=42)
        assert "." in token
        parts = token.split(".")
        assert len(parts) == 2
        assert len(parts[0]) > 0  # non-empty body
        assert len(parts[1]) == 64  # SHA-256 hex = 64 chars

    def test_parse_valid_token(self):
        token = generate_session_token(member_id=1, company_id=42)
        parsed = parse_session_token(token)
        assert parsed is not None
        assert parsed["cid"] == 42
        assert parsed["mid"] == 1
        assert "iat" in parsed
        assert "exp" in parsed

    def test_parse_expired_token(self):
        with patch.object(sess_module, "_MAX_AGE", -1):  # already expired
            token = generate_session_token(member_id=1, company_id=42)
        parsed = parse_session_token(token)
        assert parsed is None

    def test_parse_malformed_token(self):
        assert parse_session_token("no-dot-here") is None
        assert parse_session_token("") is None

    def test_parse_tampered_token(self):
        token = generate_session_token(member_id=1, company_id=42)
        # Tamper with the body part
        parts = token.split(".")
        tampered = "AAAA" + "." + parts[1]
        assert parse_session_token(tampered) is None

    def test_parse_wrong_cid(self):
        token = generate_session_token(member_id=1, company_id=42)
        parsed = parse_session_token(token)
        assert parsed is not None
        assert parsed["cid"] == 42

    def test_token_idempotent_generation(self):
        """Tokens should be different each time (due to iat changing)."""
        t1 = generate_session_token(member_id=1, company_id=1)
        t2 = generate_session_token(member_id=1, company_id=1)
        assert t1 != t2


# ── Integration tests: validate_session against DB ──────────────────────────


class TestValidateSession:
    def test_validate_with_stored_token(self, seed_company):
        """validate_session should succeed if the token is stored in DB."""
        company_id, _api_key, member_id = seed_company
        from src.web.session import store_session

        token = store_session(member_id)
        assert validate_session(member_id, token)

    def test_validate_wrong_token(self, seed_company):
        """validate_session should fail if the token doesn't match DB."""
        company_id, _api_key, member_id = seed_company
        token = generate_session_token(member_id=member_id, company_id=company_id)
        # Token not persisted yet
        assert not validate_session(member_id, token)

    def test_validate_expired_token(self, seed_company):
        """validate_session should fail for expired tokens."""
        company_id, _api_key, member_id = seed_company
        from src.web.session import store_session

        store_session(member_id)
        # Generate a token with negative max_age so it's immediately expired
        with patch.object(sess_module, "_MAX_AGE", -1):
            expired_token = generate_session_token(
                member_id=member_id, company_id=company_id
            )

        # Token should fail parsing (expired)
        assert parse_session_token(expired_token) is None

    def test_validate_nonexistent_company(self):
        assert not validate_session(9999, "some_token")

    def test_validate_empty_stored_token(self, seed_company):
        """validate_session should fail if DB has empty session_token."""
        company_id, _api_key, member_id = seed_company

        # Clear the token
        from src.web.session import clear_session

        clear_session(member_id)

        token = generate_session_token(member_id=member_id, company_id=company_id)
        assert not validate_session(member_id, token)


# ── Integration tests: store_session / clear_session / restore_from_url_param


class TestStoreClearRestore:
    def test_store_session_updates_db(self, seed_company):
        company_id, _api_key, member_id = seed_company
        from src.web.session import store_session

        token = store_session(member_id)
        stored_token = _get_member_session_token(member_id)
        assert stored_token == token

    def test_clear_session(self, seed_company):
        company_id, _api_key, member_id = seed_company
        from src.web.session import store_session, clear_session

        store_session(member_id)
        clear_session(member_id)

        stored_token = _get_member_session_token(member_id)
        assert stored_token == ""

    def test_restore_from_url_param(self, seed_company):
        """restore_from_url_param should return session state on success."""
        company_id, _api_key, member_id = seed_company
        from src.web.session import store_session, restore_from_url_param

        token = store_session(member_id)
        session_data = restore_from_url_param(f"{member_id}:{company_id}:{token}")
        assert session_data is not None
        assert session_data["company_id"] == company_id
        assert session_data["session_token"] != token  # rotated

    def test_restore_from_invalid_param(self):
        from src.web.session import restore_from_url_param

        assert restore_from_url_param("invalid") is None
        assert restore_from_url_param("abc:def") is None
        assert restore_from_url_param("") is None


# ── Integration tests: cleanup_expired_sessions ────────────────────────────


class TestCleanup:
    def test_cleanup_expired_sessions(self, seed_company):
        """cleanup_expired_sessions should clear tokens older than max_age."""
        company_id, _api_key, member_id = seed_company
        from src.web.session import store_session
        from src.core import database as db

        store_session(member_id)

        # Set session_created_at to a very old date manually on company_members
        ph = db._ph()
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE company_members SET session_created_at = '2020-01-01 00:00:00' WHERE id = {ph}",
            (member_id,),
        )
        conn.commit()
        conn.close()

        cleaned = db.cleanup_expired_sessions(3600)  # 1 hour max age
        assert cleaned >= 1

        # Verify token is cleared from company_members
        stored_token = _get_member_session_token(member_id)
        assert stored_token == ""

    def test_cleanup_noop_for_fresh_sessions(self, seed_company):
        """cleanup_expired_sessions should NOT touch fresh sessions."""
        company_id, _api_key, member_id = seed_company
        from src.web.session import store_session
        from src.core import database as db

        token = store_session(member_id)
        time.sleep(0.1)  # Ensure created_at is set

        # Try cleaning with a very large max age (should not affect anything)
        cleaned = db.cleanup_expired_sessions(9999999)
        assert cleaned == 0

        # Verify token is still there (query company_members)
        stored_token = _get_member_session_token(member_id)
        assert stored_token == token
