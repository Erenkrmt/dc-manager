"""
FastAPI server for the DC Trade Toolbox – REST API endpoints.
Provides programmatic access to stash data and other features.
"""

import sys
import os
import logging
from contextlib import asynccontextmanager

# Ensure the project root is on sys.path so src.* imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from src.core import database as db
from src.core import constants

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app):
    """Initialize the database on server start and clean up on shutdown."""
    db.init_db()
    logger.info("API server started – database initialized.")
    yield


app = FastAPI(
    title=f"{constants.COMPANY_NAME} Toolbox API",
    description=f"REST API for the {constants.COMPANY_NAME} Trading Toolbox",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Stash endpoints
# ---------------------------------------------------------------------------

@app.get("/stash")
def get_stash() -> dict:
    """Return the current stash as JSON."""
    stash = db.load_stash()
    # Calculate ingot equivalents for convenience (including raw blocks)
    stash["total_ingots"] = {
        "iron": (stash.get("iron_blocks", 0) + stash.get("raw_iron_blocks", 0)) * constants.INGOTS_PER_BLOCK + stash.get("iron_ingots", 0),
        "gold": (stash.get("gold_blocks", 0) + stash.get("raw_gold_blocks", 0)) * constants.INGOTS_PER_BLOCK + stash.get("gold_ingots", 0),
        "diamond": stash.get("diamond_blocks", 0) * constants.INGOTS_PER_BLOCK + stash.get("diamond_items", 0),
    }
    # Also include raw_* counts for convenience
    stash.setdefault("raw_iron_blocks", 0)
    stash.setdefault("raw_gold_blocks", 0)
    return stash


@app.get("/stash/raw")
def get_stash_raw() -> dict:
    """Return the stash exactly as stored in the database (no computed fields)."""
    return db.load_stash()


@app.get("/stash/auto_subtract")
def get_auto_subtract() -> dict:
    """Return whether auto-subtract is enabled."""
    return {"auto_subtract": db.get_auto_subtract()}


# ---------------------------------------------------------------------------
# Prices endpoint
# ---------------------------------------------------------------------------

@app.get("/prices")
def get_prices() -> dict:
    """Return live prices from a fresh cache load."""
    from src.core.market_deal import MarketDeal

    cache = MarketDeal.load_cache()
    p_iron = MarketDeal.get_price("Iron Ingot", cache)
    p_gold = MarketDeal.get_price("Gold Ingot", cache)
    p_diamond = MarketDeal.get_price("Diamond", cache)
    MarketDeal.save_cache(cache)
    return {
        "prices": {
            "Iron Ingot": p_iron,
            "Gold Ingot": p_gold,
            "Diamond": p_diamond,
        },
        "per_block": {
            "Iron Block": p_iron * constants.INGOTS_PER_BLOCK,
            "Gold Block": p_gold * constants.INGOTS_PER_BLOCK,
            "Diamond Block": p_diamond * constants.INGOTS_PER_BLOCK,
        },
        "per_stack_of_blocks": {
            "Iron Block": p_iron * constants.INGOTS_PER_BLOCK * constants.ITEMS_PER_STACK,
            "Gold Block": p_gold * constants.INGOTS_PER_BLOCK * constants.ITEMS_PER_STACK,
            "Diamond Block": p_diamond * constants.INGOTS_PER_BLOCK * constants.ITEMS_PER_STACK,
        },
    }


# ---------------------------------------------------------------------------
# Deals endpoints
# ---------------------------------------------------------------------------

@app.get("/deals")
def get_deals(limit: int = 100) -> list:
    """Return recent deals."""
    return db.get_all_deals(limit=limit)


@app.get("/deals/stats")
def get_deal_stats() -> dict:
    """Return aggregate deal statistics."""
    return db.get_deal_stats()


# ---------------------------------------------------------------------------
# Public stash page (HTML – shareable with customers)
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


@app.get("/stash/public", response_class=HTMLResponse)
def get_stash_public() -> str:
    """Return a public, read-only HTML page showing the stash (shareable with customers)."""
    from src.core.market_deal import MarketDeal

    stash = db.load_stash()

    # Ingot totals (including raw blocks treated as same value)
    total_iron = (stash.get("iron_blocks", 0) + stash.get("raw_iron_blocks", 0)) * constants.INGOTS_PER_BLOCK + stash.get("iron_ingots", 0)
    total_gold = (stash.get("gold_blocks", 0) + stash.get("raw_gold_blocks", 0)) * constants.INGOTS_PER_BLOCK + stash.get("gold_ingots", 0)
    total_diamond = stash.get("diamond_blocks", 0) * constants.INGOTS_PER_BLOCK + stash.get("diamond_items", 0)

    # Prices
    cache = MarketDeal.load_cache()
    p_iron = MarketDeal.get_price("Iron Ingot", cache)
    p_gold = MarketDeal.get_price("Gold Ingot", cache)
    p_diamond = MarketDeal.get_price("Diamond", cache)
    MarketDeal.save_cache(cache)

    iron_value = total_iron * p_iron
    gold_value = total_gold * p_gold
    diamond_value = total_diamond * p_diamond
    total_value = iron_value + gold_value + diamond_value

    updated_at = stash.get("updated_at", "never")
    stash_url = str(app.url_path_for("get_stash_raw"))
    company_name = constants.COMPANY_NAME

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
        stash_url=stash_url,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check() -> dict:
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "database": constants.DB_FILE,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run() -> None:
    """Run the API server with uvicorn."""
    import uvicorn
    uvicorn.run("src.web.api:app", host="0.0.0.0", port=8000, reload=True)
