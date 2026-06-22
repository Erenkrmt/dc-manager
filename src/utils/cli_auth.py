"""Session context and authentication for the CLI."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from src.core import database as db

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path.home() / ".dc_trade_config"


@dataclass
class SessionContext:
    """
    Holds all mutable session state for the CLI.

    Replaces the module-level globals ``_COMPANY_ID`` and ``_IS_READ_ONLY``
    so that state can be passed explicitly instead of mutated via ``global``.
    """

    company_id: int = 1
    is_read_only: bool = False

    # ── helpers that use self.company_id ──────────────────────────────

    def stash_auto_subtract(self) -> bool:
        """Return whether auto-subtract is enabled for this session's company."""
        return bool(db.get_auto_subtract(company_id=self.company_id))

    def set_auto_subtract(self, enabled: bool) -> None:
        """Toggle auto-subtract for this session's company."""
        db.set_auto_subtract(enabled, company_id=self.company_id)

    def load_stash(self) -> dict:
        """Load stash for this session's company."""
        return db.load_stash(company_id=self.company_id)

    def save_stash(self, stash: dict) -> None:
        """Save stash for this session's company."""
        db.save_stash(stash, company_id=self.company_id)

    def clear_stash(self) -> None:
        """Clear stash for this session's company."""
        db.clear_stash(company_id=self.company_id)


def _load_config() -> dict:
    """Load CLI config from ``~/.dc_trade_config``."""
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_config(config: dict) -> None:
    """Save CLI config to ``~/.dc_trade_config`` with restricted permissions."""
    try:
        _CONFIG_FILE.write_text(json.dumps(config, indent=2))
        os.chmod(_CONFIG_FILE, 0o600)
    except OSError as exc:
        logger.warning("Could not save config: %s", exc)


def resolve_company() -> SessionContext | None:
    """
    Prompt for API key (or load from config), validate, return a
    :class:`SessionContext` or ``None`` if authentication failed.

    The returned context holds the resolved ``company_id`` and
    ``is_read_only`` flag, replacing the previous module-level globals.
    """
    config = _load_config()
    api_key = config.get("api_key", "")

    if not api_key:
        print("\n🔑 Enter your API key to authenticate with the server.")
        print("  (Get your key from the web UI → My API Key)")
        api_key = input("API Key: ").strip()

    company = db.get_company_by_api_key(api_key)
    if not company:
        print("\n❌ Invalid API key. Please check your key and try again.")
        return None

    # Save to config for next time
    config["api_key"] = api_key
    _save_config(config)

    company_id = company["id"]
    is_active, is_read_only = db.check_company_access(company_id)

    if not is_active:
        print("\n❌ Your account is inactive. Contact the admin.")
        return None

    print(f"\n✅ Authenticated as {company.get('discord_username', company.get('company_name', 'User'))}")

    ctx = SessionContext(company_id=company_id, is_read_only=is_read_only)
    if ctx.is_read_only:
        print("⚠️  **Read-only mode** — your access has expired. Contact Fishy Business to renew.")
    return ctx
