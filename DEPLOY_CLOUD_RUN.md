# 🚀 Deploy to Google Cloud Run

This guide walks you through deploying the DC Trade Toolbox (FastAPI only) to [Google Cloud Run](https://cloud.google.com/run).

## Overview

- **Cloud Run** – serverless container runtime (pay per request, auto-scales)
- **FastAPI** – serves the REST API on port `8080` (or whatever `$PORT` is set to)
- **Cloud SQL (PostgreSQL)** – persistent database (optional; SQLite works but is ephemeral)
- **Artifact Registry** – stores the Docker image
- **Cloud Build** – CI/CD pipeline (build → push → deploy)

---

## Prerequisites

1. [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed
2. A GCP project with billing enabled
3. Required APIs enabled:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com
```

4. A [DemocracyCraft API key](https://api.democracycraft.net) stored in Secret Manager:

```bash
echo -n "your-api-key-here" | \
  gcloud secrets create dc-api-key --data-file=-
```

---

## Option 1: Quick Deploy (SQLite – ephemeral storage)

> ⚠️ **Warning:** SQLite data is lost when the container restarts. Only use for testing.

```bash
cd dc_trade_api

# Build with Cloud Build
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_SERVICE_NAME=dc-trade-api,_REGION=europe-west1

# Or build & deploy manually:
docker build -f Dockerfile.cloudrun -t gcr.io/YOUR_PROJECT/dc-trade-api .
docker push gcr.io/YOUR_PROJECT/dc-trade-api
gcloud run deploy dc-trade-api \
  --image=gcr.io/YOUR_PROJECT/dc-trade-api \
  --region=europe-west1 \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --memory=512Mi \
  --set-secrets=DC_API_KEY=dc-api-key:latest
```

---

## Option 2: Production Deploy (Cloud SQL PostgreSQL)

### Step 1: Create a Cloud SQL PostgreSQL instance

```bash
gcloud sql instances create dc-trade-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=europe-west1 \
  --root-password=your-strong-password
```

### Step 2: Create the database

```bash
gcloud sql databases create dctrade --instance=dc-trade-db
```

### Step 3: Create a user

```bash
gcloud sql users create dctrade --instance=dc-trade-db --password=your-strong-password
```

### Step 4: Update `cloudbuild.yaml`

Edit the `_CLOUD_SQL_INSTANCE` substitution in `cloudbuild.yaml`:

```yaml
_CLOUD_SQL_INSTANCE: your-project:europe-west1:dc-trade-db
_DB_USER: dctrade
_DB_PASS: your-strong-password
_DB_NAME: dctrade
```

### Step 5: Deploy

```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=\
_SERVICE_NAME=dc-trade-api,\
_REGION=europe-west1,\
_CLOUD_SQL_INSTANCE=your-project:europe-west1:dc-trade-db,\
_DB_USER=dctrade,\
_DB_PASS=your-strong-password,\
_DB_NAME=dctrade
```

### Step 6: Enable the Cloud SQL Admin API (if not already)

```bash
gcloud services enable sqladmin.googleapis.com
```

The Cloud Run service will now connect to Cloud SQL via the Unix socket at `/cloudsql/your-project:europe-west1:dc-trade-db`.

---

## Option 3: Manual Deploy (without Cloud Build)

```bash
# 1. Authenticate
gcloud auth configure-docker europe-west1-docker.pkg.dev

# 2. Create Artifact Registry repo (one-time)
gcloud artifacts repositories create cloud-run-source-deploy \
  --repository-format=docker \
  --location=europe-west1

# 3. Build & tag
docker build -f Dockerfile.cloudrun \
  -t europe-west1-docker.pkg.dev/YOUR_PROJECT/cloud-run-source-deploy/dc-trade-api:latest .

# 4. Push
docker push europe-west1-docker.pkg.dev/YOUR_PROJECT/cloud-run-source-deploy/dc-trade-api:latest

# 5. Deploy
gcloud run deploy dc-trade-api \
  --image=europe-west1-docker.pkg.dev/YOUR_PROJECT/cloud-run-source-deploy/dc-trade-api:latest \
  --region=europe-west1 \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10 \
  --concurrency=80 \
  --timeout=300 \
  --set-secrets=DC_API_KEY=dc-api-key:latest \
  --update-env-vars=COMPANY_NAME=Fishy Business,CACHE_DURATION=21600,DEBUG=false

# (For PostgreSQL) add:
#   --add-cloudsql-instances=your-project:europe-west1:dc-trade-db \
#   --set-env-vars=DATABASE_URL=postgres://dctrade:password@//cloudsql/your-project:europe-west1:dc-trade-db/dctrade
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DC_API_KEY` | ✅ | DemocracyCraft API key (use Secret Manager) |
| `COMPANY_NAME` | ❌ | Branding in UI (default: "Fishy Business") |
| `DATABASE_URL` | ❌ | PostgreSQL connection string (omit for SQLite) |
| `CACHE_DURATION` | ❌ | Price cache TTL in seconds (default: 21600 = 6h) |
| `DEBUG` | ❌ | Enable debug mode (default: false) |
| `API_TIMEOUT` | ❌ | API timeout in seconds (default: 10) |
| `API_RETRIES` | ❌ | Number of API retries (default: 3) |

> **Note:** `PORT` is set automatically by Cloud Run. The container listens on whatever `PORT` is set to.

---

## Verifying the Deployment

After deployment, Cloud Run provides a URL like `https://dc-trade-api-xxxx-ew.a.run.app`.

Test the endpoints:

```bash
# Health check
curl https://dc-trade-api-xxxx-ew.a.run.app/health

# API docs
curl https://dc-trade-api-xxxx-ew.a.run.app/docs

# Stash
curl https://dc-trade-api-xxxx-ew.a.run.app/stash

# Prices
curl https://dc-trade-api-xxxx-ew.a.run.app/prices

# Deals
curl https://dc-trade-api-xxxx-ew.a.run.app/deals

# Public stash page (shareable with customers)
curl https://dc-trade-api-xxxx-ew.a.run.app/stash/public
```

---

## Files Reference

| File | Description |
|------|-------------|
| `Dockerfile.cloudrun` | Cloud Run-optimized Docker image |
| `scripts/run_cloudrun.py` | Entry point that listens on `$PORT` |
| `cloudbuild.yaml` | CI/CD pipeline (build → push → deploy) |
| `.gcloudignore` | Files excluded from Cloud Build uploads |
| `src/core/database.py` | Dual SQLite/PostgreSQL database layer |

---

## Notes

- **Streamlit UI is NOT deployed** – Cloud Run runs only the FastAPI REST API.
- For the Streamlit web UI, run locally or deploy separately.
- The container is **stateless by design** – use Cloud SQL for persistent data.
- Auto-scales from 0 to 10 instances by default (adjust `max-instances` as needed).
- Cold starts take ~3–5 seconds on the first request after idle.