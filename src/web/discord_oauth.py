# src/web/discord_oauth.py
"""
Discord OAuth 2.0 helper for the DC Trade Toolbox.
Handles the OAuth flow: authorize URL, token exchange, user info fetch.
"""

import httpx
import logging
from urllib.parse import urlencode

from src.core.settings import get_settings

_settings = get_settings()
logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"


def get_authorize_url(state: str = "") -> str:
    """
    Build the Discord OAuth authorize URL.
    The user is redirected here to log in with Discord.
    """
    params = {
        "client_id": _settings.DISCORD_CLIENT_ID,
        "redirect_uri": _settings.discord_redirect_uri,
        "response_type": "code",
        "scope": "identify",
    }
    if state:
        params["state"] = state
    return f"{DISCORD_API_BASE}/oauth2/authorize?{urlencode(params)}"


async def exchange_code(code: str) -> dict | None:
    """
    Exchange an authorization code for an access token.
    Returns the token data dict, or None on failure.
    """
    if not _settings.DISCORD_CLIENT_ID or not _settings.DISCORD_CLIENT_SECRET:
        logger.error(
            "Discord OAuth not configured (missing DISCORD_CLIENT_ID or DISCORD_CLIENT_SECRET)"
        )
        return None

    data = {
        "client_id": _settings.DISCORD_CLIENT_ID,
        "client_secret": _settings.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _settings.discord_redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{DISCORD_API_BASE}/oauth2/token",
                data=data,
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error(
                    "Discord token exchange failed: %s %s", resp.status_code, resp.text
                )
                return None
            return resp.json()
    except Exception:
        logger.exception("Discord token exchange error")
        return None


async def get_user_info(access_token: str) -> dict | None:
    """
    Fetch user info from Discord using an access token.
    Returns user dict with keys: id, username, avatar, discriminator, etc.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{DISCORD_API_BASE}/users/@me",
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error(
                    "Discord user info fetch failed: %s %s", resp.status_code, resp.text
                )
                return None
            return resp.json()
    except Exception:
        logger.exception("Discord user info error")
        return None


# ── Synchronous helpers (for Streamlit which has a running event loop) ──────


def exchange_code_sync(code: str) -> dict | None:
    """
    Synchronous version of exchange_code — uses httpx.Client instead of AsyncClient.
    Safe to call from Streamlit's event loop context.
    """
    if not _settings.DISCORD_CLIENT_ID or not _settings.DISCORD_CLIENT_SECRET:
        logger.error(
            "Discord OAuth not configured (missing DISCORD_CLIENT_ID or DISCORD_CLIENT_SECRET)"
        )
        return None

    data = {
        "client_id": _settings.DISCORD_CLIENT_ID,
        "client_secret": _settings.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _settings.discord_redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        with httpx.Client() as client:
            resp = client.post(
                f"{DISCORD_API_BASE}/oauth2/token",
                data=data,
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error(
                    "Discord token exchange (sync) failed: %s %s",
                    resp.status_code,
                    resp.text,
                )
                return None
            return resp.json()
    except Exception:
        logger.exception("Discord token exchange (sync) error")
        return None


def get_user_info_sync(access_token: str) -> dict | None:
    """
    Synchronous version of get_user_info — uses httpx.Client instead of AsyncClient.
    Safe to call from Streamlit's event loop context.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        with httpx.Client() as client:
            resp = client.get(
                f"{DISCORD_API_BASE}/users/@me",
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error(
                    "Discord user info fetch (sync) failed: %s %s",
                    resp.status_code,
                    resp.text,
                )
                return None
            return resp.json()
    except Exception:
        logger.exception("Discord user info (sync) error")
        return None


def get_avatar_url(user: dict) -> str:
    """
    Build the CDN URL for a Discord user's avatar.
    Returns empty string if no avatar.
    """
    avatar_hash = user.get("avatar")
    discord_id = user.get("id")
    if not avatar_hash or not discord_id:
        return ""
    is_animated = avatar_hash.startswith("a_")
    ext = "gif" if is_animated else "png"
    return f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.{ext}"
