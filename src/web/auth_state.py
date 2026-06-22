"""
Unified authentication state for the DC Trade Toolbox web UI.

Provides an :class:`AuthState` dataclass that encapsulates ALL session state
fields used by the Streamlit frontend, with helper methods to apply to /
clear from ``st.session_state`` in a single call.

This replaces the ad-hoc per-key assignment that was duplicated in three places
across ``app.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AuthState:
    """
    Holds all mutable session state for the web UI.

    Every field maps 1:1 to a ``st.session_state`` key set by
    :meth:`apply_to_session_state` and cleared by :meth:`clear_from_session_state`.
    """

    company_id: Optional[int] = None
    company_name: str = ""
    member_id: Optional[int] = None
    discord_id: str = ""
    discord_username: str = ""
    discord_avatar_url: str = ""
    member_role: str = "member"
    is_admin: bool = False
    is_read_only: bool = False
    is_active: bool = False
    session_token: str = ""
    user_companies: list[dict] = field(default_factory=list)
    selected_admin_company: Optional[int] = None

    # ── Convenience properties ──────────────────────────────────────────

    @property
    def is_authenticated(self) -> bool:
        """Return ``True`` if a company is selected (i.e. logged in)."""
        return self.company_id is not None

    # ── Streamlit session-state bridge ───────────────────────────────────

    def apply_to_session_state(self) -> None:
        """
        Write every field into the calling module's ``st.session_state``.

        Only call this from within a Streamlit context (i.e. after ``import streamlit as st``).
        The import is intentionally deferred so this module can be imported outside of
        Streamlit contexts without error.
        """
        import streamlit as st  # noqa: PLC0415

        st.session_state.company_id = self.company_id
        st.session_state.company_name = self.company_name
        st.session_state.member_id = self.member_id
        st.session_state.discord_id = self.discord_id
        st.session_state.discord_username = self.discord_username
        st.session_state.discord_avatar_url = self.discord_avatar_url
        st.session_state.member_role = self.member_role
        st.session_state.is_admin = self.is_admin
        st.session_state.is_read_only = self.is_read_only
        st.session_state.is_active = self.is_active
        st.session_state.session_token = self.session_token
        st.session_state.user_companies = self.user_companies
        st.session_state.selected_admin_company = self.selected_admin_company

    @classmethod
    def from_session_state(cls) -> AuthState:
        """
        Build an :class:`AuthState` from the current ``st.session_state``.

        Returns a default (unauthenticated) instance for any keys that don't
        exist yet in session state, so it's safe to call before
        :meth:`init_session_state` or :meth:`apply_to_session_state`.
        """
        import streamlit as st  # noqa: PLC0415

        def _get(key: str, default=None):
            return st.session_state.get(key, default)

        return cls(
            company_id=_get("company_id"),
            company_name=_get("company_name", ""),
            member_id=_get("member_id"),
            discord_id=_get("discord_id", ""),
            discord_username=_get("discord_username", ""),
            discord_avatar_url=_get("discord_avatar_url", ""),
            member_role=_get("member_role", "member"),
            is_admin=bool(_get("is_admin", False)),
            is_read_only=bool(_get("is_read_only", False)),
            is_active=bool(_get("is_active", False)),
            session_token=_get("session_token", ""),
            user_companies=_get("user_companies", []),
            selected_admin_company=_get("selected_admin_company"),
        )

    @staticmethod
    def clear_from_session_state() -> None:
        """Reset all auth-related keys in ``st.session_state`` to their defaults."""
        import streamlit as st  # noqa: PLC0415

        st.session_state.company_id = None
        st.session_state.company_name = ""
        st.session_state.member_id = None
        st.session_state.discord_id = ""
        st.session_state.discord_username = ""
        st.session_state.discord_avatar_url = ""
        st.session_state.member_role = ""
        st.session_state.is_admin = False
        st.session_state.is_read_only = False
        st.session_state.is_active = False
        st.session_state.session_token = ""
        st.session_state.user_companies = []
        st.session_state.selected_admin_company = None
