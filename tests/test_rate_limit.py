import os

os.environ["RATE_LIMIT"] = "1/second"

from fastapi.testclient import TestClient
from src.web.api import app

client = TestClient(app)


def test_rate_limit_exceeded():
    # Send requests quickly to exceed the default limit (e.g., 100/minute).
    # We'll set a low limit in env for the test if needed, but here we just loop.
    for _ in range(5):
        response = client.get("/health")
        if response.status_code == 429:
            break
    # Ensure we received a 429 Too Many Requests response
    assert response.status_code == 429
    assert response.headers.get("Retry-After") is not None
    assert response.json().get("detail") == "Rate limit exceeded"
