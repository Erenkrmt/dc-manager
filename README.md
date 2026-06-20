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

### Option 3: Dockge (home server deployment)

If you run [Dockge](https://github.com/louislam/dockge) on your home server:

1. In Dockge, click **Create Stack**
2. Paste the contents of `docker-compose.yml` into the compose editor
3. Click **Environment** → add your variables (see below)
4. Click **Deploy**

The app will be pulled from the pre-built image at `ghcr.io/erenkrmt/dc-trade:latest`.

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

## 🐳 Docker Deployment Guide

This project uses a **pre-built image** hosted on GitHub Container Registry (`ghcr.io/erenkrmt/dc-trade`). Every push to `master` triggers a GitHub Action that builds and pushes a new image automatically.

### Local Docker (development)

```bash
# Build locally from source
docker compose build

# Start with SQLite (default – no setup needed)
docker compose up -d

# Start with PostgreSQL (production-like)
docker compose --profile db up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

### Auto-build with GitHub Actions

The CI workflow (`.github/workflows/docker-publish.yml`) runs on every push to `master`:

1. Logs into GitHub Container Registry using the automatic `GITHUB_TOKEN`
2. Builds the Docker image
3. Pushes two tags:
   - `ghcr.io/erenkrmt/dc-trade:latest`
   - `ghcr.io/erenkrmt/dc-trade:<commit-sha>`

No secrets to configure — the `GITHUB_TOKEN` is provided automatically by GitHub.

### Deploy on Dockge (home server)

[Dockge](https://github.com/louislam/dockge) is a Docker Compose manager with a web UI. To deploy:

**1. Copy the environment template**

Open `.env.example` from this repo — it lists all available variables. Create your own list with real values:

```
DC_API_KEY=your_actual_api_key
COMPANY_NAME=Fishy Business
```

You only need `DC_API_KEY` to get started. The rest are optional (see table below).

**2. Create a stack in Dockge**

In the Dockge web UI:
- Click **Create Stack**
- Paste the contents of `docker-compose.yml` into the compose editor
- Click **Environment** tab → paste your env vars
- Set the stack name (e.g., `dc-trade`)
- Click **Deploy**

Dockge will pull `ghcr.io/erenkrmt/dc-trade:latest` and start the container.

**3. Access the services**

| Service  | Port | URL                     |
|----------|------|-------------------------|
| Web UI   | 8501 | `http://your-server:8501` |
| REST API | 8000 | `http://your-server:8000` |
| API Docs | 8000 | `http://your-server:8000/docs` |

**4. Update to a new version**

Push to `master` → GitHub Action builds a new image → In Dockge click **Update** on the stack → Done.

### Using PostgreSQL in production

To switch from SQLite to PostgreSQL:

1. Uncomment/Set these environment variables in Dockge:
   ```
   DATABASE_URL=postgres://dctrade:YOUR_PASSWORD_HERE@postgres:5432/dctrade
   POSTGRES_PASSWORD=YOUR_PASSWORD_HERE
   POSTGRES_USER=dctrade
   POSTGRES_DB=dctrade
   ```
2. In the compose editor, add `--profile db` to the stack, OR enable the profile in Dockge by adding the `db` profile to the `app` service's `profiles` list.

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