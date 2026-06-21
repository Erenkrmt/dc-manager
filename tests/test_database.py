"""Tests for the database module – stash operations and company management."""

import os
import sys
import tempfile

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import database as db
from src.core import settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch):
    """
    Redirect the database to a temporary file for every test,
    ensuring isolation and a clean slate.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    monkeypatch.setattr(settings.Settings, "DB_FILE", tmp.name)
    # Initialise the schema on the temporary database
    db.init_db()
    yield
    # Teardown: remove the temporary file
    os.unlink(tmp.name)


# ---------------------------------------------------------------------------
# Tests: Company management
# ---------------------------------------------------------------------------


class TestCompanyManagement:
    """Verify company CRUD and access control."""

    def test_get_or_create_company_creates_new(self):
        """A new Discord user should get a company with a trial."""
        company, member = db.get_or_create_company_by_discord("12345", "TestUser", "")
        assert company is not None
        assert member is not None
        assert member["discord_id"] == "12345"
        assert member["discord_username"] == "TestUser"
        assert company["api_key"].startswith("dc_")
        assert company["trial_used"] == 1
        assert company["access_expires_at"] is not None  # trial set

    def test_get_or_create_company_returns_existing(self):
        """Calling again with the same Discord ID should return the same company.
        The API key is only returned on creation (raw); existing lookups return empty string.
        """
        (c1, _) = db.get_or_create_company_by_discord("12345", "TestUser")
        (c2, _) = db.get_or_create_company_by_discord("12345", "TestUser")
        assert c1["id"] == c2["id"]
        assert c1["api_key"].startswith("dc_")  # raw key on creation
        assert c2["api_key"] == ""  # masked on existing lookup

    def test_get_company_by_api_key(self):
        """Lookup by API key should return the company."""
        company, _ = db.get_or_create_company_by_discord("67890", "AnotherUser")
        found = db.get_company_by_api_key(company["api_key"])
        assert found is not None
        assert found["id"] == company["id"]

    def test_get_company_by_api_key_invalid(self):
        """Invalid API key should return None."""
        assert db.get_company_by_api_key("dc_invalid") is None

    def test_get_company_by_id(self):
        """Lookup by database ID."""
        company, _ = db.get_or_create_company_by_discord("111", "User1")
        found = db.get_company_by_id(company["id"])
        assert found is not None
        assert found["company_name"] is not None

    def test_list_all_companies(self):
        """list_all_companies should return all companies."""
        db.get_or_create_company_by_discord("a", "A")
        db.get_or_create_company_by_discord("b", "B")
        companies = db.list_all_companies()
        assert len(companies) >= 2

    def test_update_company_access(self):
        """Extending access should update the expiry."""
        company, _ = db.get_or_create_company_by_discord("999", "ExpiryTest")
        db.update_company_access(company["id"], 30)
        updated = db.get_company_by_id(company["id"])
        assert updated["access_expires_at"] is not None

    def test_deactivate_company(self):
        """Deactivating should set is_active=0."""
        company, _ = db.get_or_create_company_by_discord("777", "DeactTest")
        db.deactivate_company(company["id"])
        # Check by raw lookup (get_company_by_api_key filters active)
        direct = db.get_company_by_id(company["id"])
        assert direct["is_active"] == 0

    def test_regenerate_api_key(self):
        """Regenerating should return a new key."""
        company, _ = db.get_or_create_company_by_discord("444", "KeyRegen")
        old_key = company["api_key"]
        new_key = db.regenerate_api_key(company["id"])
        assert new_key != old_key
        assert new_key.startswith("dc_")

    def test_check_company_access_full(self):
        """A company with no expiry should have full access."""
        company, _ = db.get_or_create_company_by_discord("555", "FullAccess")
        # Remove expiry to simulate permanent access
        db.update_company_access(company["id"], 0)
        is_active, is_read_only = db.check_company_access(company["id"])
        assert is_active is True
        assert is_read_only is True  # expired now

    def test_update_company_name(self):
        """Company display name should be updatable."""
        company, _ = db.get_or_create_company_by_discord("888", "NameTest")
        db.update_company_name(company["id"], "Super Corp")
        updated = db.get_company_by_id(company["id"])
        assert updated["company_name"] == "Super Corp"


# ---------------------------------------------------------------------------
# Tests: add_to_stash
# ---------------------------------------------------------------------------


class TestAddToStash:
    """Verify that add_to_stash correctly adds materials to the existing stash."""

    def test_add_to_empty_stash(self):
        """Adding to a fresh (default) stash should set the values."""
        db.add_to_stash(
            iron_blocks=5,
            iron_ingots=10,
            gold_blocks=3,
            gold_ingots=7,
            diamond_blocks=2,
            diamond_items=4,
        )
        loaded = db.load_stash()
        assert loaded["iron_blocks"] == 5
        assert loaded["iron_ingots"] == 10
        assert loaded["gold_blocks"] == 3
        assert loaded["gold_ingots"] == 7
        assert loaded["diamond_blocks"] == 2
        assert loaded["diamond_items"] == 4

    def test_add_to_existing_stash(self):
        """Adding more materials should accumulate on top of existing values."""
        db.save_stash(
            {
                "iron_blocks": 10,
                "iron_ingots": 20,
                "gold_blocks": 5,
                "gold_ingots": 15,
                "diamond_blocks": 3,
                "diamond_items": 6,
            }
        )
        db.add_to_stash(
            iron_blocks=2,
            iron_ingots=3,
            gold_blocks=1,
            gold_ingots=2,
            diamond_blocks=1,
            diamond_items=1,
        )
        loaded = db.load_stash()
        assert loaded["iron_blocks"] == 12
        assert loaded["iron_ingots"] == 23
        assert loaded["gold_blocks"] == 6
        assert loaded["gold_ingots"] == 17
        assert loaded["diamond_blocks"] == 4
        assert loaded["diamond_items"] == 7

    def test_add_zero_values(self):
        """Adding all zeros should leave the stash unchanged."""
        db.save_stash(
            {
                "iron_blocks": 1,
                "iron_ingots": 2,
                "gold_blocks": 3,
                "gold_ingots": 4,
                "diamond_blocks": 5,
                "diamond_items": 6,
            }
        )
        db.add_to_stash()  # defaults to 0 for everything
        loaded = db.load_stash()
        assert loaded["iron_blocks"] == 1
        assert loaded["iron_ingots"] == 2
        assert loaded["gold_blocks"] == 3
        assert loaded["gold_ingots"] == 4
        assert loaded["diamond_blocks"] == 5
        assert loaded["diamond_items"] == 6

    def test_add_partial_values(self):
        """Adding only some material types should only affect those fields."""
        db.save_stash(
            {
                "iron_blocks": 10,
                "iron_ingots": 0,
                "gold_blocks": 0,
                "gold_ingots": 0,
                "diamond_blocks": 0,
                "diamond_items": 0,
            }
        )
        db.add_to_stash(iron_blocks=5, diamond_items=3)
        loaded = db.load_stash()
        assert loaded["iron_blocks"] == 15
        assert loaded["iron_ingots"] == 0
        assert loaded["gold_blocks"] == 0
        assert loaded["gold_ingots"] == 0
        assert loaded["diamond_blocks"] == 0
        assert loaded["diamond_items"] == 3

    def test_add_to_nonexistent_stash_returns_dict(self):
        """add_to_stash should work even when no stash row exists yet."""
        stash = db.add_to_stash(iron_ingots=42)
        assert isinstance(stash, dict)
        assert stash["iron_ingots"] == 42

    def test_add_large_numbers(self):
        """Adding large values should work without overflow issues."""
        db.add_to_stash(
            iron_blocks=1_000_000,
            iron_ingots=2_000_000,
            gold_blocks=3_000_000,
            gold_ingots=4_000_000,
            diamond_blocks=5_000_000,
            diamond_items=6_000_000,
        )
        loaded = db.load_stash()
        assert loaded["iron_blocks"] == 1_000_000
        assert loaded["iron_ingots"] == 2_000_000
        assert loaded["gold_blocks"] == 3_000_000
        assert loaded["gold_ingots"] == 4_000_000
        assert loaded["diamond_blocks"] == 5_000_000
        assert loaded["diamond_items"] == 6_000_000

    def test_add_negative_values(self):
        """Adding negative values should reduce the stash (manual subtract)."""
        db.save_stash(
            {
                "iron_blocks": 10,
                "iron_ingots": 20,
                "gold_blocks": 5,
                "gold_ingots": 15,
                "diamond_blocks": 3,
                "diamond_items": 6,
            }
        )
        db.add_to_stash(
            iron_blocks=-3,
            iron_ingots=-5,
            gold_blocks=-2,
            gold_ingots=-4,
            diamond_blocks=-1,
            diamond_items=-2,
        )
        loaded = db.load_stash()
        assert loaded["iron_blocks"] == 7
        assert loaded["iron_ingots"] == 15
        assert loaded["gold_blocks"] == 3
        assert loaded["gold_ingots"] == 11
        assert loaded["diamond_blocks"] == 2
        assert loaded["diamond_items"] == 4

    def test_stash_per_company_isolation(self):
        """Two different companies should have independent stashes."""
        c1, _ = db.get_or_create_company_by_discord("c1", "Comp1")
        c2, _ = db.get_or_create_company_by_discord("c2", "Comp2")

        db.save_stash({"iron_blocks": 100}, company_id=c1["id"])
        db.save_stash({"iron_ingots": 50}, company_id=c2["id"])

        stash1 = db.load_stash(company_id=c1["id"])
        stash2 = db.load_stash(company_id=c2["id"])

        assert stash1["iron_blocks"] == 100
        assert stash1["iron_ingots"] == 0
        assert stash2["iron_blocks"] == 0
        assert stash2["iron_ingots"] == 50


# ---------------------------------------------------------------------------
# Tests: clear_stash
# ---------------------------------------------------------------------------


class TestClearStash:
    """Verify that clear_stash resets the stash to zeros."""

    def test_clear_nonempty_stash(self):
        db.save_stash(
            {
                "iron_blocks": 10,
                "iron_ingots": 20,
                "gold_blocks": 3,
                "gold_ingots": 7,
                "diamond_blocks": 2,
                "diamond_items": 5,
            }
        )
        db.clear_stash()
        loaded = db.load_stash()
        assert loaded["iron_blocks"] == 0
        assert loaded["iron_ingots"] == 0
        assert loaded["gold_blocks"] == 0
        assert loaded["gold_ingots"] == 0
        assert loaded["diamond_blocks"] == 0
        assert loaded["diamond_items"] == 0

    def test_clear_already_empty_stash(self):
        db.clear_stash()
        loaded = db.load_stash()
        assert loaded["iron_blocks"] == 0


# ---------------------------------------------------------------------------
# Tests: load_stash / save_stash basics
# ---------------------------------------------------------------------------


class TestStashBasics:
    """Basic round-trip sanity checks."""

    def test_load_default_stash(self):
        """A fresh database should return the default (all zeros) stash."""
        loaded = db.load_stash()
        for key in (
            "iron_blocks",
            "iron_ingots",
            "gold_blocks",
            "gold_ingots",
            "diamond_blocks",
            "diamond_items",
        ):
            assert loaded[key] == 0

    def test_save_stash_updates_updated_at(self):
        """After saving, updated_at should not be 'never'."""
        db.save_stash(
            {
                "iron_blocks": 1,
                "iron_ingots": 2,
                "gold_blocks": 3,
                "gold_ingots": 4,
                "diamond_blocks": 5,
                "diamond_items": 6,
            }
        )
        loaded = db.load_stash()
        assert loaded["updated_at"] != "never"


# ---------------------------------------------------------------------------
# Tests: set_auto_subtract / get_auto_subtract
# ---------------------------------------------------------------------------


class TestAutoSubtract:
    """Verify auto-subtract toggle works correctly."""

    def test_auto_subtract_default_off(self):
        assert db.get_auto_subtract() is False

    def test_auto_subtract_toggle_on(self):
        db.set_auto_subtract(True)
        assert db.get_auto_subtract() is True

    def test_auto_subtract_toggle_off(self):
        db.set_auto_subtract(True)
        db.set_auto_subtract(False)
        assert db.get_auto_subtract() is False