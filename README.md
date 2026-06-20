# ⛏️ DC Trade Toolbox

Bulk trading calculator for the DemocracyCraft Minecraft server. Calculates market values, analyzes deals, manages inventory stash, and tracks price history.

[![Docker](https://img.shields.io/badge/image-ghcr.io%2Ferenkrmt%2Fdc--trade-blue)](https://github.com/users/erenkrmt/packages/container/package/dc-trade)

---

## 📋 Features

- **💰 Deal Calculator** – Enter material amounts and get instant deal analysis
- **📦 Shulker Scanner** – Convert full stacks directly to deal value
- **⚡ Quick Converter** – Convert between blocks, stacks, and shulkers
- **📊 Deal History** – View all deals with profit chart, edit/delete entries
- **📦 Stash Manager** – Save your inventory, auto-subtract after deals
- **📋 Deal Templates** – Save and load common deal configurations
- **📈 Price History** – Track price changes over time with snapshots
- **🌐 REST API** – Programmatic access to stash and deal data
- **🔐 Multi-Company** – Discord OAuth login, per-company scoping

---

## 🚀 Getting Started

### 1. Docker (recommended)

Pull and run the pre-built image from GitHub Container Registry:

```bash
# Quick start with SQLite (no database setup needed)
docker run -d --name dc-trade \
  -p 8501:8501 -p 8000:8000 \
  -e DC_API_KEY="your_api_key_here" \
  -v dc_trade_data:/app/data \
  ghcr.io/erenkrmt/dc-trade:latest

# Web UI:  http://localhost:8501
# API:     http://localhost:8000
# API doc: http://localhost:8000/docs
```

Or with docker-compose (recommended for production):

```bash
# Start with SQLite
docker compose up -d

# Start with PostgreSQL
docker compose --profile db up -d
```

The image auto-builds on every push to `master` — just pull the latest tag to update.

### 2. Local (Python)

```bash
# Install dependencies
pip install uv && uv sync

# Set up config
cp .env.example .env
# Edit .env and set DC_API_KEY=your_key

# Start web UI
streamlit run src/web/app.py

# Or start REST API
uvicorn src.web.api:app --reload --port 8000
```

### 3. From Source (development)

```bash
make dev       # Start both Streamlit + API
make test      # Run tests
make help      # Show all commands
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DC_API_KEY` | `""` | **Yes** | DemocracyCraft API key |
| `DATABASE_URL` | *(SQLite)* | No | PostgreSQL connection string (leave empty for SQLite) |
| `DATABASE_SSLMODE` | *(auto)* | No | PostgreSQL SSL mode: `disable`, `require`, `verify-full` etc. Auto-detected for local vs remote hosts |
| `POSTGRES_PASSWORD` | `""` | No | Password for the PostgreSQL container (`--profile db`) |
| `COMPANY_NAME` | `Fishy Business` | No | Branding in the web UI |
| `STREAMLIT_PORT` | `8501` | No | Web UI port |
| `API_PORT` | `8000` | No | REST API port |
| `API_TIMEOUT` | `10` | No | HTTP request timeout (seconds) |
| `API_RETRIES` | `3` | No | Number of API retries |
| `MIN_ACCEPTABLE_PERCENT` | `0.85` | No | Minimum deal threshold |
| `CACHE_DURATION` | `21600` | No | Price cache TTL (seconds, 6h) |
| `SSL_ENABLED` | `false` | No | Enable HTTPS for both servers |
| `SSL_CERTFILE` | `""` | No* | Path to SSL certificate file (`/app/certs/fullchain.pem`) |
| `SSL_KEYFILE` | `""` | No* | Path to SSL private key (`/app/certs/privkey.pem`) |
| `DISCORD_CLIENT_ID` | `""` | No | Discord OAuth 2.0 client ID |
| `DISCORD_CLIENT_SECRET` | `""` | No | Discord OAuth 2.0 client secret |
| `DISCORD_REDIRECT_URI` | `http://localhost:8501/` | No | Discord OAuth redirect URL |
| `ADMIN_DISCORD_IDS` | `""` | No | Comma-separated Discord user IDs with admin access |
| `TRIAL_DAYS` | `3` | No | Free trial duration for new companies |
| `SESSION_SECRET` | *(auto)* | No | Session cookie signing key |
| `DEBUG` | `false` | No | Enable debug logging |

*\* Required when `SSL_ENABLED=true`.*

### Database

The app supports two database backends:

- **SQLite** (default) — No setup required. Database file is stored at `data/dc_trade.db`.
- **PostgreSQL** (production) — Set `DATABASE_URL` to a connection string:
  ```
  DATABASE_URL=postgres://user:password@host:5432/database
  ```

  The database, user, and tables must exist. Tables are created automatically on first start (`CREATE TABLE IF NOT EXISTS`). Use the bundled PostgreSQL container with `docker compose --profile db up -d`.

  > **SSL mode:** For remote PostgreSQL hosts, the connection uses `sslmode=require` by default. Override with `DATABASE_SSLMODE=disable` (or `verify-full`, `verify-ca`, etc.).

### SSL / HTTPS

To serve the web UI and REST API over HTTPS:

```bash
# Generate a self-signed certificate (for testing)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout privkey.pem -out fullchain.pem \
  -subj "/CN=localhost"

# Run with SSL
docker run -d --name dc-trade \
  -p 443:8501 -p 8443:8000 \
  -e DC_API_KEY="..." \
  -e SSL_ENABLED=true \
  -e SSL_CERTFILE=/app/certs/fullchain.pem \
  -e SSL_KEYFILE=/app/certs/privkey.pem \
  -v /host/path/to/certs:/app/certs:ro \
  ghcr.io/erenkrmt/dc-trade:latest
```

Or uncomment the `certs` volume in `docker-compose.yml`:

```yaml
volumes:
  - dc_trade_data:/app/data
  - ./certs:/app/certs:ro     # mount your certificate files here
```

For production, use Let's Encrypt or a reverse proxy (nginx, Caddy, Traefik).

> **Discord OAuth:** When SSL is enabled, the app automatically upgrades `DISCORD_REDIRECT_URI` from `http://` to `https://` — no manual change needed.

### Discord Authentication

1. Create an application at [discord.com/developers](https://discord.com/developers/applications)
2. Set `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET` in your environment
3. Set `DISCORD_REDIRECT_URI` to your app's URL followed by `/` (e.g. `https://yourdomain.com/`)
4. Set `ADMIN_DISCORD_IDS` for users that should have admin access
5. The first login creates a company with a trial period (`TRIAL_DAYS`)

---

## 🔌 REST API

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/health` | — | Health check |
| `GET` | `/auth/me` | API key | Current company info |
| `PUT` | `/auth/name` | API key | Update company name |
| `POST` | `/auth/company` | — | Create a new company |
| `GET` | `/stash` | API key | Get stash contents |
| `PUT` | `/stash` | API key | Update stash |
| `PUT` | `/stash/add` | API key | Add materials to stash |
| `POST` | `/stash/clear` | API key | Reset stash to zero |
| `GET` | `/stash/raw` | API key | Parse a game-item dump into stash |
| `GET` | `/stash/auto_subtract` | API key | Check auto-subtract setting |
| `PUT` | `/stash/auto_subtract` | API key | Toggle auto-subtract |
| `GET` | `/deals` | API key | List recent deals |
| `GET` | `/deals/stats` | API key | Deal statistics |
| `PUT` | `/deals/update` | API key | Update a deal |
| `DELETE` | `/deals/delete` | API key | Delete a deal |
| `GET` | `/prices` | — | Current market prices |
| `GET` | `/prices/history` | — | Price history (last 30 days) |
| `GET` | `/stash/public/{token}` | — | Public stash view (no API key needed) |

**Authentication** uses the `X-API-Key` header. Get your API key from the web UI (Profile → Show API key).

---

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
```

## 🛠️ Development Commands

```bash
make help              # Show all commands
make install           # Install dependencies
make dev               # Start both servers
make streamlit         # Start web UI only
make api               # Start REST API only
make test              # Run tests
make docker-build      # Build Docker image
make docker-up         # Start Docker stack
make docker-down       # Stop Docker stack
```

## 📄 License

MIT