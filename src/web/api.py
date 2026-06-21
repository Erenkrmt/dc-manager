"""
FastAPI server for the DC Trade Toolbox – REST API endpoints.
Provides programmatic access to stash data and other features.
Multi-company: scoped by API key authentication.
"""

import sys
import os
import logging
from contextlib import asynccontextmanager

# Ensure the project root is on sys.path so src.* imports resolve
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from typing import Annotated
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from src.core import database as db
from src.core.settings import get_settings

_settings = get_settings()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app):
    """Initialize the database on server start and clean up on shutdown."""
    db.init_db()
    logger.info("API server started – database initialized.")
    yield


app = FastAPI(
    title=f"{_settings.COMPANY_NAME} Toolbox API",
    description=f"REST API for the {_settings.COMPANY_NAME} Trading Toolbox",
    version="2.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Auth middleware — extract company_id from X-API-Key header
# ---------------------------------------------------------------------------


def get_api_key(request: Request) -> str:
    """Extract API key from request headers."""
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    return api_key


def _resolve_company(api_key: str) -> dict:
    """Look up company by API key. Raises on invalid/inactive."""
    company = db.get_company_by_api_key(api_key)
    if not company:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return company


def _check_write_access(company: dict) -> None:
    """Check if company has write access. Raises 403 if read-only."""
    is_active, is_read_only = db.check_company_access(company["id"])
    if not is_active:
        raise HTTPException(status_code=403, detail="Company account is inactive")
    if is_read_only:
        raise HTTPException(
            status_code=403, detail="Access expired. Contact Fishy Business to renew."
        )


def _get_company_id(request: Request) -> int:
    """Return company_id from the authenticated request."""
    api_key = get_api_key(request)
    company = _resolve_company(api_key)
    return company["id"]


def _require_admin(api_key: str) -> dict:
    """Validate that the API key belongs to an admin Discord ID."""
    company = _resolve_company(api_key)
    discord_id = str(company.get("discord_id", ""))
    if discord_id not in _settings.ADMIN_DISCORD_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return company


AuthDep = Annotated[str, Depends(get_api_key)]


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth & Company management endpoints
# ---------------------------------------------------------------------------


@app.get("/auth/me", responses={401: {"description": "Missing or invalid API key"}})
def auth_me(api_key: AuthDep) -> dict:
    """Return the current company info based on API key."""
    company = _resolve_company(api_key)
    is_active, is_read_only = db.check_company_access(company["id"])
    return {
        "id": company["id"],
        "company_name": company.get("company_name", ""),
        "discord_username": company.get("discord_username", ""),
        "is_active": is_active,
        "is_read_only": is_read_only,
        "access_expires_at": company.get("access_expires_at"),
    }


@app.post("/auth/register")
def register_company(
    discord_id: str,
    discord_username: str,
    discord_avatar: str = "",
) -> dict:
    """Register a new company via Discord OAuth data. Returns company info."""
    company, member = db.get_or_create_company_by_discord(
        discord_id, discord_username, discord_avatar
    )
    return {
        "id": company["id"],
        "company_name": company.get("company_name", ""),
        "api_key": company["api_key"],  # shown only once
        "discord_username": member.get("discord_username", discord_username),
        "access_expires_at": company.get("access_expires_at"),
    }


@app.put("/auth/name", responses={401: {"description": "Missing or invalid API key"}})
def update_company_name(name: str, api_key: AuthDep) -> dict:
    """Update the current company's display name."""
    company = _resolve_company(api_key)
    db.update_company_name(company["id"], name)
    return {"status": "ok", "company_name": name}


# ---------------------------------------------------------------------------
# Admin endpoints (for authorized Discord admins)
# ---------------------------------------------------------------------------


@app.get(
    "/admin/companies",
    responses={
        401: {"description": "Missing or invalid API key"},
        403: {"description": "Admin access required"},
    },
)
def admin_list_companies(api_key: AuthDep) -> list:
    """List all companies (admin only). Authenticated admin Discord IDs only."""
    _require_admin(api_key)
    return db.list_all_companies()


@app.post(
    "/admin/companies/{company_id}/extend",
    responses={
        401: {"description": "Missing or invalid API key"},
        403: {"description": "Admin access required"},
        500: {"description": "Failed to extend access"},
    },
)
def admin_extend_access(company_id: int, days: int, api_key: AuthDep) -> dict:
    """Extend a company's access by N days. Admin only."""
    _require_admin(api_key)
    if db.update_company_access(company_id, days):
        return {"status": "ok", "message": f"Access extended by {days} days"}
    raise HTTPException(status_code=500, detail="Failed to extend access")


@app.post(
    "/admin/companies/{company_id}/deactivate",
    responses={
        401: {"description": "Missing or invalid API key"},
        403: {"description": "Admin access required"},
        500: {"description": "Failed to deactivate company"},
    },
)
def admin_deactivate_company(company_id: int, api_key: AuthDep) -> dict:
    """Deactivate a company. Admin only."""
    _require_admin(api_key)
    if db.deactivate_company(company_id):
        return {"status": "ok", "message": "Company deactivated"}
    raise HTTPException(status_code=500, detail="Failed to deactivate company")


# ---------------------------------------------------------------------------
# Stash endpoints (scoped by API key)
# ---------------------------------------------------------------------------


@app.get("/stash", responses={401: {"description": "Missing or invalid API key"}})
def get_stash(api_key: AuthDep) -> dict:
    """Return the current stash as JSON for the authenticated company."""
    company = _resolve_company(api_key)
    stash = db.load_stash(company_id=company["id"])
    stash["total_ingots"] = {
        "iron": (stash.get("iron_blocks", 0) + stash.get("raw_iron_blocks", 0))
        * _settings.INGOTS_PER_BLOCK
        + stash.get("iron_ingots", 0),
        "gold": (stash.get("gold_blocks", 0) + stash.get("raw_gold_blocks", 0))
        * _settings.INGOTS_PER_BLOCK
        + stash.get("gold_ingots", 0),
        "diamond": stash.get("diamond_blocks", 0) * _settings.INGOTS_PER_BLOCK
        + stash.get("diamond_items", 0),
    }
    stash.setdefault("raw_iron_blocks", 0)
    stash.setdefault("raw_gold_blocks", 0)
    return stash


@app.get("/stash/raw", responses={401: {"description": "Missing or invalid API key"}})
def get_stash_raw(api_key: AuthDep) -> dict:
    """Return the stash exactly as stored in the database."""
    company = _resolve_company(api_key)
    return db.load_stash(company_id=company["id"])


@app.get(
    "/stash/auto_subtract",
    responses={401: {"description": "Missing or invalid API key"}},
)
def get_auto_subtract(api_key: AuthDep) -> dict:
    """Return whether auto-subtract is enabled."""
    company = _resolve_company(api_key)
    return {"auto_subtract": db.get_auto_subtract(company_id=company["id"])}


@app.put(
    "/stash/auto_subtract",
    responses={
        401: {"description": "Missing or invalid API key"},
        403: {"description": "Read-only or inactive"},
    },
)
def set_auto_subtract(enabled: bool, api_key: AuthDep) -> dict:
    """Enable or disable auto-subtract."""
    company = _resolve_company(api_key)
    _check_write_access(company)
    db.set_auto_subtract(enabled, company_id=company["id"])
    return {"auto_subtract": enabled}


@app.put(
    "/stash",
    responses={
        401: {"description": "Missing or invalid API key"},
        403: {"description": "Read-only or inactive"},
    },
)
def save_stash(data: dict, api_key: AuthDep) -> dict:
    """Save the stash for the authenticated company."""
    company = _resolve_company(api_key)
    _check_write_access(company)
    db.save_stash(data, company_id=company["id"])
    return db.load_stash(company_id=company["id"])


@app.put(
    "/stash/add",
    responses={
        401: {"description": "Missing or invalid API key"},
        403: {"description": "Read-only or inactive"},
    },
)
def add_to_stash(
    api_key: AuthDep,
    iron_blocks: int = 0,
    iron_ingots: int = 0,
    gold_blocks: int = 0,
    gold_ingots: int = 0,
    diamond_blocks: int = 0,
    diamond_items: int = 0,
) -> dict:
    """Add materials to the stash."""
    company = _resolve_company(api_key)
    _check_write_access(company)
    return db.add_to_stash(
        iron_blocks,
        iron_ingots,
        gold_blocks,
        gold_ingots,
        diamond_blocks,
        diamond_items,
        company_id=company["id"],
    )


@app.post(
    "/stash/clear",
    responses={
        401: {"description": "Missing or invalid API key"},
        403: {"description": "Read-only or inactive"},
    },
)
def clear_stash(api_key: AuthDep) -> dict:
    """Clear the stash."""
    company = _resolve_company(api_key)
    _check_write_access(company)
    db.clear_stash(company_id=company["id"])
    return {"status": "ok", "message": "Stash cleared"}


# ---------------------------------------------------------------------------
# Prices endpoint (shared)
# ---------------------------------------------------------------------------


@app.get("/prices")
def get_prices() -> dict:
    """Return live prices from a fresh cache load."""
    from src.core.market_deal import fetch_live_prices

    p_iron, p_gold, p_diamond, _ = fetch_live_prices()
    return {
        "prices": {
            "Iron Ingot": p_iron,
            "Gold Ingot": p_gold,
            "Diamond": p_diamond,
        },
        "per_block": {
            "Iron Block": p_iron * _settings.INGOTS_PER_BLOCK,
            "Gold Block": p_gold * _settings.INGOTS_PER_BLOCK,
            "Diamond Block": p_diamond * _settings.INGOTS_PER_BLOCK,
        },
        "per_stack_of_blocks": {
            "Iron Block": p_iron
            * _settings.INGOTS_PER_BLOCK
            * _settings.ITEMS_PER_STACK,
            "Gold Block": p_gold
            * _settings.INGOTS_PER_BLOCK
            * _settings.ITEMS_PER_STACK,
            "Diamond Block": p_diamond
            * _settings.INGOTS_PER_BLOCK
            * _settings.ITEMS_PER_STACK,
        },
    }


# ---------------------------------------------------------------------------
# Deals endpoints (scoped)
# ---------------------------------------------------------------------------


@app.get("/deals", responses={401: {"description": "Missing or invalid API key"}})
def get_deals(api_key: AuthDep, limit: int = 100) -> list:
    """Return recent deals for the authenticated company."""
    company = _resolve_company(api_key)
    return db.get_all_deals(limit=limit, company_id=company["id"])


@app.get("/deals/stats", responses={401: {"description": "Missing or invalid API key"}})
def get_deal_stats(api_key: AuthDep) -> dict:
    """Return aggregate deal statistics."""
    company = _resolve_company(api_key)
    return db.get_deal_stats(company_id=company["id"])


# ---------------------------------------------------------------------------
# Public stash page (HTML – shareable with customers, no auth)
# ---------------------------------------------------------------------------

_STASH_PUBLIC_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{company_name} – Live Stash</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a; color: #e2e8f0;
            display: flex; justify-content: center; align-items: center;
            min-height: 100vh; padding: 1rem;
        }}
        .card {{
            background: #1e293b; border-radius: 1rem; padding: 2rem;
            max-width: 600px; width: 100%;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
        }}
        h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
        .subtitle {{ color: #94a3b8; font-size: 0.875rem; margin-bottom: 1.5rem; }}
        .material {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 1rem; border-radius: 0.75rem; margin-bottom: 0.75rem;
        }}
        .material.iron {{ background: #334155; }}
        .material.gold {{ background: #422006; }}
        .material.diamond {{ background: #1e3a5f; }}
        .material-name {{ font-size: 1.125rem; font-weight: 600; }}
        .material-amount {{ text-align: right; }}
        .material-amount .blocks {{ font-size: 1.25rem; font-weight: 700; }}
        .material-amount .ingots {{ font-size: 0.875rem; color: #94a3b8; }}
        .material-amount .value {{ font-size: 0.875rem; color: #22c55e; }}
        .totals {{
            margin-top: 1rem; padding: 1rem; background: #0f172a;
            border-radius: 0.75rem; text-align: center;
        }}
        .totals .total-value {{ font-size: 1.5rem; font-weight: 700; color: #22c55e; }}
        .totals .label {{ font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
        .footer {{ margin-top: 1rem; text-align: center; font-size: 0.75rem; color: #64748b; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>⛏️ {company_name} – Live Stash</h1>
        <div class="subtitle">Updated: {updated_at}</div>

        <div class="material iron">
            <span class="material-name">⬜ Iron</span>
            <div class="material-amount">
                <div class="blocks">{iron_blocks} blocks + {iron_ingots} ingots</div>
                <div class="value">${iron_value:,.2f}</div>
            </div>
        </div>

        <div class="material gold">
            <span class="material-name">🟨 Gold</span>
            <div class="material-amount">
                <div class="blocks">{gold_blocks} blocks + {gold_ingots} ingots</div>
                <div class="value">${gold_value:,.2f}</div>
            </div>
        </div>

        <div class="material diamond">
            <span class="material-name">💎 Diamond</span>
            <div class="material-amount">
                <div class="blocks">{diamond_blocks} blocks + {diamond_items} items</div>
                <div class="value">${diamond_value:,.2f}</div>
            </div>
        </div>

        <div class="totals">
            <div class="label">Total Market Value</div>
            <div class="total-value">${total_value:,.2f}</div>
        </div>

        <div class="footer">
            Data refreshes every 30 seconds · <a href="{stash_url}" style="color:#64748b;">View JSON</a>
        </div>
    </div>
    <script>
        setTimeout(function() {{ location.reload(); }}, 30000);
    </script>
</body>
</html>
"""


def _render_public_stash_page(company: dict) -> str:
    """Render the public stash HTML page for a given company."""
    from src.core.market_deal import fetch_live_prices, stash_ingot_equivalents

    stash = db.load_stash(company_id=company["id"])
    total_iron, total_gold, total_diamond = stash_ingot_equivalents(stash)
    p_iron, p_gold, p_diamond, _ = fetch_live_prices()

    iron_value = total_iron * p_iron
    gold_value = total_gold * p_gold
    diamond_value = total_diamond * p_diamond
    total_value = iron_value + gold_value + diamond_value

    updated_at = stash.get("updated_at", "never")
    company_name = company.get("company_name", _settings.COMPANY_NAME)

    return _STASH_PUBLIC_HTML.format(
        company_name=company_name,
        updated_at=updated_at,
        iron_blocks=stash["iron_blocks"],
        iron_ingots=stash["iron_ingots"],
        gold_blocks=stash["gold_blocks"],
        gold_ingots=stash["gold_ingots"],
        diamond_blocks=stash["diamond_blocks"],
        diamond_items=stash["diamond_items"],
        iron_value=iron_value,
        gold_value=gold_value,
        diamond_value=diamond_value,
        total_value=total_value,
        stash_url="",  # no JSON link for public view
    )


@app.get(
    "/stash/public",
    response_class=HTMLResponse,
    responses={401: {"description": "Missing or invalid API key"}},
)
def get_stash_public(api_key: AuthDep) -> str:
    """Return a public, read-only HTML page showing the stash (authenticated)."""
    company = _resolve_company(api_key)
    return _render_public_stash_page(company)


@app.get(
    "/stash/public/static/{rest:path}",
    include_in_schema=False,
)
def stash_public_static_files(rest: str) -> dict:
    """
    Catch requests to /stash/public/static/... paths.
    These are likely stale service worker cache requests (from Streamlit or browser
    extensions) that get routed here because /stash/public/{token} catches them.
    Return a proper 404 so the browser doesn't error on MIME type mismatch.
    """
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("Not Found", status_code=404)


@app.get(
    "/stash/public/{token}",
    response_class=HTMLResponse,
    responses={404: {"description": "Invalid or inactive public stash token"}},
)
def get_stash_public_by_token(token: str) -> str:
    """
    Return a public, read-only HTML page showing a company's stash via public token.
    No API key required — share this URL with customers.
    """
    # Reject tokens with slashes — they're subpath requests (e.g. static files)
    if "/" in token:
        raise HTTPException(
            status_code=404, detail="Invalid public stash token"
        )
    company = db.get_company_by_public_token(token)
    if not company:
        raise HTTPException(
            status_code=404, detail="Invalid or inactive public stash token"
        )
    return _render_public_stash_page(company)


# ---------------------------------------------------------------------------
# Public stash token management (authenticated)
# ---------------------------------------------------------------------------


@app.get(
    "/stash/public_token",
    responses={401: {"description": "Missing or invalid API key"}},
)
def get_public_token(api_key: AuthDep) -> dict:
    """Return the current company's public stash token (or empty if not set)."""
    company = _resolve_company(api_key)
    token = company.get("public_stash_token", "")
    return {"public_stash_token": token}


@app.post(
    "/stash/public_token/generate",
    responses={
        401: {"description": "Missing or invalid API key"},
        403: {"description": "Read-only or inactive"},
        500: {"description": "Failed to generate token"},
    },
)
def generate_public_token(api_key: AuthDep) -> dict:
    """Generate a new public stash token for the authenticated company."""
    company = _resolve_company(api_key)
    _check_write_access(company)
    token = db.generate_public_stash_token(company["id"])
    if not token:
        raise HTTPException(status_code=500, detail="Failed to generate token")
    return {"public_stash_token": token}


# ---------------------------------------------------------------------------
# Health check (no auth)
# ---------------------------------------------------------------------------


@app.get("/health")
def health_check() -> dict:
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "database": "connected",
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def run() -> None:
    """Run the API server with uvicorn."""
    import uvicorn

    host = os.environ.get("API_HOST", "127.0.0.1")
    uvicorn.run("src.web.api:app", host=host, port=8000, reload=True)
