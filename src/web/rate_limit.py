from fastapi import Request
from src.core.settings import get_settings

_settings = get_settings()


def get_identifier(request: Request) -> str:
    """Return a unique identifier for rate limiting.

    The identifier is based on the `RATE_LIMIT_PER` setting:
    - "ip": use the client IP address.
    - "api_key": use the `X-API-Key` header value.
    """
    if _settings.RATE_LIMIT_PER.lower() == "api_key":
        api_key = request.headers.get("X-API-Key", "")
        return api_key or request.client.host
    # Default to IP-based limiting
    return request.client.host
