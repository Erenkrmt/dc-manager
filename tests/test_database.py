"""Tests for the database module – stash operations."""

import os
import sys
import tempfile

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import database as db
from src.core import constants


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
    monkeypatch.setattr(constants, "DB_FILE", tmp.name)
    # Initialise the schema on the temporary database
    db.init_db()
    yield
    # Teardown: remove the temporary file
    os.unlink(tmp.name)


# ---------------------------------------------------------------------------
# Tests: add_to_stash
# ---------------------------------------------------------------------------

class TestAddToStash:
    """Verify that add_to_stash correctly adds materials to the existing stash."""

    def test_add_to_empty_stash(self):
        """Adding to a fresh (default) stash should set the values."""
        stash = db.add_to_stash(
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
        db.save_stash({
            "iron_blocks": 10,
            "iron_ingots": 20,
            "gold_blocks": 5,
            "gold_ingots": 15,
            "diamond_blocks": 3,
            "diamond_items": 6,
        })
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
        db.save_stash({
            "iron_blocks": 1,
            "iron_ingots": 2,
            "gold_blocks": 3,
            "gold_ingots": 4,
            "diamond_blocks": 5,
            "diamond_items": 6,
        })
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
        db.save_stash({
            "iron_blocks": 10,
            "iron_ingots": 0,
            "gold_blocks": 0,
            "gold_ingots": 0,
            "diamond_blocks": 0,
            "diamond_items": 0,
        })
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
        # The returned value should be a dict with our added value
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
        db.save_stash({
            "iron_blocks": 10,
            "iron_ingots": 20,
            "gold_blocks": 5,
            "gold_ingots": 15,
            "diamond_blocks": 3,
            "diamond_items": 6,
        })
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


# ---------------------------------------------------------------------------
# Tests: clear_stash
# ---------------------------------------------------------------------------

class TestClearStash:
    """Verify that clear_stash resets the stash to zeros."""

    def test_clear_nonempty_stash(self):
        db.save_stash({
            "iron_blocks": 10,
            "iron_ingots": 20,
            "gold_blocks": 3,
            "gold_ingots": 7,
            "diamond_blocks": 2,
            "diamond_items": 5,
        })
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
        # Should not raise – just stays at zeros
        assert loaded["iron_blocks"] == 0


# ---------------------------------------------------------------------------
# Tests: load_stash / save_stash basics
# ---------------------------------------------------------------------------

class TestStashBasics:
    """Basic round-trip sanity checks."""

    def test_load_default_stash(self):
        """A fresh database should return the default (all zeros) stash."""
        loaded = db.load_stash()
        for key in ("iron_blocks", "iron_ingots", "gold_blocks",
                     "gold_ingots", "diamond_blocks", "diamond_items"):
            assert loaded[key] == 0

    def test_save_stash_updates_updated_at(self):
        """After saving, updated_at should not be 'never'."""
        db.save_stash({
            "iron_blocks": 1,
            "iron_ingots": 2,
            "gold_blocks": 3,
            "gold_ingots": 4,
            "diamond_blocks": 5,
            "diamond_items": 6,
        })
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