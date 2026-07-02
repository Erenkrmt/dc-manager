# =============================================================================
# Dockerfile – DC Trade Toolbox
# Optimized multi-stage build using uv.lock for deterministic production builds
# =============================================================================

# ---- Builder stage ----
FROM python:3.11-slim AS builder

WORKDIR /app

# Copy uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project configuration and lockfile
COPY pyproject.toml uv.lock ./

# Install project dependencies from the lockfile
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy only the installed dependencies from builder's virtual environment
COPY --from=builder /app/.venv/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy only required source files
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY main.py ./

# Create data directory with correct permissions
RUN mkdir -p /app/data && chmod -R 755 /app/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; port=os.getenv('API_PORT','8000'); p='https' if os.getenv('SSL_ENABLED','').lower() in ('1','true','yes') else 'http'; urllib.request.urlopen(p+'://localhost:'+port+'/health',timeout=5)" || exit 1

EXPOSE 8501 8000

CMD ["python", "scripts/run.py"]