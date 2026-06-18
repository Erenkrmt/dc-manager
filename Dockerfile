# =============================================================================
# Dockerfile – DC Trade Toolbox
# Multi-stage build: dependencies first, then app
# =============================================================================

# ---- Base stage ----
FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system deps (for psycopg2, uvloop, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ---- Dependencies stage ----
FROM base AS deps

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --no-dev --frozen

# ---- Runtime stage ----
FROM deps AS runtime

COPY . .

# Create data directory with correct permissions
RUN mkdir -p /app/data && chmod -R 777 /app/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Expose ports: 8501 (Streamlit), 8000 (FastAPI)
EXPOSE 8501 8000

# Default: run both Streamlit + API via supervisor-like script
CMD ["python", "scripts/run.py"]