import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["RATE_LIMIT"] = "2/minute"

from fastapi.testclient import TestClient
from slowapi import Limiter
from src.web.api import app, limiter

client = TestClient(app)


def test_rate_limit_exceeded():
    # Ensure the limiter uses a small limit for this test even if settings were already imported
    old_limits = limiter._default_limits
    temp_limiter = Limiter(key_func=limiter._key_func, default_limits=["2/minute"])
    limiter._default_limits = temp_limiter._default_limits
    limiter.reset()

    try:
        response = None
        for _ in range(5):
            response = client.get("/health")
            if response.status_code == 429:
                break
        # Ensure we received a 429 Too Many Requests response
        assert response.status_code == 429
        assert response.headers.get("Retry-After") is not None
        assert response.json().get("detail") == "Rate limit exceeded"
    finally:
        limiter._default_limits = old_limits
        limiter.reset()
