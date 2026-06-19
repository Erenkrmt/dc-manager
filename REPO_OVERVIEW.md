# DC Trade Toolbox — Repository Overview

> **Generated:** 2026-06-19
> **Purpose:** Quick onboarding for new tasks / new machines. Read this instead of re-reading the full codebase each time.

---

## 1. What It Is

A **bulk trading calculator** for the [DemocracyCraft](https://democracycraft.net) Minecraft server. It:
- Fetches live item prices from the DemocracyCraft economy API
- Calculates market values, profits, and deal statuses for bulk trades (iron, gold, diamond)
- Manages an inventory stash (blocks/ingots/items)
- Logs deal history and price snapshots
- Provides both a **CLI** (terminal) and a **Web UI** (Streamlit + FastAPI)

---

## 2. Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10+ |
| CLI | Built-in `main.py` with console prompts |
| Web UI | **Streamlit** (`src/web/app.py`) |
| REST API | **FastAPI** (`src/web/api.py`) |
| Database | SQLite (dev) / PostgreSQL (prod) — raw SQL, no ORM at runtime |
| ORM / Migrations | SQLAlchemy models + **Alembic** |
| Config | Pydantic-style `Settings` class via env vars + `.env` |
| Container | Docker + docker-compose |
| CI/CD | Cloud Build (`cloudbuild.yaml`), Cloud Run (`Dockerfile.cloudrun`) |

---

## 3. Project Structure

```
dc-manager/
├── main.py                          # CLI entry point (delegates to src/main.py)
├── pyproject.toml                   # Project metadata, dependencies, CLI scripts
├── Dockerfile                       # Multi-stage Docker build
├── Dockerfile.cloudrun             # Cloud Run-specific build
├── docker-compose.yml              # Local dev + optional PostgreSQL
├── Makefile                        # Dev commands (install, dev, test, docker-*)
├── requirements.txt                # Legacy dependency list (used by Docker build)
├── alembic.ini                     # Alembic config
├── cloudbuild.yaml                 # GCP Cloud Build pipeline
├── DEPLOY_CLOUD_RUN.md            # Cloud Run deployment guide
├── .env.example                    # Template for env vars
├── data/                           # SQLite database lives here (gitignored)
├── scripts/
│   ├── run.py                      # Runs both Streamlit + API concurrently (for Docker)
│   └── run_cloudrun.py             # Cloud Run entry point
├── src/
│   ├── __init__.py
│   ├── main.py                     # Actual CLI entry point (same as root main.py)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── settings.py             # Environment config (Settings class)
│   │   ├── database.py             # All DB operations (SQLite/PostgreSQL dual backend)
│   │   ├── models.py               # SQLAlchemy ORM models (used by Alembic)
│   │   └── market_deal.py          # Core business logic (MarketDeal class)
│   ├── web/
│   │   ├── __init__.py
│   │   ├── api.py                  # FastAPI REST API
│   │   └── app.py                  # Streamlit web UI (all pages)
│   └── utils/
│       ├── __init__.py
│       └── console_ui.py           # Terminal UI (menu, prompts, formatting)
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py   # Initial DB schema migration
└── tests/
    ├── test_api.py                 # FastAPI endpoint tests
    └── test_database.py            # Database operation tests
```

---

## 4. Key Modules — Deep Dive

### 4.1 `src/core/settings.py`
- **Class `Settings`** — all config values from env vars (or `.env` file)
- Singleton via `@lru_cache` + `get_settings()` function
- Key groups:
  - Database: `DATABASE_URL` (empty = SQLite), `DB_DIR`, `DB_FILE`
  - API: `DC_API_KEY`, `API_BASE_URL`, timeout/retry values
  - Trading thresholds: `MIN_ACCEPTABLE_PERCENT` (default 85%)
  - Price cache: `CACHE_DURATION` (default 6h)
  - Minecraft units: `ITEMS_PER_STACK` (64), `ITEMS_PER_SHULKER` (1728), `INGOTS_PER_BLOCK` (9)
  - Fallback prices: hardcoded dict for Iron/Gold/Diamond
  - Item import mapping: maps item names to stash fields

### 4.2 `src/core/database.py`
- **Dual backend**: SQLite (no setup) or PostgreSQL (via `DATABASE_URL`)
- All DB operations use raw SQL with parameterized placeholders (`?` for SQLite, `%s` for PostgreSQL)
- Key functions:
  - `init_db()` — creates schema tables, runs column migrations for new fields
  - `log_deal()` / `update_deal()` / `delete_deal()` — CRUD for deals
  - `save_template()` / `load_templates()` / `delete_template()` — deal templates
  - `save_price_snapshot()` / `get_price_history()` — price tracking
  - `load_stash()` / `save_stash()` / `add_to_stash()` / `clear_stash()` — stash CRUD
  - `subtract_from_stash()` — intelligent subtraction (blocks first, then ingots)
  - `import_items_to_stash()` — parses game item dump and replaces stash
  - `get_auto_subtract()` / `set_auto_subtract()` — toggle auto-deduction
- Schema tables: `deals`, `price_cache`, `templates`, `price_history`, `item_lookup_deals`, `stash`

### 4.3 `src/core/market_deal.py`
- **Class `MarketDeal`** (all static methods)
- Key methods:
  - `get_price(item_name, cache)` — fetches live price from DC API with retry + fallback
  - `convert_to_ingots(amount, unit)` — block/nugget → ingot conversion
  - `format_bulk_storage(total_items)` — human-readable block/ingot formatting
  - `lookup_item(item_name, cache)` — arbitrary item lookup (not just iron/gold/diamond)
  - `log_deal()` — delegates to `db.log_deal()`
- API interaction: REST calls to `api.democracycraft.net/economy/api/v1/chestshop/items/{item}?days=N`
- Cache: in-memory dict loaded from/saved to `price_cache` table

### 4.4 `src/web/api.py` — FastAPI REST API
- Endpoints:
  - `GET /stash` — full stash with computed ingot equivalents
  - `GET /stash/raw` — raw stash from DB
  - `GET /stash/auto_subtract` — auto-subtract setting
  - `GET /stash/public` — shareable HTML page (pretty styled)
  - `GET /prices` — live prices (per ingot, per block, per stack of blocks)
  - `GET /deals` — recent deals (limit param)
  - `GET /deals/stats` — aggregate deal statistics
  - `GET /health` — health check

### 4.5 `src/web/app.py` — Streamlit UI
- **8 pages** (sidebar navigation):
  1. **Deal Calculator** — enter amounts/units, get deal analysis + logging UI
  2. **Shulker Scanner** — enter stacks + remainders for block/item counts
  3. **Quick Converter** — blocks ↔ stacks ↔ shulkers with value estimates
  4. **Deal History** — table, stats, profit chart, edit/delete deals
  5. **Stash Manager** — view/edit/add/clear/import stash, toggle auto-subtract
  6. **Deal Templates** — save/load/delete common deal configs
  7. **Item Lookup** — arbitrary item search + deal analysis + history
  8. **Price History** — snapshots + line chart + price changes
- Sidebar shows live prices, per-block/per-stack values, and stash summary
- Background thread starts the FastAPI server alongside Streamlit

### 4.6 `src/utils/console_ui.py` — Terminal UI
- Menu-driven CLI with 4 modes:
  1. Deal Calculator
  2. Shulker Box Scanner
  3. Quick Converter
  4. Stash Manager
- Shared calculation function `_calculate_and_show_result()` used by both Mode 1 and Mode 2
- Stash subtraction helper (auto or prompted)

---

## 5. Database Schema

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `deals` | Trade records | iron_ingots, gold_ingots, diamond_items, market_value, offered_price, status, profit, unit fields |
| `price_cache` | Cached API prices | item_name (PK), price, timestamp |
| `templates` | Saved deal templates | name (PK), iron_ingots, gold_ingots, diamond_items, offered_price |
| `price_history` | Price snapshots over time | id, timestamp, iron_price, gold_price, diamond_price |
| `item_lookup_deals` | Non-standard item deals | item_name, quantity, unit_price, total_value, offered_price, status, profit |
| `stash` | Single-row inventory (id=1 enforced) | iron_blocks, iron_ingots, gold_blocks, gold_ingots, diamond_blocks, diamond_items, raw_iron_blocks, raw_gold_blocks, auto_subtract, updated_at |

---

## 6. CLI Entry Points (from pyproject.toml)

| Command | Script | What it runs |
|---------|--------|--------------|
| `dc-trade` | `src.main:main` | CLI terminal UI |
| `dc-trade-web` | `src.web.app:main` | Streamlit web UI |
| `dc-trade-api` | `src.web.api:run` | FastAPI server |

---

## 7. Running Locally

```bash
# 1. Install
pip install uv && uv sync

# 2. Set API key
cp .env.example .env
# Edit .env → DC_API_KEY=your_key

# 3a. CLI
python main.py

# 3b. Web UI
streamlit run src/web/app.py

# 3c. REST API
uvicorn src.web.api:app --reload --port 8000
```

---

## 8. Docker

```bash
# Build & start (SQLite)
docker compose up -d

# With PostgreSQL
docker compose --profile db up -d
```

---

## 9. Makefile Commands

| Command | Description |
|---------|-------------|
| `make install` | Install deps with uv |
| `make dev` | Run both Streamlit + API |
| `make streamlit` | Streamlit only |
| `make api` | FastAPI only |
| `make docker-build` | Build Docker image |
| `make docker-up` | Start Docker services |
| `make test` | Run pytest |
| `make clean` | Clean cache files |

---

## 10. Tests

- **`tests/test_database.py`** — Tests stash CRUD (add, clear, load/save, auto-subtract, negative values, large numbers)
- **`tests/test_api.py`** — Tests FastAPI endpoints (stash, health, deals, prices)
- Both use a temp SQLite database fixture for isolation
- Run: `make test` or `python -m pytest tests/ -v`

---

## 11. Deployment

- **Cloud Run** via `Dockerfile.cloudrun` + `scripts/run_cloudrun.py`
- **Cloud Build** pipeline defined in `cloudbuild.yaml`
- See `DEPLOY_CLOUD_RUN.md` for detailed instructions
- For production: set `DATABASE_URL` to PostgreSQL, run `alembic upgrade head`

---

## 12. Common Gotchas / Notes

1. **DC_API_KEY is required** — get it from https://api.democracycraft.net. Without it, the CLI/API will exit with an error.
2. **Database auto-creates** on first run (`data/dc_trade.db` for SQLite).
3. **Price caching** — prices are cached for 6h (configurable) in the DB to avoid excessive API calls.
4. **Stash is single-row** — there's only one stash with id=1. `CHECK(id=1)` constraint enforces this.
5. **Raw blocks** (raw iron/gold) are tracked separately in the stash and treated as having the same value as refined blocks.
6. **Auto-subtract** — when enabled, materials are automatically deducted from stash after every deal without asking.
7. **Alembic migrations** are used for production DB schema management, but the app also auto-creates/migrates tables on startup via `init_db()`.
8. **Streamlit background thread** — the Streamlit app starts a FastAPI server in a daemon thread on launch.