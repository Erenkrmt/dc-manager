# =============================================================================
# Dockerfile – DC Trade Toolbox
# Multi-stage build: dependencies first, then app
# Uses uv for fast package resolution + BuildKit cache mounts
# =============================================================================

# ---- Base stage ----
FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

# Install uv for fast pip installs
RUN pip install uv

# ---- Dependencies stage ----
FROM base AS deps

# Install system build deps (needed for psycopg2, uvloop, etc.)
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency files first (for caching)
COPY requirements.txt ./

# Install packages system-wide using uv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-cache-dir -r requirements.txt

# Remove build deps from the system (not needed at runtime)
RUN apt-get remove -y gcc libpq-dev && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ---- Runtime stage ----
FROM deps AS runtime

COPY . .

# Create data directory with correct permissions
RUN mkdir -p /app/data && chmod -R 755 /app/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Expose ports: 8501 (Streamlit), 8000 (FastAPI)
EXPOSE 8501 8000

# Default: run both Streamlit + API via supervisor-like script
CMD ["python", "scripts/run.py"]