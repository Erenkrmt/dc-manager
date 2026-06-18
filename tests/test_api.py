"""Tests for the FastAPI REST API endpoints."""

import os
import sys
import tempfile

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import database as db
from src.core import constants


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch):
    """Redirect the database to a temporary file for every test."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    monkeypatch.setattr(constants, "DB_FILE", tmp.name)
    db.init_db()
    yield
    os.unlink(tmp.name)


@pytest.fixture(scope="module")
def client():
    """Create a Starlette TestClient for the FastAPI app."""
    from starlette.testclient import TestClient
    from src.web.api import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests: /stash endpoints
# ---------------------------------------------------------------------------

class TestStashEndpoint:
    """Test the /stash GET endpoint."""

    def test_get_stash_default(self, client):
        """A fresh stash should return default (zero) values with ingot equivalents."""
        r = client.get("/stash")
        assert r.status_code == 200
        data = r.json()
        assert data["iron_blocks"] == 0
        assert data["iron_ingots"] == 0
        assert data["gold_blocks"] == 0
        assert data["gold_ingots"] == 0
        assert data["diamond_blocks"] == 0
        assert data["diamond_items"] == 0
        # Should include computed total_ingots
        assert "total_ingots" in data
        assert data["total_ingots"]["iron"] == 0

    def test_get_stash_with_values(self, client):
        """After saving some stash, /stash should reflect the values."""
        db.save_stash({
            "iron_blocks": 10,
            "iron_ingots": 5,
            "gold_blocks": 3,
            "gold_ingots": 2,
            "diamond_blocks": 1,
            "diamond_items": 7,
        })
        r = client.get("/stash")
        assert r.status_code == 200
        data = r.json()
        assert data["iron_blocks"] == 10
        assert data["iron_ingots"] == 5
        assert data["total_ingots"]["iron"] == 10 * 9 + 5

    def test_get_stash_raw(self, client):
        """The raw endpoint should not include computed fields."""
        db.save_stash({"iron_blocks": 5})
        r = client.get("/stash/raw")
        assert r.status_code == 200
        data = r.json()
        assert data["iron_blocks"] == 5
        assert "total_ingots" not in data

    def test_get_auto_subtract_default(self, client):
        """Auto-subtract should default to false."""
        r = client.get("/stash/auto_subtract")
        assert r.status_code == 200
        assert r.json()["auto_subtract"] is False

    def test_get_auto_subtract_enabled(self, client):
        """After enabling, the endpoint should return true."""
        db.set_auto_subtract(True)
        r = client.get("/stash/auto_subtract")
        assert r.status_code == 200
        assert r.json()["auto_subtract"] is True


# ---------------------------------------------------------------------------
# Tests: /health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Test the /health GET endpoint."""

    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "database" in data


# ---------------------------------------------------------------------------
# Tests: /deals endpoints
# ---------------------------------------------------------------------------

class TestDealsEndpoint:
    """Test the /deals GET endpoints."""

    def test_deals_stats_empty(self, client):
        """With no deals, stats should return zeros."""
        r = client.get("/deals/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_deals"] == 0
        assert data["accepted"] == 0
        assert data["rejected"] == 0

    def test_deals_list_empty(self, client):
        """With no deals, the deals list should be empty."""
        r = client.get("/deals")
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# Tests: /prices endpoint
# ---------------------------------------------------------------------------

class TestPricesEndpoint:
    """Test the /prices GET endpoint."""

    def test_prices_structure(self, client):
        """The prices endpoint should return a prices dict with expected keys."""
        r = client.get("/prices")
        assert r.status_code == 200
        data = r.json()
        assert "prices" in data
        for key in ("Iron Ingot", "Gold Ingot", "Diamond"):
            assert key in data["prices"]
            assert isinstance(data["prices"][key], float)