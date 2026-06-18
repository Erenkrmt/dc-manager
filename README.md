# ⛏️ DC Trade Toolbox

Bulk trading calculator for DemocracyCraft Minecraft server.  
Calculates market values, analyzes deals, manages inventory stash, and tracks price history.

## 🚀 Quick Start

### Option 1: Local (Python)

```bash
# Install
pip install uv && uv sync

# Set your API key (get from https://api.democracycraft.net)
cp .env.example .env
# Edit .env and set DC_API_KEY=your_key

# Start web UI
streamlit run src/web/app.py
# → http://localhost:8501

# Or start REST API
uvicorn src.web.api:app --reload --port 8000
# → http://localhost:8000/docs
```

### Option 2: Docker (recommended for deployment)

```bash
# Build & start
docker compose up -d

# Or with PostgreSQL for production
docker compose --profile db up -d

# → Web UI: http://localhost:8501
# → REST API: http://localhost:8000
```

## 📋 Features

- **💰 Deal Calculator** – Enter material amounts and get instant deal analysis
- **📦 Shulker Scanner** – Convert full stacks directly to deal value
- **⚡ Quick Converter** – Convert between blocks, stacks, and shulkers
- **📊 Deal History** – View all deals with profit chart, edit/delete entries
- **📦 Stash Manager** – Save your inventory, auto-subtract after deals
- **📋 Deal Templates** – Save and load common deal configurations
- **📈 Price History** – Track price changes over time with snapshots
- **🌐 REST API** – Programmatic access to stash and deal data

## 🛠️ Development

```bash
# Show all available commands
make help

# Start both Streamlit + API
make dev

# Run tests
make test

# Docker
make docker-build
make docker-up
```

## 🐳 Deployment

### Production with Docker

```bash
# Build and start
docker compose --profile db up -d --build

# Set your API key in docker-compose.yml or .env
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DC_API_KEY` | `""` | **Required.** DemocracyCraft API key |
| `COMPANY_NAME` | `Fishy Business` | Branding in UI |
| `DATABASE_URL` | *(SQLite)* | PostgreSQL connection string for production |
| `API_TIMEOUT` | `10` | Seconds before API timeout |
| `API_RETRIES` | `3` | Number of API retries |
| `MIN_ACCEPTABLE_PERCENT` | `0.85` | Minimum deal threshold (85%) |
| `CACHE_DURATION` | `21600` | Price cache TTL in seconds (6h) |
| `DEBUG` | `false` | Enable debug mode |

## 🗄️ Database

- **Default:** SQLite (`data/dc_trade.db`) – no setup required
- **Production:** PostgreSQL via `DATABASE_URL` env var
- **Migrations:** Alembic (`alembic upgrade head`)

## 📁 Project Structure

```
dc_trade_api/
├── src/
│   ├── core/          # Business logic (market_deal, database, settings)
│   ├── web/           # Web interface (Streamlit app, FastAPI routes)
│   └── utils/         # Console UI helpers
├── scripts/           # Production entry points
├── tests/             # Test suite
├── alembic/           # Database migrations
├── Dockerfile
├── docker-compose.yml
└── Makefile