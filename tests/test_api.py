"""Tests for the FastAPI REST API endpoints — multi-company edition."""

import os
import sys
import tempfile

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import database as db
from src.core import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_company() -> tuple:
    """Create a test company and return (company_dict, api_key)."""
    company = db.get_or_create_company_by_discord("test_discord_id", "TestUser", "")
    # Remove expiry so it has full write access
    db.update_company_access(company["id"], 30)
    return company, company["api_key"]


# ---------------------------------------------------------------------------
# Fixture: temp DB
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch):
    """Redirect the database to a temporary file for every test."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    monkeypatch.setattr(settings.Settings, "DB_FILE", tmp.name)
    monkeypatch.setenv("DC_API_KEY", "test_dc_api_key_for_ci")
    db.init_db()
    yield
    os.unlink(tmp.name)


# ---------------------------------------------------------------------------
# Fixture: TestClient + FastAPI app
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Create a Starlette TestClient for the FastAPI app."""
    from starlette.testclient import TestClient
    from src.web.api import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests: Auth / Company endpoints
# ---------------------------------------------------------------------------


class TestAuthEndpoints:
    """Test auth and company management endpoints."""

    def test_auth_me_with_valid_key(self, client):
        """GET /auth/me should return company info when valid API key provided."""
        company, api_key = _create_company()
        r = client.get("/auth/me", headers={"X-API-Key": api_key})
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == company["id"]
        assert data["discord_username"] == "TestUser"

    def test_auth_me_with_invalid_key(self, client):
        """GET /auth/me should return 401 when no API key provided."""
        r = client.get("/auth/me")
        assert r.status_code == 401

    def test_auth_me_with_bad_key(self, client):
        """GET /auth/me should return 401 for an invalid API key."""
        r = client.get("/auth/me", headers={"X-API-Key": "dc_badkey"})
        assert r.status_code == 401

    def test_register_company_endpoint(self, client):
        """POST /auth/register should create a new company."""
        r = client.post(
            "/auth/register",
            params={"discord_id": "new_discord", "discord_username": "NewUser"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["api_key"].startswith("dc_")
        assert data["discord_username"] == "NewUser"

    def test_update_company_name(self, client):
        """PUT /auth/name should update the display name."""
        _, api_key = _create_company()
        r = client.put(
            "/auth/name", params={"name": "My Corp"}, headers={"X-API-Key": api_key}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["company_name"] == "My Corp"


# ---------------------------------------------------------------------------
# Tests: /stash endpoints
# ---------------------------------------------------------------------------


class TestStashEndpoint:
    """Test the /stash GET endpoint."""

    def test_get_stash_default(self, client):
        """A fresh stash should return default (zero) values with ingot equivalents."""
        _, api_key = _create_company()
        r = client.get("/stash", headers={"X-API-Key": api_key})
        assert r.status_code == 200
        data = r.json()
        assert data["iron_blocks"] == 0
        assert data["iron_ingots"] == 0
        assert "total_ingots" in data

    def test_get_stash_with_values(self, client):
        """After saving some stash, /stash should reflect the values."""
        _, api_key = _create_company()
        company = db.get_company_by_api_key(api_key)
        db.save_stash(
            {
                "iron_blocks": 10,
                "iron_ingots": 5,
                "gold_blocks": 3,
                "gold_ingots": 2,
                "diamond_blocks": 1,
                "diamond_items": 7,
            },
            company_id=company["id"],
        )
        r = client.get("/stash", headers={"X-API-Key": api_key})
        assert r.status_code == 200
        data = r.json()
        assert data["iron_blocks"] == 10
        assert data["total_ingots"]["iron"] == 10 * 9 + 5

    def test_get_stash_raw(self, client):
        """The raw endpoint should not include computed fields."""
        _, api_key = _create_company()
        company = db.get_company_by_api_key(api_key)
        db.save_stash({"iron_blocks": 5}, company_id=company["id"])
        r = client.get("/stash/raw", headers={"X-API-Key": api_key})
        assert r.status_code == 200
        data = r.json()
        assert data["iron_blocks"] == 5
        assert "total_ingots" not in data

    def test_get_auto_subtract_default(self, client):
        """Auto-subtract should default to false."""
        _, api_key = _create_company()
        r = client.get("/stash/auto_subtract", headers={"X-API-Key": api_key})
        assert r.status_code == 200
        assert r.json()["auto_subtract"] is False

    def test_set_auto_subtract(self, client):
        """PUT /stash/auto_subtract should toggle the setting."""
        _, api_key = _create_company()
        db.set_auto_subtract(False)
        r = client.put(
            "/stash/auto_subtract",
            params={"enabled": True},
            headers={"X-API-Key": api_key},
        )
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

    def test_health_no_auth_required(self, client):
        """Health endpoint should not require auth."""
        r = client.get("/health", headers={})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Tests: /deals endpoints
# ---------------------------------------------------------------------------


class TestDealsEndpoint:
    """Test the /deals GET endpoints."""

    def test_deals_stats_empty(self, client):
        """With no deals, stats should return zeros."""
        _, api_key = _create_company()
        r = client.get("/deals/stats", headers={"X-API-Key": api_key})
        assert r.status_code == 200
        data = r.json()
        assert data["total_deals"] == 0

    def test_deals_list_empty(self, client):
        """With no deals, the deals list should be empty."""
        _, api_key = _create_company()
        r = client.get("/deals", headers={"X-API-Key": api_key})
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# Tests: /prices endpoint
# ---------------------------------------------------------------------------


class TestPricesEndpoint:
    """Test the /prices GET endpoint."""

    def test_prices_structure(self, client, monkeypatch):
        """The prices endpoint should return a prices dict with expected keys."""

        def _mock_fetch_live_prices(*args, **kwargs):
            return (5.0, 10.0, 20.0, {})

        monkeypatch.setattr("src.web.api.fetch_live_prices", _mock_fetch_live_prices)
        r = client.get("/prices")
        assert r.status_code == 200
        data = r.json()
        assert "prices" in data
        for key in ("Iron Ingot", "Gold Ingot", "Diamond"):
            assert key in data["prices"]
            assert isinstance(data["prices"][key], float)


# ---------------------------------------------------------------------------
# Tests: Stash save/clear via API
# ---------------------------------------------------------------------------


class TestStashMutations:
    """Test stash write operations via the API."""

    def test_save_stash_via_api(self, client):
        """PUT /stash should save stash."""
        _, api_key = _create_company()
        r = client.put(
            "/stash", json={"iron_blocks": 42}, headers={"X-API-Key": api_key}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["iron_blocks"] == 42

    def test_add_to_stash_via_api(self, client):
        """PUT /stash/add should add materials."""
        _, api_key = _create_company()
        r = client.put(
            "/stash/add",
            params={"iron_blocks": 10, "gold_ingots": 5},
            headers={"X-API-Key": api_key},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["iron_blocks"] == 10
        assert data["gold_ingots"] == 5

    def test_clear_stash_via_api(self, client):
        """POST /stash/clear should clear the stash."""
        _, api_key = _create_company()
        company = db.get_company_by_api_key(api_key)
        db.save_stash({"iron_blocks": 100}, company_id=company["id"])
        r = client.post("/stash/clear", headers={"X-API-Key": api_key})
        assert r.status_code == 200
        stash = db.load_stash(company_id=company["id"])
        assert stash["iron_blocks"] == 0
