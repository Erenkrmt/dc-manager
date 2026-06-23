"""
DemocracyCraft Trading Toolbox – Streamlit Web Interface
Multi-company: Discord OAuth login, scoped by company_id, admin dashboard.
"""

import sys
import os
import logging
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timezone

# Ensure the project root is on sys.path so src.* imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd

from src.core.market_deal import (
    MarketDeal,
    analyze_deal,
    stash_ingot_equivalents,
    fetch_live_prices,
    stash_market_value,
    total_stash_shipping,
)
from src.core.settings import get_settings
from src.core import database as db
from src.web.discord_oauth import get_authorize_url, get_avatar_url
from src.web.session import (
    store_session,
    clear_session as _clear_db_session,
    restore_from_url_param,
)
from src.web.auth_state import AuthState

logger = logging.getLogger(__name__)

_settings = get_settings()

# Initialize database schema on startup
db.init_db()


# ── OAuth callback helper (run ONCE, then lock) ────────────────────────────


def _handle_oauth_callback() -> AuthState | None:
    """
    Process the Discord OAuth ``?code=...`` query parameter exactly once.

    After successfully exchanging the code and fetching user info, the ``code``
    param is **immediately removed** from the URL so it cannot be re-processed
    on a subsequent rerun (Discord codes are single-use — reusing them produces
    the "token exchange returned no data" error).

    Returns an :class:`AuthState` fully populated with the selected company, or
    ``None`` if the callback is not present or could not be processed.
    """
    # ── 1. Check for OAuth code ──────────────────────────────────────────
    code = st.query_params.get("code", [None])
    if isinstance(code, list):
        code = code[0] if code else None
    if not code:
        return None

    # ── 2. Lock so this runs once per code ───────────────────────────────
    # Streamlit reruns the whole script on every interaction, so the code
    # param would be re-read every time. We track consumption in session_state.
    if st.session_state.get("_oauth_code_consumed"):
        return None

    st.session_state._oauth_code_consumed = True

    from src.web.discord_oauth import exchange_code_sync, get_user_info_sync

    try:
        token_data = exchange_code_sync(code)
        if not token_data:
            st.error("❌ Login failed: Discord token exchange returned no data.")
            return None

        access_token = token_data.get("access_token")
        if not access_token:
            st.error("❌ Login failed: No access token in Discord response.")
            return None

        user = get_user_info_sync(access_token)
    except Exception as exc:
        logger.exception("Discord OAuth login failed")
        st.error(f"❌ Login failed: {exc}")
        return None

    if not user:
        st.error("❌ Discord login failed. Could not fetch user info.")
        return None

    # ── 3. Remove the code from the URL so it can't be re-processed ──────
    st.query_params.clear()
    # (session param will be set after company selection)

    discord_id = str(user["id"])
    discord_username = user.get("username", "Unknown")
    discord_avatar = get_avatar_url(user)

    # ── 4. Check if user has existing memberships ────────────────────────
    user_companies = db.get_user_companies(discord_id)

    if user_companies:
        # Store user info in session_state so the company-picker can use it
        # without re-fetching. The actual login happens when they click
        # "Login to selected company" which triggers _complete_login().
        return AuthState(
            user_companies=user_companies,
            discord_id=discord_id,
            discord_username=discord_username,
            discord_avatar_url=discord_avatar,
        )

    # ── 5. First-time user — auto-create company ────────────────────────
    try:
        company, member = db.get_or_create_company_by_discord(discord_id, discord_username, discord_avatar)
    except Exception as exc:
        st.error(f"❌ Database error: {exc}")
        return None

    if not company or not member:
        st.error("❌ Could not create or find your company account.")
        return None

    return _build_auth_state(company, member, discord_id, discord_username, discord_avatar)


def _build_auth_state(
    company: dict,
    member: dict,
    discord_id: str,
    discord_username: str,
    discord_avatar: str,
) -> AuthState:
    """Build and return a fully populated AuthState from company + member data."""
    session_token = store_session(member["id"])
    is_active, is_read_only = db.check_company_access(company["id"])
    return AuthState(
        company_id=company["id"],
        company_name=company.get("company_name", ""),
        member_id=member["id"],
        discord_id=discord_id,
        discord_username=discord_username,
        discord_avatar_url=discord_avatar,
        member_role=member.get("role", "member"),
        session_token=session_token,
        is_admin=discord_id in _settings.ADMIN_DISCORD_IDS,
        is_read_only=is_read_only,
        is_active=is_active,
    )


def _complete_login(
    member_id: int,
    company_id: int,
    discord_id: str,
    discord_username: str,
    discord_avatar: str,
    company_name: str,
    member_role: str,
) -> AuthState:
    """Generate a session token and build an AuthState for a completed login."""
    session_token = store_session(member_id)
    is_active, is_read_only = db.check_company_access(company_id)
    return AuthState(
        company_id=company_id,
        company_name=company_name,
        member_id=member_id,
        discord_id=discord_id,
        discord_username=discord_username,
        discord_avatar_url=discord_avatar,
        member_role=member_role,
        session_token=session_token,
        is_admin=discord_id in _settings.ADMIN_DISCORD_IDS,
        is_read_only=is_read_only,
        is_active=is_active,
    )


# ── Session helpers ────────────────────────────────────────────────────────


def _try_restore_session() -> bool:
    """
    Try to restore session from a one-time URL session token.
    Format: ``?session=mid:cid:token``
    If valid, rotates the token and applies to session_state.
    Returns True if session was restored.
    """
    session_param = st.query_params.get("session", None)
    if isinstance(session_param, list):
        session_param = session_param[0] if session_param else None
    if not session_param:
        return False

    session_data = restore_from_url_param(session_param)
    if not session_data:
        # Don't clear query params here — may be an OAuth callback in progress
        return False

    auth = AuthState(
        company_id=session_data["company_id"],
        company_name=session_data["company_name"],
        member_id=session_data.get("member_id"),
        discord_id=session_data.get("discord_id", ""),
        discord_username=session_data["discord_username"],
        discord_avatar_url=session_data["discord_avatar_url"],
        member_role=session_data.get("member_role", "member"),
        is_admin=session_data["is_admin"],
        is_read_only=session_data["is_read_only"],
        is_active=session_data["is_active"],
        session_token=session_data["session_token"],
    )
    auth.apply_to_session_state()

    # Update URL with rotated token
    st.query_params.clear()
    st.query_params["session"] = (
        f"{session_data['member_id']}:{session_data['company_id']}:{session_data['session_token']}"
    )
    return True


def init_session_state() -> None:
    """Initialize auth session state from stored token or OAuth callback."""
    # ── Ensure all auth keys exist (default = unauthenticated) ──────
    if "company_id" not in st.session_state:
        AuthState().apply_to_session_state()

    # ── Track OAuth code consumption ──
    if "_oauth_code_consumed" not in st.session_state:
        st.session_state._oauth_code_consumed = False

    # ── Non-auth UI state defaults ──
    if "selected_admin_company" not in st.session_state:
        st.session_state.selected_admin_company = None
    if "template_load" not in st.session_state:
        st.session_state.template_load = None
    if "deal_result" not in st.session_state:
        st.session_state.deal_result = None
    if "shulker_result" not in st.session_state:
        st.session_state.shulker_result = None

    # ── Restore session from URL token ──
    if st.session_state.company_id is None:
        if _try_restore_session():
            return  # success — no need to process OAuth

    # ── Process OAuth callback (only if not authenticated) ──
    if st.session_state.company_id is None and st.query_params.get("code"):
        auth = _handle_oauth_callback()
        if auth and auth.is_authenticated:
            auth.apply_to_session_state()
            # Set URL session param
            st.query_params.clear()
            st.query_params["session"] = f"{auth.member_id}:{auth.company_id}:{auth.session_token}"
            st.rerun()
        elif auth and not auth.is_authenticated:
            # User has companies but hasn't selected one yet
            auth.apply_to_session_state()
        # else: auth is None (error already shown)


def clear_session() -> None:
    """Clear all session state (logout)."""
    # Clear the stored session token from DB so it can't be reused
    mid = st.session_state.get("member_id")
    if mid is not None:
        _clear_db_session(mid)
    AuthState.clear_from_session_state()
    st.session_state._oauth_code_consumed = False
    st.query_params.clear()


def check_read_only() -> None:
    """Show a warning banner if company is in read-only mode."""
    if st.session_state.is_read_only:
        st.warning(
            "🔒 **Read-only mode.** Your trial/access has expired. Contact Fishy Business to renew your subscription.",
            icon="⚠️",
        )


# ── API Background Thread (once per process) ───────────────────────────────
# ⚠️ CRITICAL: Streamlit re-executes this module on EVERY user interaction
# (button click, rerun, page navigation). Without this guard, a NEW uvicorn
# subprocess would be spawned on every rerun, causing port conflicts (port
# 8000 already bound), orphaned processes, and the server appearing to
# restart continuously.


def _start_api_server():
    """Start the FastAPI server in a background subprocess."""
    project_root = Path(__file__).resolve().parents[2]
    api_port = os.getenv("API_PORT", "8000")
    logger.info("Starting FastAPI background server on port %s", api_port)
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.web.api:app",
                "--host",
                "0.0.0.0",
                "--port",
                api_port,
            ],
            cwd=str(project_root),
            check=False,
        )
    except Exception:
        logger.exception("FastAPI background server exited")


# Guard: only start the API server thread ONCE per process lifetime.
# We use a module-level flag because st.session_state is cleared on rerun
# and would NOT prevent the duplicate spawns.
if "_api_server_started" not in globals():
    _api_server_started = False

if not _api_server_started:
    _api_server_started = True
    api_thread = threading.Thread(target=_start_api_server, daemon=True)
    api_thread.start()


# ── Page Config ────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=f"{_settings.COMPANY_NAME} Toolbox",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()


# ═══════════════════════════════════════════════════════════════════════════
# LOGIN PAGE
# ═══════════════════════════════════════════════════════════════════════════


def render_login_page() -> None:
    """Display the login/landing page before the user authenticates."""
    st.title(f"⛏️ {_settings.COMPANY_NAME} Toolbox")
    st.markdown("### Bulk Trading Calculator for DemocracyCraft")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("🔑 Login with Discord")
        st.markdown(
            "Sign in with your Discord account to access the trading toolbox.\n\n"
            "**First time?** You'll get a **3-day free trial** immediately."
        )

        # Build the Discord OAuth authorize URL
        discord_login_url = get_authorize_url(state="dc_trade")

        # Use st.link_button to redirect to Discord
        st.link_button(
            "🔵 Login with Discord",
            discord_login_url,
            use_container_width=True,
            type="primary",
        )

        # ── Company picker (shown after OAuth if user has multiple companies) ──
        user_companies = st.session_state.get("user_companies", [])
        if user_companies and st.session_state.company_id is None:
            st.markdown("---")
            st.subheader("🏢 Select Company")

            company_options = {f"{c['company_name']} ({c['role']})": c for c in user_companies}
            selected_label = st.selectbox(
                "Select a company to log into:",
                list(company_options.keys()),
                key="company_picker",
            )
            selected = company_options[selected_label]

            if st.button("🔑 Login to selected company", type="primary"):
                auth = _complete_login(
                    member_id=selected["member_id"],
                    company_id=selected["company_id"],
                    discord_id=st.session_state.discord_id,
                    discord_username=st.session_state.discord_username,
                    discord_avatar=st.session_state.discord_avatar_url,
                    company_name=selected["company_name"],
                    member_role=selected["role"],
                )
                auth.apply_to_session_state()
                st.query_params.clear()
                st.query_params["session"] = f"{auth.member_id}:{auth.company_id}:{auth.session_token}"
                st.rerun()

            # Also show invite acceptance option
            st.markdown("---")
            st.subheader("🎟️ Have an invite code?")
            invite_code = st.text_input("Enter invite code:", key="invite_code_input")
            if st.button("Accept Invite", type="secondary", use_container_width=True):
                if invite_code.strip():
                    member = db.add_member_by_invite(
                        invite_code.strip(),
                        st.session_state.discord_id,
                        st.session_state.discord_username,
                        st.session_state.discord_avatar_url,
                    )
                    if member:
                        st.session_state.user_companies = db.get_user_companies(st.session_state.discord_id)
                        st.success("✅ You've been added to a new company! Select it above.")
                        st.rerun()
                    else:
                        st.error("❌ Invalid invite code or already a member.")

    with col2:
        st.subheader("🐟 About")
        st.markdown(
            f"Welcome to **{_settings.COMPANY_NAME}'s** trading toolbox!\n\n"
            "**Features:**\n"
            "- 💰 Deal Calculator\n"
            "- 📦 Shulker Scanner\n"
            "- 📊 Deal History\n"
            "- 📦 Stash Manager\n"
            "- 📋 Deal Templates\n"
            "- 🔍 Item Lookup\n"
            "- 📈 Price History\n\n"
            "Powered by the DemocracyCraft economy API."
        )


# ═══════════════════════════════════════════════════════════════════════════
# MAIN UI (authenticated)
# ═══════════════════════════════════════════════════════════════════════════


def main() -> None:
    """Entry point for `dc-trade-web` CLI command."""
    pass


# ── If not logged in, show login page ──
if st.session_state.company_id is None:
    render_login_page()
    st.stop()

# ── Logged in — show read-only warning if needed ──
check_read_only()

# Determine the company_id to use (admin may view other companies)
company_id = st.session_state.company_id
admin_viewing_company = st.session_state.get("selected_admin_company")
if admin_viewing_company is not None and st.session_state.is_admin:
    company_id = admin_viewing_company

# ── Logout button in top-right ──
with st.container():
    col_logo, col_logout = st.columns([5, 1])
    with col_logo:
        avatar = st.session_state.discord_avatar_url
        username = st.session_state.discord_username
        if avatar:
            st.markdown(
                f"<span style='display:flex;align-items:center;gap:8px;'>"
                f"<img src='{avatar}' width='32' height='32' style='border-radius:50%'>"
                f"<span>{username}</span>"
                f"</span>",
                unsafe_allow_html=True,
            )
        else:
            st.caption(f"👤 {username}")
    with col_logout:
        if st.button("🚪 Logout"):
            clear_session()
            st.rerun()

st.markdown("---")


# ── Fetch live prices (cached) ──
@st.cache_data(ttl=_settings.CACHE_DURATION, show_spinner="⏳ Fetching live prices...")
def fetch_prices() -> tuple[float, float, float]:
    p_iron, p_gold, p_diamond, _ = fetch_live_prices()
    return p_iron, p_gold, p_diamond


price_iron, price_gold, price_diamond = fetch_prices()

# ── Sidebar ──
st.sidebar.title(f"⛏️ {_settings.COMPANY_NAME} Toolbox")
st.sidebar.markdown(f"👤 **{st.session_state.discord_username}**")
if st.session_state.is_admin:
    st.sidebar.success("🛡️ **Admin Mode**")
if st.session_state.is_read_only:
    st.sidebar.warning("🔒 **Read-only**")
st.sidebar.markdown("---")

# Navigation — admin gets extra pages; free tier gets limited features
_company_tier = db.get_company_tier(company_id)
_is_premium = _company_tier == "premium" or st.session_state.is_admin

nav_pages = [
    "💰 Deal Calculator",
    "⚡ Quick Converter",
    "📊 Deal History",
]
if _is_premium:
    nav_pages += [
        "📦 Shulker Scanner",
        "📦 Stash Manager",
        "📋 Deal Templates",
        "🔍 Item Lookup",
        "📈 Price History",
    ]
nav_pages.append("👤 My Profile")
if st.session_state.is_admin:
    nav_pages.append("🏢 Company Management")

page = st.sidebar.radio("Navigation", nav_pages)

st.sidebar.markdown("---")

# Sidebar: live prices
st.sidebar.subheader("📈 Live Prices")
st.sidebar.metric("Iron Ingot", f"${price_iron:.2f}")
st.sidebar.metric("Gold Ingot", f"${price_gold:.2f}")
st.sidebar.metric("Diamond", f"${price_diamond:.2f}")

iron_block_price = price_iron * _settings.INGOTS_PER_BLOCK
gold_block_price = price_gold * _settings.INGOTS_PER_BLOCK
diamond_block_price = price_diamond * _settings.INGOTS_PER_BLOCK

min_pct = _settings.MIN_ACCEPTABLE_PERCENT

prices_block_col1, prices_block_col2, prices_block_col3 = st.sidebar.columns(3)
prices_block_col1.caption("💰 **Per Block**")
prices_block_col2.caption("💰 **Per Stack of Blocks**")
prices_block_col3.caption(f"📉 **Min ({min_pct * 100:.0f}%) / Stack**")

prices_block_col1.metric("Iron", f"${iron_block_price:.2f}")
prices_block_col2.metric("Iron", f"${iron_block_price * 64:,.2f}")
prices_block_col3.metric(
    "Iron",
    f"${iron_block_price * 64 * min_pct:,.2f}",
    delta=f"-{(1 - min_pct) * 100:.0f}%",
)
prices_block_col1.metric("Gold", f"${gold_block_price:.2f}")
prices_block_col2.metric("Gold", f"${gold_block_price * 64:,.2f}")
prices_block_col3.metric(
    "Gold",
    f"${gold_block_price * 64 * min_pct:,.2f}",
    delta=f"-{(1 - min_pct) * 100:.0f}%",
)
prices_block_col1.metric("Diamond", f"${diamond_block_price:.2f}")
prices_block_col2.metric("Diamond", f"${diamond_block_price * 64:,.2f}")
prices_block_col3.metric(
    "Diamond",
    f"${diamond_block_price * 64 * min_pct:,.2f}",
    delta=f"-{(1 - min_pct) * 100:.0f}%",
)

# Sidebar: stash summary (scoped) — using shared stash_ingot_equivalents
stash_summary = db.load_stash(company_id=company_id)
st.sidebar.subheader("📦 Your Stash")

if stash_summary.get("updated_at") != "never" and any(
    [
        stash_summary.get("iron_blocks", 0),
        stash_summary.get("iron_ingots", 0),
        stash_summary.get("gold_blocks", 0),
        stash_summary.get("gold_ingots", 0),
        stash_summary.get("diamond_blocks", 0),
        stash_summary.get("diamond_items", 0),
        stash_summary.get("raw_iron_blocks", 0),
        stash_summary.get("raw_gold_blocks", 0),
    ]
):
    total_iron, total_gold, total_diamond = stash_ingot_equivalents(stash_summary)
    total_value = stash_market_value(stash_summary, (price_iron, price_gold, price_diamond))

    iron_parts = []
    if stash_summary.get("raw_iron_blocks"):
        iron_parts.append(f"{stash_summary['raw_iron_blocks']} raw")
    if stash_summary.get("iron_blocks"):
        iron_parts.append(f"{stash_summary['iron_blocks']}b")
    if stash_summary.get("iron_ingots"):
        iron_parts.append(f"{stash_summary['iron_ingots']}i")
    iron_display = " + ".join(iron_parts) if iron_parts else "0"
    gold_parts = []
    if stash_summary.get("raw_gold_blocks"):
        gold_parts.append(f"{stash_summary['raw_gold_blocks']} raw")
    if stash_summary.get("gold_blocks"):
        gold_parts.append(f"{stash_summary['gold_blocks']}b")
    if stash_summary.get("gold_ingots"):
        gold_parts.append(f"{stash_summary['gold_ingots']}i")
    gold_display = " + ".join(gold_parts) if gold_parts else "0"
    diamond_parts = []
    if stash_summary.get("diamond_blocks"):
        diamond_parts.append(f"{stash_summary['diamond_blocks']}b")
    if stash_summary.get("diamond_items"):
        diamond_parts.append(f"{stash_summary['diamond_items']}i")
    diamond_display = " + ".join(diamond_parts) if diamond_parts else "0"
    st.sidebar.caption(f"⬜ Iron: {iron_display}\n🟨 Gold: {gold_display}\n💎 Diamond: {diamond_display}")
    st.sidebar.metric("Total Value", f"${total_value:,.2f}")
    st.sidebar.caption(f"Updated: {stash_summary.get('updated_at', 'never')}")
else:
    st.sidebar.caption("Empty — add materials in Stash Manager.")

st.sidebar.markdown("---")
st.sidebar.caption(f"Data cached for {_settings.CACHE_DURATION // 3600}h")
st.sidebar.caption(f"Database: `{_settings.DB_FILE}`")


# ═══════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════


def _format_subtract_result(result: dict) -> str:
    """Format a stash subtraction result dict into a human-readable string."""
    parts = []
    if result.get("iron_blocks") or result.get("iron_ingots"):
        parts.append(f"Iron: {result['iron_blocks']} blocks + {result['iron_ingots']} ingots")
    if result.get("gold_blocks") or result.get("gold_ingots"):
        parts.append(f"Gold: {result['gold_blocks']} blocks + {result['gold_ingots']} ingots")
    if result.get("diamond_blocks") or result.get("diamond_items"):
        parts.append(f"Diamonds: {result['diamond_blocks']} blocks + {result['diamond_items']} items")
    return " | ".join(parts)


def _log_deal_with_all_fields(  # noqa: PLR0913 - many parameters needed for all deal fields
    iron_ingots: float,
    gold_ingots: float,
    diamond_items: float,
    market_value: float,
    offered_price: float,
    status: str,
    iron_price: float,
    gold_price: float,
    diamond_price: float,
    iron_amount: float = 0.0,
    iron_unit: str = "ingot",
    gold_amount: float = 0.0,
    gold_unit: str = "ingot",
    diamond_amount: float = 0.0,
    diamond_unit: str = "ingot",
) -> None:
    ph = db._ph()
    profit = offered_price - market_value
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""INSERT INTO deals
               (company_id, timestamp, iron_ingots, gold_ingots, diamond_items,
                iron_price, gold_price, diamond_price,
                market_value, offered_price, status, profit,
                iron_amount, iron_unit, gold_amount, gold_unit,
                diamond_amount, diamond_unit)
               VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
            (
                company_id,
                date_str,
                iron_ingots,
                gold_ingots,
                diamond_items,
                iron_price,
                gold_price,
                diamond_price,
                market_value,
                offered_price,
                status,
                profit,
                iron_amount,
                iron_unit,
                gold_amount,
                gold_unit,
                diamond_amount,
                diamond_unit,
            ),
        )
        conn.commit()
        conn.close()
        logging.getLogger(__name__).info("Deal logged to database: %s | %s", status, date_str)
    except Exception:
        logging.getLogger(__name__).exception("Failed to log deal")


def _handle_deal_logging(  # noqa: PLR0913 - many parameters needed for logging all deal details
    iron_ingots_val: float,
    gold_ingots_val: float,
    diamond_items_val: float,
    result: dict,
    price_iron_local: float,
    price_gold_local: float,
    price_diamond_local: float,
    key_prefix: str,
    iron_amount_orig: float = 0.0,
    iron_unit_orig: str = "ingot",
    gold_amount_orig: float = 0.0,
    gold_unit_orig: str = "ingot",
    diamond_amount_orig: float = 0.0,
    diamond_unit_orig: str = "ingot",
) -> None:
    st.markdown("---")
    st.subheader("💾 Save Deal")

    if st.session_state.is_read_only:
        st.info("🔒 Read-only mode — deals cannot be saved.")
        return

    col_log1, col_log2 = st.columns([1, 1])

    with col_log1:
        auto_status = result["status"]
        status_options = [
            f"Auto: {auto_status}",
            "ACCEPTED (PROFIT)",
            "ACCEPTED (BULK)",
            "REJECTED",
            "CUSTOM",
        ]
        selected_status = st.selectbox(
            "Deal Status",
            status_options,
            key=f"{key_prefix}_status_select",
        )

        if selected_status == f"Auto: {auto_status}":
            final_status = auto_status
        elif selected_status == "CUSTOM":
            final_status = st.text_input("Enter custom status:", key=f"{key_prefix}_custom_status")
            if not final_status.strip():
                final_status = auto_status
        else:
            final_status = selected_status

    with col_log2:
        manual_offer = st.number_input(
            "Offered Price ($) (override if needed)",
            min_value=0.0,
            step=0.5,
            value=result["offered_price"],
            key=f"{key_prefix}_manual_offer",
        )

    log_clicked = st.button(
        "💾 Log this deal to database",
        key=f"{key_prefix}_log_btn",
        use_container_width=True,
    )

    if log_clicked:
        _log_deal_with_all_fields(
            iron_ingots_val,
            gold_ingots_val,
            diamond_items_val,
            result["market_value"],
            manual_offer,
            final_status,
            price_iron_local,
            price_gold_local,
            price_diamond_local,
            iron_amount_orig,
            iron_unit_orig,
            gold_amount_orig,
            gold_unit_orig,
            diamond_amount_orig,
            diamond_unit_orig,
        )
        st.success(f"✅ Deal logged to database as '{final_status}'!")

    auto_sub = db.get_auto_subtract(company_id=company_id)
    if auto_sub:
        sub_result = db.subtract_from_stash(
            int(iron_ingots_val),
            int(gold_ingots_val),
            int(diamond_items_val),
            company_id=company_id,
        )
        st.info(f"📦 Auto-subtracted from stash: {_format_subtract_result(sub_result)}")
    else:
        col_sub1, _ = st.columns([1, 1])
        with col_sub1:
            subtract_choice = st.checkbox(
                "📦 Subtract these materials from stash?",
                value=False,
                key=f"{key_prefix}_subtract",
            )
        if subtract_choice:
            sub_result = db.subtract_from_stash(
                int(iron_ingots_val),
                int(gold_ingots_val),
                int(diamond_items_val),
                company_id=company_id,
            )
            st.info(f"✅ Subtracted from stash: {_format_subtract_result(sub_result)}")

    return final_status


# ── Page routing ──────────────────────────────────────────────────────────

if page == "🏢 Company Management":
    st.header("🏢 Company Management")
    if not st.session_state.is_admin:
        st.error("Access denied. Admin only.")
        st.stop()

    companies = db.list_all_companies()
    if not companies:
        st.info("No companies registered yet.")
        st.stop()

    admin_tabs = st.tabs(["📊 Dashboard", "👥 Company Detail", "⚙️ Operations"])

    # ────────────────────────────────────────────────────────────────
    # TAB 1: Dashboard
    # ────────────────────────────────────────────────────────────────
    with admin_tabs[0]:
        total = len(companies)
        active = sum(1 for c in companies if c.get("is_active"))
        premium = sum(1 for c in companies if c.get("tier") == "premium")
        trial = sum(1 for c in companies if c.get("trial_used"))
        expired = sum(1 for c in companies if c.get("access_expires_at") and c.get("is_active"))

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("🏢 Total", total)
        col2.metric("✅ Active", active)
        col3.metric("⭐ Premium", premium)
        col4.metric("🎁 Trial", trial)
        col5.metric("⏳ Active (expiring)", expired)

        st.markdown("---")
        st.subheader("📋 All Companies")

        # Enrich with deal stats and member count
        enriched = []
        for c in companies:
            stats = db.get_deal_stats(company_id=c["id"])
            members = db.get_company_members(c["id"])
            stash = db.load_stash(company_id=c["id"])
            total_iron, total_gold, total_diamond = (
                stash.get("iron_blocks", 0) * 9 + stash.get("iron_ingots", 0),
                stash.get("gold_blocks", 0) * 9 + stash.get("gold_ingots", 0),
                stash.get("diamond_blocks", 0) * 9 + stash.get("diamond_items", 0),
            )
            enriched.append(
                {
                    "ID": c["id"],
                    "Name": c.get("company_name", "") or f"Company #{c['id']}",
                    "Tier": c.get("tier", "free"),
                    "Members": len(members),
                    "Deals": stats.get("total_deals", 0),
                    "Profit": f"${stats.get('total_profit', 0):,.0f}",
                    "Stash Value": f"${((total_iron + total_gold + total_diamond) * 1.2):,.0f}"
                    if (total_iron + total_gold + total_diamond) > 0
                    else "$0",
                    "Active": "✅" if c.get("is_active") else "❌",
                    "Expires": c.get("access_expires_at", "Permanent"),
                }
            )

        df_compact = pd.DataFrame(enriched)
        st.dataframe(df_compact, use_container_width=True, hide_index=True)

    # ────────────────────────────────────────────────────────────────
    # TAB 2: Company Detail (members, invite, API key)
    # ────────────────────────────────────────────────────────────────
    with admin_tabs[1]:
        company_options = {f"#{c['id']} – {c.get('company_name', '') or 'Unnamed'}": c["id"] for c in companies}
        selected_label = st.selectbox(
            "Select a company to inspect:",
            list(company_options.keys()),
            key="admin_company_detail_select",
        )
        selected_company_id = company_options[selected_label]

        company_data = db.get_company_by_id(selected_company_id)
        if company_data:
            st.markdown("---")
            col_info1, col_info2, col_info3, col_info4 = st.columns(4)
            col_info1.metric("ID", company_data["id"])
            col_info2.metric("Name", company_data.get("company_name", "") or "—")
            col_info3.metric("Tier", company_data.get("tier", "free"))
            col_info4.metric("Active", "✅" if company_data.get("is_active") else "❌")

            col_inv, col_api = st.columns(2)

            with col_inv:
                st.subheader("🎟️ Invite Code")
                invite_code = company_data.get("invite_code", "")
                if invite_code:
                    st.code(invite_code, language="text")
                else:
                    st.info("No invite code set.")
                if st.button(
                    "🔄 Regenerate Invite Code",
                    key=f"admin_regen_invite_{selected_company_id}",
                    use_container_width=True,
                ):
                    new_code = db.generate_company_invite_code(selected_company_id)
                    if new_code:
                        st.success(f"✅ New invite code: `{new_code}`")
                        st.rerun()
                    else:
                        st.error("Failed to regenerate invite code.")

            with col_api:
                st.subheader("🔑 API Key")
                show_api = st.checkbox("Show API key", key=f"show_api_{selected_company_id}")
                if show_api:
                    st.code(company_data.get("api_key", ""), language="text")
                else:
                    st.code("••••••••••••••", language="text")
                if st.button(
                    "🔄 Regenerate API Key",
                    key=f"admin_regen_api_{selected_company_id}",
                    use_container_width=True,
                ):
                    new_key = db.regenerate_api_key(selected_company_id)
                    if new_key:
                        st.success(f"✅ New key: `{new_key}`")
                        st.rerun()
                    else:
                        st.error("Failed to regenerate key.")

            st.markdown("---")

            # ── Member list ──
            st.subheader("👥 Members")
            members = db.get_company_members(selected_company_id)

            for m in members:
                col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns([1, 2, 1.5, 1, 1.5, 1])
                avatar_url = m.get("discord_avatar", "") or ""
                if avatar_url:
                    col_m1.markdown(
                        f"<img src='{avatar_url}' width='28' height='28' style='border-radius:50%'>",
                        unsafe_allow_html=True,
                    )
                else:
                    col_m1.markdown("👤")
                col_m2.write(m.get("discord_username", "?"))
                role_badge = {
                    "owner": "🟢 Owner",
                    "admin": "🔵 Admin",
                    "member": "⚪ Member",
                }
                col_m3.write(role_badge.get(m["role"], m["role"]))
                col_m4.write(f"ID: {m['discord_id']}")

                # Notes
                notes = m.get("notes", "") or ""
                notes_key = f"notes_{m['id']}"
                current_notes = st.session_state.get(notes_key, notes)
                col_m5.text_area(
                    "Notes",
                    value=current_notes,
                    key=notes_key,
                    label_visibility="collapsed",
                    placeholder="Add notes...",
                )
                if current_notes != notes:
                    if db.update_member_notes(selected_company_id, m["id"], current_notes):
                        st.rerun()

                # Role change dropdown
                if m["role"] != "owner":
                    with col_m6:
                        new_role = st.selectbox(
                            "Role",
                            ["member", "admin"],
                            index=0 if m["role"] == "member" else 1,
                            key=f"role_{m['id']}",
                            label_visibility="collapsed",
                        )
                        if new_role != m["role"]:
                            if db.update_company_member_role(selected_company_id, m["id"], new_role):
                                st.rerun()

                # Remove button (only for non-owner)
                if m["role"] != "owner":
                    if st.button(
                        "🗑️ Remove",
                        key=f"remove_member_{m['id']}",
                        use_container_width=True,
                    ):
                        if db.remove_company_member(selected_company_id, m["id"]):
                            st.success(f"Removed {m['discord_username']}")
                            st.rerun()
                        else:
                            st.error("Failed to remove (last owner?)")

                # Transfer ownership button (only for owner)
                if m["role"] == "owner":
                    st.caption("🟢 **Owner** — cannot be removed or demoted directly")
                    # Show transfer ownership option
                    other_members = [x for x in members if x["id"] != m["id"]]
                    if other_members:
                        transfer_to = st.selectbox(
                            "Transfer ownership to:",
                            {f"{x['discord_username']} (ID: {x['id']})": x["id"] for x in other_members},
                            key=f"transfer_{selected_company_id}",
                        )
                        if st.button(
                            "🔄 Transfer Ownership",
                            key=f"transfer_btn_{selected_company_id}",
                            use_container_width=True,
                        ):
                            if db.transfer_ownership(selected_company_id, m["id"], transfer_to):
                                st.success("✅ Ownership transferred!")
                                st.rerun()
                            else:
                                st.error("Failed to transfer ownership.")

                st.markdown("---")

            # ── Add member form ──
            st.subheader("➕ Add Member")
            col_add1, col_add2, col_add3 = st.columns([2, 2, 1])
            with col_add1:
                add_discord_id = st.text_input(
                    "Discord ID (required)",
                    key=f"add_member_id_{selected_company_id}",
                    placeholder="e.g. 123456789012345678",
                )
            with col_add2:
                add_role = st.selectbox(
                    "Role",
                    ["member", "admin"],
                    key=f"add_member_role_{selected_company_id}",
                )
            with col_add3:
                st.markdown("##### &nbsp;")
                if st.button(
                    "➕ Add Member",
                    key=f"add_member_btn_{selected_company_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    if add_discord_id.strip():
                        # Try to resolve username from Discord API
                        from src.web.discord_oauth import get_username_by_discord_id

                        resolved_name = get_username_by_discord_id(add_discord_id.strip())
                        display_name = resolved_name or f"User #{add_discord_id.strip()}"
                        member = db.add_company_member(
                            selected_company_id,
                            add_discord_id.strip(),
                            display_name,
                            role=add_role,
                        )
                        if member:
                            st.success(f"✅ Added {display_name} as {add_role}!")
                            st.rerun()
                        else:
                            st.error("❌ Failed to add member (already a member or invalid ID).")
                    else:
                        st.warning("Please enter a Discord ID.")

            # ── Impersonation button ──
            st.markdown("---")
            st.subheader("🔍 Impersonate")
            if st.button(
                f"📂 View as company #{selected_company_id}",
                type="secondary",
                use_container_width=True,
                key=f"impersonate_{selected_company_id}",
            ):
                st.session_state.selected_admin_company = selected_company_id
                st.success(f"Now viewing company #{selected_company_id}.")
                st.rerun()
            if st.session_state.selected_admin_company is not None:
                if st.button("🔄 Back to my own data", use_container_width=True):
                    st.session_state.selected_admin_company = None
                    st.rerun()

    # ────────────────────────────────────────────────────────────────
    # TAB 3: Operations (extend, tier, deactivate, key regen)
    # ────────────────────────────────────────────────────────────────
    with admin_tabs[2]:
        op_options = {f"#{c['id']} – {c.get('company_name', '') or 'Unnamed'}": c["id"] for c in companies}

        st.subheader("⭐ Set Tier")
        col_op1, col_op2 = st.columns([2, 1])
        with col_op1:
            tier_target = st.selectbox(
                "Company:",
                list(op_options.keys()),
                key="op_tier_select",
            )
            tier_company_id = op_options[tier_target]
        with col_op2:
            target_co = db.get_company_by_id(tier_company_id)
            current_tier = target_co.get("tier", "free") if target_co else "free"
            new_tier = st.selectbox(
                "New tier:",
                ["free", "premium"],
                index=0 if current_tier == "free" else 1,
                key="op_tier_new",
            )
        if st.button("⭐ Set Tier", type="primary", use_container_width=True):
            if db.set_company_tier(tier_company_id, new_tier):
                st.success(f"✅ Company #{tier_company_id} tier set to '{new_tier}'!")
                st.rerun()
            else:
                st.error("Failed to set tier.")

        st.markdown("---")
        st.subheader("🕐 Extend Access")
        col_ext1, col_ext2 = st.columns([2, 1])
        with col_ext1:
            ext_target = st.selectbox(
                "Company:",
                list(op_options.keys()),
                key="op_ext_select",
            )
            ext_company_id = op_options[ext_target]
        with col_ext2:
            ext_days = st.number_input("Days:", min_value=1, step=1, value=30, key="op_ext_days")
        if st.button("➕ Extend", type="primary", use_container_width=True):
            if db.update_company_access(ext_company_id, ext_days):
                st.success(f"✅ Company #{ext_company_id} extended by {ext_days} days!")
                st.rerun()
            else:
                st.error("Failed to extend.")

        st.markdown("---")
        st.subheader("⛔ Deactivate / Reactivate")
        col_deact1, col_deact2 = st.columns([2, 1])
        with col_deact1:
            deact_target = st.selectbox(
                "Company:",
                list(op_options.keys()),
                key="op_deact_select",
            )
            deact_company_id = op_options[deact_target]
        with col_deact2:
            deact_co = db.get_company_by_id(deact_company_id)
            is_active = deact_co.get("is_active", 1) if deact_co else 1
            if is_active:
                if st.button("⛔ Deactivate", type="secondary", use_container_width=True):
                    if db.deactivate_company(deact_company_id):
                        st.success(f"✅ Company #{deact_company_id} deactivated!")
                        st.rerun()
                    else:
                        st.error("Failed to deactivate.")
            else:
                # Reactivate
                if st.button("✅ Reactivate", type="primary", use_container_width=True):
                    if db.update_company_access(deact_company_id, 0):
                        # Setting update_company_access will set expiry; instead directly
                        # We need reactivate function — use SQL update
                        st.error("Reactivate via Extend Access above (set days > 0).")

        st.markdown("---")
        st.subheader("🔑 Regenerate API Key")
        col_key1, col_key2 = st.columns([2, 1])
        with col_key1:
            key_target = st.selectbox(
                "Company:",
                list(op_options.keys()),
                key="op_key_select",
            )
            key_company_id = op_options[key_target]
        with col_key2:
            st.markdown("##### &nbsp;")
            if st.button("🔄 Regenerate", type="secondary", use_container_width=True):
                new_key = db.regenerate_api_key(key_company_id)
                if new_key:
                    st.success(f"✅ New API key for #{key_company_id}: `{new_key}`")
                else:
                    st.error("Failed to regenerate key.")
elif page == "💰 Deal Calculator":
    st.header("💰 Deal Calculator")
    st.markdown("Enter raw material amounts and their units.")

    load_from_stash = st.checkbox("📦 Load values from stash", value=False, key="deal_load_stash")
    stash = db.load_stash(company_id=company_id) if load_from_stash else None

    default_iron = 0.0
    default_gold = 0.0
    default_diamond = 0.0

    if stash and stash.get("updated_at") != "never":
        iron_i, gold_i, diamond_i = stash_ingot_equivalents(stash)
        default_iron = float(iron_i)
        default_gold = float(gold_i)
        default_diamond = float(diamond_i)
        if iron_i or gold_i or diamond_i:
            st.info(
                f"📦 Loaded from stash: "
                f"Iron: {MarketDeal.format_bulk_storage(iron_i)}, "
                f"Gold: {MarketDeal.format_bulk_storage(gold_i)}, "
                f"Diamonds: {MarketDeal.format_bulk_storage(diamond_i, is_diamond=True)}"
            )
        else:
            st.warning("⚠ Stash is empty. Enter values manually.")

    if "deal_iron_amount_orig" not in st.session_state:
        st.session_state.deal_iron_amount_orig = 0.0
    if "deal_iron_unit_orig" not in st.session_state:
        st.session_state.deal_iron_unit_orig = "ingot"
    if "deal_gold_amount_orig" not in st.session_state:
        st.session_state.deal_gold_amount_orig = 0.0
    if "deal_gold_unit_orig" not in st.session_state:
        st.session_state.deal_gold_unit_orig = "ingot"
    if "deal_diamond_amount_orig" not in st.session_state:
        st.session_state.deal_diamond_amount_orig = 0.0
    if "deal_diamond_unit_orig" not in st.session_state:
        st.session_state.deal_diamond_unit_orig = "ingot"

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("⬜ Iron")
        iron_amount = st.number_input("Iron amount", min_value=0.0, step=1.0, key="iron_amt", value=default_iron)
        iron_unit = st.selectbox("Iron unit", ["ingot", "block", "nugget"], key="iron_unit", index=0)

    with col2:
        st.subheader("🟨 Gold")
        gold_amount = st.number_input("Gold amount", min_value=0.0, step=1.0, key="gold_amt", value=default_gold)
        gold_unit = st.selectbox("Gold unit", ["ingot", "block", "nugget"], key="gold_unit", index=0)

    with col3:
        st.subheader("💎 Diamond")
        diamond_amount = st.number_input(
            "Diamond amount",
            min_value=0.0,
            step=1.0,
            key="diamond_amt",
            value=default_diamond,
        )
        diamond_unit = st.selectbox("Diamond unit", ["ingot", "block", "nugget"], key="diamond_unit", index=0)

    offered_price = st.number_input("💰 Offered price ($)", min_value=0.0, step=0.5, value=0.0, key="deal_offer")

    if "deal_result" not in st.session_state:
        st.session_state.deal_result = None

    if st.button("📊 Calculate Deal", type="primary", use_container_width=True, disabled=False):
        iron_ingots_val = MarketDeal.convert_to_ingots(iron_amount, iron_unit)
        gold_ingots_val = MarketDeal.convert_to_ingots(gold_amount, gold_unit)
        diamond_items_val = MarketDeal.convert_to_ingots(diamond_amount, diamond_unit)

        st.session_state.deal_iron_amount_orig = iron_amount
        st.session_state.deal_iron_unit_orig = iron_unit
        st.session_state.deal_gold_amount_orig = gold_amount
        st.session_state.deal_gold_unit_orig = gold_unit
        st.session_state.deal_diamond_amount_orig = diamond_amount
        st.session_state.deal_diamond_unit_orig = diamond_unit

        if iron_ingots_val == 0 and gold_ingots_val == 0 and diamond_items_val == 0:
            st.warning("Please enter at least some materials.")
            st.session_state.deal_result = None
        else:
            result = analyze_deal(
                iron_ingots_val,
                gold_ingots_val,
                diamond_items_val,
                price_iron,
                price_gold,
                price_diamond,
                offered_price=offered_price,
            )
            st.session_state.deal_result = {
                "iron_ingots": iron_ingots_val,
                "gold_ingots": gold_ingots_val,
                "diamond_items": diamond_items_val,
                "result": result,
                "price_iron": price_iron,
                "price_gold": price_gold,
                "price_diamond": price_diamond,
            }

    if st.session_state.deal_result is not None:
        d = st.session_state.deal_result
        iron_ingots_val = d["iron_ingots"]
        gold_ingots_val = d["gold_ingots"]
        diamond_items_val = d["diamond_items"]
        result = d["result"]

        st.markdown("---")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Market Value", f"${result['market_value']:.2f}")
        col_b.metric("Your Offer", f"${result['offered_price']:.2f}")
        col_c.metric(
            "Profit / Loss",
            f"${result['profit_loss']:.2f}",
            delta=f"${result['profit_loss']:.2f}",
        )

        st.markdown(f"### {result['status']}")
        st.markdown(f"**{result['status_msg']}**")
        st.markdown(f"Your offer is **{result['percent_of_market']:.1f}%** of market value.")
        st.markdown(
            f"Minimum acceptable ({MarketDeal.MIN_ACCEPTABLE_PERCENT * 100:.0f}%): **${result['min_needed_price']:.2f}**"
        )

        st.markdown("#### Logistics")
        st.write(f"~{result['stacks']:.1f} stacks ({result['shulkers']:.2f} shulker boxes)")
        if result["stacks"] > 0:
            st.write(
                f"${result['profit_loss'] / result['stacks']:.2f} per stack | ${result['profit_loss'] / result['shulkers']:.2f} per shulker"
            )

        if result.get("counter_offer"):
            st.markdown("#### 💡 Counter-Offer Suggestion")
            co = result["counter_offer"]
            iron_part = MarketDeal.format_bulk_storage(co["iron"]) if co.get("iron", 0) > 0 else "0"
            gold_part = MarketDeal.format_bulk_storage(co["gold"]) if co.get("gold", 0) > 0 else "0"
            diamond_part = (
                MarketDeal.format_bulk_storage(co["diamond"], is_diamond=True) if co.get("diamond", 0) > 0 else "0"
            )
            st.info(
                f"For ${result['offered_price']:.0f}, offer instead:\n- Iron: {iron_part}\n- Gold: {gold_part}\n- Diamonds: {diamond_part} (unchanged)"
            )

        _handle_deal_logging(
            iron_ingots_val,
            gold_ingots_val,
            diamond_items_val,
            result,
            price_iron,
            price_gold,
            price_diamond,
            "deal",
            iron_amount_orig=st.session_state.deal_iron_amount_orig,
            iron_unit_orig=st.session_state.deal_iron_unit_orig,
            gold_amount_orig=st.session_state.deal_gold_amount_orig,
            gold_unit_orig=st.session_state.deal_gold_unit_orig,
            diamond_amount_orig=st.session_state.deal_diamond_amount_orig,
            diamond_unit_orig=st.session_state.deal_diamond_unit_orig,
        )

elif page == "📦 Shulker Scanner":
    st.header("📦 Shulker Scanner")
    st.markdown("Enter materials as full stacks + remainder for blocks and items.")

    load_from_stash = st.checkbox("📦 Load values from stash", value=False, key="shulker_load_stash")
    stash = db.load_stash(company_id=company_id) if load_from_stash else None

    di_blocks_stacks_default = 0
    di_blocks_rest_default = 0
    di_items_stacks_default = 0
    di_items_rest_default = 0
    ir_blocks_stacks_default = 0
    ir_blocks_rest_default = 0
    ir_items_stacks_default = 0
    ir_items_rest_default = 0
    go_blocks_stacks_default = 0
    go_blocks_rest_default = 0
    go_items_stacks_default = 0
    go_items_rest_default = 0

    if stash and stash.get("updated_at") != "never":
        has_values = (
            stash.get("iron_blocks", 0) > 0
            or stash.get("iron_ingots", 0) > 0
            or stash.get("gold_blocks", 0) > 0
            or stash.get("gold_ingots", 0) > 0
            or stash.get("diamond_blocks", 0) > 0
            or stash.get("diamond_items", 0) > 0
        )
        if has_values:
            st.info(
                f"📦 Loaded from stash: "
                f"Iron: {stash['iron_blocks']} blocks + {stash['iron_ingots']} ingots, "
                f"Gold: {stash['gold_blocks']} blocks + {stash['gold_ingots']} ingots, "
                f"Diamonds: {stash['diamond_blocks']} blocks + {stash['diamond_items']} items"
            )
            di_blocks_stacks_default = stash["diamond_blocks"] // 64
            di_blocks_rest_default = stash["diamond_blocks"] % 64
            di_items_stacks_default = stash["diamond_items"] // 64
            di_items_rest_default = stash["diamond_items"] % 64
            ir_blocks_stacks_default = stash["iron_blocks"] // 64
            ir_blocks_rest_default = stash["iron_blocks"] % 64
            ir_items_stacks_default = stash["iron_ingots"] // 64
            ir_items_rest_default = stash["iron_ingots"] % 64
            go_blocks_stacks_default = stash["gold_blocks"] // 64
            go_blocks_rest_default = stash["gold_blocks"] % 64
            go_items_stacks_default = stash["gold_ingots"] // 64
            go_items_rest_default = stash["gold_ingots"] % 64
        else:
            st.warning("⚠ Stash is empty. Enter values manually.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("💎 Diamond")
        di_blocks_stacks = st.number_input(
            "Full stacks DIAMOND BLOCKS",
            min_value=0,
            step=1,
            key="di_b_s",
            value=di_blocks_stacks_default,
        )
        di_blocks_rest = st.number_input(
            "Remainder DIAMOND BLOCKS (0-63)",
            min_value=0,
            max_value=63,
            step=1,
            key="di_b_r",
            value=di_blocks_rest_default,
        )
        di_items_stacks = st.number_input(
            "Full stacks DIAMOND ITEMS",
            min_value=0,
            step=1,
            key="di_i_s",
            value=di_items_stacks_default,
        )
        di_items_rest = st.number_input(
            "Remainder DIAMOND ITEMS (0-63)",
            min_value=0,
            max_value=63,
            step=1,
            key="di_i_r",
            value=di_items_rest_default,
        )
        total_diamond = (di_blocks_stacks * 64 + di_blocks_rest) * 9 + (di_items_stacks * 64 + di_items_rest)

    with col2:
        st.subheader("⬜ Iron")
        ir_blocks_stacks = st.number_input(
            "Full stacks IRON BLOCKS",
            min_value=0,
            step=1,
            key="ir_b_s",
            value=ir_blocks_stacks_default,
        )
        ir_blocks_rest = st.number_input(
            "Remainder IRON BLOCKS (0-63)",
            min_value=0,
            max_value=63,
            step=1,
            key="ir_b_r",
            value=ir_blocks_rest_default,
        )
        ir_items_stacks = st.number_input(
            "Full stacks IRON ITEMS",
            min_value=0,
            step=1,
            key="ir_i_s",
            value=ir_items_stacks_default,
        )
        ir_items_rest = st.number_input(
            "Remainder IRON ITEMS (0-63)",
            min_value=0,
            max_value=63,
            step=1,
            key="ir_i_r",
            value=ir_items_rest_default,
        )
        total_iron = (ir_blocks_stacks * 64 + ir_blocks_rest) * 9 + (ir_items_stacks * 64 + ir_items_rest)

    with col3:
        st.subheader("🟨 Gold")
        go_blocks_stacks = st.number_input(
            "Full stacks GOLD BLOCKS",
            min_value=0,
            step=1,
            key="go_b_s",
            value=go_blocks_stacks_default,
        )
        go_blocks_rest = st.number_input(
            "Remainder GOLD BLOCKS (0-63)",
            min_value=0,
            max_value=63,
            step=1,
            key="go_b_r",
            value=go_blocks_rest_default,
        )
        go_items_stacks = st.number_input(
            "Full stacks GOLD ITEMS",
            min_value=0,
            step=1,
            key="go_i_s",
            value=go_items_stacks_default,
        )
        go_items_rest = st.number_input(
            "Remainder GOLD ITEMS (0-63)",
            min_value=0,
            max_value=63,
            step=1,
            key="go_i_r",
            value=go_items_rest_default,
        )
        total_gold = (go_blocks_stacks * 64 + go_blocks_rest) * 9 + (go_items_stacks * 64 + go_items_rest)

    multiplier = st.number_input("Multiplier", min_value=1, step=1, value=1)
    offered_price = st.number_input("💰 Offered price ($)", min_value=0.0, step=0.5, value=0.0, key="shulker_offer")

    if "shulker_result" not in st.session_state:
        st.session_state.shulker_result = None

    if st.button("📊 Scan Shulker", type="primary", use_container_width=True):
        iron_ingots_val = total_iron * multiplier
        gold_ingots_val = total_gold * multiplier
        diamond_items_val = total_diamond * multiplier

        if iron_ingots_val == 0 and gold_ingots_val == 0 and diamond_items_val == 0:
            st.warning("Please enter at least some materials.")
            st.session_state.shulker_result = None
        else:
            result = analyze_deal(
                iron_ingots_val,
                gold_ingots_val,
                diamond_items_val,
                price_iron,
                price_gold,
                price_diamond,
                offered_price=offered_price,
            )
            st.session_state.shulker_result = {
                "iron_ingots": iron_ingots_val,
                "gold_ingots": gold_ingots_val,
                "diamond_items": diamond_items_val,
                "result": result,
                "price_iron": price_iron,
                "price_gold": price_gold,
                "price_diamond": price_diamond,
            }

    if st.session_state.shulker_result is not None:
        d = st.session_state.shulker_result
        iron_ingots_val = d["iron_ingots"]
        gold_ingots_val = d["gold_ingots"]
        diamond_items_val = d["diamond_items"]
        result = d["result"]

        st.markdown("---")
        st.write(f"Iron: {MarketDeal.format_bulk_storage(iron_ingots_val)}")
        st.write(f"Gold: {MarketDeal.format_bulk_storage(gold_ingots_val)}")
        st.write(f"Diamonds: {MarketDeal.format_bulk_storage(diamond_items_val, is_diamond=True)}")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Market Value", f"${result['market_value']:.2f}")
        col_b.metric("Your Offer", f"${result['offered_price']:.2f}")
        col_c.metric(
            "Profit / Loss",
            f"${result['profit_loss']:.2f}",
            delta=f"${result['profit_loss']:.2f}",
        )

        st.markdown(f"### {result['status']}")
        st.markdown(f"**{result['status_msg']}**")
        st.markdown("#### Logistics")
        st.write(f"~{result['stacks']:.1f} stacks ({result['shulkers']:.2f} shulker boxes)")

        if result.get("counter_offer"):
            st.markdown("#### 💡 Counter-Offer")
            co = result["counter_offer"]
            iron_part = MarketDeal.format_bulk_storage(co["iron"]) if co.get("iron", 0) > 0 else "0"
            gold_part = MarketDeal.format_bulk_storage(co["gold"]) if co.get("gold", 0) > 0 else "0"
            diamond_part = (
                MarketDeal.format_bulk_storage(co["diamond"], is_diamond=True) if co.get("diamond", 0) > 0 else "0"
            )
            st.info(
                f"For ${result['offered_price']:.0f}, offer instead:\n- Iron: {iron_part}\n- Gold: {gold_part}\n- Diamonds: {diamond_part}"
            )

        _handle_deal_logging(
            iron_ingots_val,
            gold_ingots_val,
            diamond_items_val,
            result,
            price_iron,
            price_gold,
            price_diamond,
            "shulker",
        )

elif page == "⚡ Quick Converter":
    st.header("⚡ Quick Converter")
    base_amount = st.number_input("Amount per load", min_value=1, step=100, value=1500)
    multiplier = st.number_input("Multiplier", min_value=1, step=1, value=1)

    if st.button("🔄 Convert", type="primary", use_container_width=True):
        amount = base_amount * multiplier
        blocks = amount // _settings.INGOTS_PER_BLOCK
        rest_ingots = amount % _settings.INGOTS_PER_BLOCK
        stacks = amount // _settings.ITEMS_PER_STACK
        rest_items = amount % _settings.ITEMS_PER_STACK
        shulkers = amount / _settings.ITEMS_PER_SHULKER
        iron_value = amount * price_iron
        gold_value = amount * price_gold
        diamond_value = amount * price_diamond

        st.markdown("---")
        st.write(f"**Total**: {amount} items ({base_amount} × {multiplier})")
        st.write(f"**As blocks**: {blocks} blocks + {rest_ingots} ingots")
        st.write(f"**As stacks**: {stacks} stacks + {rest_items} items")
        st.write(f"**In shulkers**: ~{shulkers:.2f} shulker boxes")
        st.markdown("#### Estimated market value")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Iron", f"${iron_value:,.2f}")
        col_b.metric("Gold", f"${gold_value:,.2f}")
        col_c.metric("Diamond", f"${diamond_value:,.2f}")

elif page == "📊 Deal History":
    st.header("📊 Deal History")

    stats = db.get_deal_stats(company_id=company_id)
    deals = db.get_all_deals(limit=200, company_id=company_id)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Deals", stats["total_deals"])
    col2.metric("Accepted", stats["accepted"])
    col3.metric("Rejected", stats["rejected"])
    col4.metric("Total Profit", f"${stats['total_profit']:,.2f}")
    col5.metric("Avg Profit/Deal", f"${stats['avg_profit']:,.2f}")
    col6.metric("Total Market Value", f"${stats['total_market_value']:,.2f}")

    if deals:
        df = pd.DataFrame(deals)
        df_chart = df.copy()
        df_chart["Date/Time"] = pd.to_datetime(df_chart["timestamp"])
        df_chart = df_chart.sort_values("Date/Time").reset_index(drop=True)
        df_chart["Deal #"] = range(1, len(df_chart) + 1)

        st.subheader("📈 Profit Trends")
        chart_data = df_chart[["Deal #", "profit"]].rename(columns={"profit": "Profit ($)"})
        st.line_chart(chart_data.set_index("Deal #"))

        st.subheader("📋 All Deals")
        df_display = df.drop(
            columns=[
                "id",
                "company_id",
                "iron_amount",
                "iron_unit",
                "gold_amount",
                "gold_unit",
                "diamond_amount",
                "diamond_unit",
            ],
            errors="ignore",
        )
        df_display = df_display.rename(
            columns={
                "timestamp": "Date/Time",
                "iron_ingots": "Iron",
                "gold_ingots": "Gold",
                "diamond_items": "Diamonds",
                "market_value": "Market Value",
                "offered_price": "Offered",
                "status": "Status",
                "profit": "Profit",
            }
        )
        df_display["Date/Time"] = pd.to_datetime(df_display["Date/Time"])
        df_display = df_display.sort_values("Date/Time", ascending=False)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        csv = df_display.to_csv(index=False).encode("utf-8")
        st.download_button("⬇ Download CSV", csv, "dc_trade_deals.csv", "text/csv")

        if not st.session_state.is_read_only:
            st.markdown("---")
            st.subheader("✏️ Edit or Delete a Deal")
            deal_options = {f"#{d['id']} – {d['status']} ({d['timestamp']})": d["id"] for d in deals[:50]}
            selected_label = st.selectbox(
                "Select a deal to edit:",
                list(deal_options.keys()),
                key="deal_edit_select",
            )
            selected_id = deal_options[selected_label]
            selected_deal = next((d for d in deals if d["id"] == selected_id), None)
            if selected_deal:
                col_edit1, col_edit2, col_edit3 = st.columns([2, 2, 1])
                with col_edit1:
                    new_status = st.text_input(
                        "New status:",
                        value=selected_deal["status"],
                        key="deal_edit_status",
                    )
                with col_edit2:
                    new_offer = st.number_input(
                        "New offered price ($):",
                        min_value=0.0,
                        step=0.5,
                        value=float(selected_deal["offered_price"]),
                        key="deal_edit_offer",
                    )
                with col_edit3:
                    st.markdown("##### &nbsp;")
                    if st.button(
                        "💾 Update Deal",
                        key="deal_edit_update",
                        use_container_width=True,
                    ):
                        if db.update_deal(selected_id, new_status, new_offer, company_id=company_id):
                            st.success(f"✅ Deal #{selected_id} updated!")
                            st.rerun()
                        else:
                            st.error("❌ Failed to update deal.")

                if st.button("🗑️ Delete Deal", key=f"deal_delete_{selected_id}", type="secondary"):
                    if db.delete_deal(selected_id, company_id=company_id):
                        st.success(f"✅ Deal #{selected_id} deleted!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete deal.")
    else:
        st.info("No deals logged yet. Use one of the calculators above!")

elif page == "📦 Stash Manager":
    st.header("📦 Stash Manager")
    stash = db.load_stash(company_id=company_id)

    total_iron, total_gold, total_diamond = stash_ingot_equivalents(stash)

    iron_value = total_iron * price_iron
    gold_value = total_gold * price_gold
    diamond_value = total_diamond * price_diamond
    total_value = iron_value + gold_value + diamond_value

    stacks, shulkers = total_stash_shipping(stash)

    st.subheader("📦 Current Stash")
    last_updated = stash.get("updated_at", "never")
    st.caption(f"Last updated: {last_updated}")

    raw_iron_str = f" (+{stash.get('raw_iron_blocks', 0)} raw)" if stash.get("raw_iron_blocks", 0) else ""
    raw_gold_str = f" (+{stash.get('raw_gold_blocks', 0)} raw)" if stash.get("raw_gold_blocks", 0) else ""
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Iron",
        f"{stash['iron_blocks']} blocks{raw_iron_str} + {stash['iron_ingots']} ingots",
        f"{MarketDeal.format_bulk_storage(total_iron)}",
    )
    col2.metric(
        "Gold",
        f"{stash['gold_blocks']} blocks{raw_gold_str} + {stash['gold_ingots']} ingots",
        f"{MarketDeal.format_bulk_storage(total_gold)}",
    )
    col3.metric(
        "Diamonds",
        f"{stash['diamond_blocks']} blocks + {stash['diamond_items']} items",
        f"{MarketDeal.format_bulk_storage(total_diamond, is_diamond=True)}",
    )

    st.markdown("---")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Total Market Value", f"${total_value:,.2f}")
    col_b.metric("Iron Value", f"${iron_value:,.2f}")
    col_c.metric("Gold Value", f"${gold_value:,.2f}")
    col_d.metric("Diamond Value", f"${diamond_value:,.2f}")
    st.caption(f"🚚 Shipping: ~{stacks:.1f} stacks (~{shulkers:.2f} shulker boxes)")

    st.markdown("---")
    st.subheader("🔗 Public Stash Link")
    _company = db.get_company_by_id(company_id)
    public_token = (_company or {}).get("public_stash_token", "")
    if public_token:
        base_url = _settings.PUBLIC_BASE_URL
        if base_url:
            public_url = f"{base_url.rstrip('/')}/stash/public/{public_token}"
        else:
            api_host = os.getenv("API_HOST", "localhost")
            api_port = os.getenv("API_PORT", "8000")
            public_url = f"http://{api_host}:{api_port}/stash/public/{public_token}"
            st.warning(
                "⚠️ **PUBLIC_BASE_URL** is not set. The link below may not be "
                "reachable from outside this container. "
                "Set `PUBLIC_BASE_URL` in your `.env` file to the externally-reachable "
                "base URL (e.g. `PUBLIC_BASE_URL=https://fishy.business`)."
            )
        st.success("✅ Public stash is enabled!")
        st.code(public_url, language="text")
        st.caption("Share this URL with customers. No API key needed.")
        read_only = st.session_state.is_read_only
        if st.button("🔄 Regenerate Token", disabled=read_only):
            new_token = db.generate_public_stash_token(company_id)
            if new_token:
                st.success("🆕 New public stash token generated!")
                st.rerun()
    else:
        st.info("🔒 No public stash link — customers need an API key to view your stash.")
        read_only = st.session_state.is_read_only
        if st.button("🔓 Enable Public Stash Link", disabled=read_only):
            new_token = db.generate_public_stash_token(company_id)
            if new_token:
                st.success("✅ Public stash link enabled!")
                st.rerun()

    st.markdown("---")

    read_only = st.session_state.is_read_only
    if read_only:
        st.info("🔒 Read-only mode — stash modifications are disabled.")

    st.subheader("✏️ Update Stash")

    auto_sub = bool(stash.get("auto_subtract", 0))
    col_toggle1, col_toggle2 = st.columns([1, 3])
    with col_toggle1:
        new_auto_sub = st.checkbox(
            "🔁 Auto-subtract",
            value=auto_sub,
            help="When enabled, materials are automatically subtracted from stash after every deal.",
            disabled=read_only,
        )
    with col_toggle2:
        st.caption("When enabled, deal materials are automatically deducted from stash without asking.")
    if new_auto_sub != auto_sub and not read_only:
        db.set_auto_subtract(new_auto_sub, company_id=company_id)
        st.success(f"Auto-subtract is now {'ON' if new_auto_sub else 'OFF'}!")
        st.rerun()

    st.markdown("---")

    with st.form("stash_form"):
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            iron_blocks = st.number_input(
                "Iron blocks",
                min_value=0,
                step=1,
                value=int(stash.get("iron_blocks", 0)),
            )
            raw_iron_blocks = st.number_input(
                "Raw iron blocks",
                min_value=0,
                step=1,
                value=int(stash.get("raw_iron_blocks", 0)),
            )
            gold_blocks = st.number_input(
                "Gold blocks",
                min_value=0,
                step=1,
                value=int(stash.get("gold_blocks", 0)),
            )
            raw_gold_blocks = st.number_input(
                "Raw gold blocks",
                min_value=0,
                step=1,
                value=int(stash.get("raw_gold_blocks", 0)),
            )
            diamond_blocks = st.number_input(
                "Diamond blocks",
                min_value=0,
                step=1,
                value=int(stash.get("diamond_blocks", 0)),
            )
        with col_i2:
            iron_ingots = st.number_input(
                "Iron ingots",
                min_value=0,
                step=1,
                value=int(stash.get("iron_ingots", 0)),
            )
            gold_ingots = st.number_input(
                "Gold ingots",
                min_value=0,
                step=1,
                value=int(stash.get("gold_ingots", 0)),
            )
            diamond_items = st.number_input(
                "Diamond items",
                min_value=0,
                step=1,
                value=int(stash.get("diamond_items", 0)),
            )

        submitted = st.form_submit_button(
            "💾 Save Stash",
            type="primary",
            use_container_width=True,
            disabled=read_only,
        )

    if submitted and not read_only:
        new_stash = {
            "iron_blocks": iron_blocks,
            "raw_iron_blocks": raw_iron_blocks,
            "iron_ingots": iron_ingots,
            "gold_blocks": gold_blocks,
            "raw_gold_blocks": raw_gold_blocks,
            "gold_ingots": gold_ingots,
            "diamond_blocks": diamond_blocks,
            "diamond_items": diamond_items,
            "auto_subtract": 1 if new_auto_sub else 0,
        }
        db.save_stash(new_stash, company_id=company_id)
        st.success("✅ Stash saved!")
        st.rerun()

    st.markdown("---")
    st.subheader("➕ Add Materials to Stash")
    with st.form("add_stash_form"):
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            add_iron_blocks = st.number_input("Iron blocks to add", min_value=0, step=1, value=0)
            add_gold_blocks = st.number_input("Gold blocks to add", min_value=0, step=1, value=0)
            add_diamond_blocks = st.number_input("Diamond blocks to add", min_value=0, step=1, value=0)
        with col_i2:
            add_iron_ingots = st.number_input("Iron ingots to add", min_value=0, step=1, value=0)
            add_gold_ingots = st.number_input("Gold ingots to add", min_value=0, step=1, value=0)
            add_diamond_items = st.number_input("Diamond items to add", min_value=0, step=1, value=0)

        add_submitted = st.form_submit_button(
            "➕ Add to Stash",
            type="secondary",
            use_container_width=True,
            disabled=read_only,
        )

    if add_submitted and not read_only:
        has_values = any(
            [
                add_iron_blocks,
                add_iron_ingots,
                add_gold_blocks,
                add_gold_ingots,
                add_diamond_blocks,
                add_diamond_items,
            ]
        )
        if has_values:
            db.add_to_stash(
                iron_blocks=add_iron_blocks,
                iron_ingots=add_iron_ingots,
                gold_blocks=add_gold_blocks,
                gold_ingots=add_gold_ingots,
                diamond_blocks=add_diamond_blocks,
                diamond_items=add_diamond_items,
                company_id=company_id,
            )
            st.success("✅ Materials added to stash!")
            st.rerun()
        else:
            st.warning("⚠ Please enter at least one value to add.")

    st.markdown("---")

    if st.button("🗑️ Clear Stash", type="secondary", use_container_width=True, disabled=read_only):
        if stash and (
            stash.get("iron_blocks")
            or stash.get("iron_ingots")
            or stash.get("gold_blocks")
            or stash.get("gold_ingots")
            or stash.get("diamond_blocks")
            or stash.get("diamond_items")
            or stash.get("raw_iron_blocks", 0)
            or stash.get("raw_gold_blocks", 0)
        ):
            st.warning("Are you sure?")
            col_confirm1, col_confirm2 = st.columns(2)
            with col_confirm1:
                if st.button("Yes, clear it", type="primary"):
                    db.clear_stash(company_id=company_id)
                    st.success("✅ Stash cleared!")
                    st.rerun()
            with col_confirm2:
                if st.button("No, cancel"):
                    st.rerun()
        else:
            st.info("Stash is already empty.")

    st.markdown("---")
    st.subheader("📋 Import from Item List")
    st.markdown(
        "Paste a raw item dump (e.g. from the game's storage interface) below. "
        "Only recognised items will be imported. **This replaces the entire stash.**"
    )
    import_text = st.text_area("Paste item list here", height=200, key="import_text")
    if st.button(
        "📥 Import & Replace Stash",
        type="primary",
        use_container_width=True,
        disabled=read_only,
    ):
        if not import_text.strip():
            st.warning("⚠ Please paste an item list first.")
        else:
            updated_stash, recognised, skipped = db.import_items_to_stash(import_text, company_id=company_id)
            skipped_count = len(skipped)
            detected_parts = []
            if updated_stash.get("raw_iron_blocks"):
                detected_parts.append(f"{updated_stash['raw_iron_blocks']} raw iron blocks")
            if updated_stash.get("iron_blocks"):
                detected_parts.append(f"{updated_stash['iron_blocks']} iron blocks")
            if updated_stash.get("iron_ingots"):
                detected_parts.append(f"{updated_stash['iron_ingots']} iron ingots")
            if updated_stash.get("raw_gold_blocks"):
                detected_parts.append(f"{updated_stash['raw_gold_blocks']} raw gold blocks")
            if updated_stash.get("gold_blocks"):
                detected_parts.append(f"{updated_stash['gold_blocks']} gold blocks")
            if updated_stash.get("gold_ingots"):
                detected_parts.append(f"{updated_stash['gold_ingots']} gold ingots")
            if updated_stash.get("diamond_blocks"):
                detected_parts.append(f"{updated_stash['diamond_blocks']} diamond blocks")
            if updated_stash.get("diamond_items"):
                detected_parts.append(f"{updated_stash['diamond_items']} diamonds")
            if detected_parts:
                st.success(f"✅ Stash updated! Detected: {', '.join(detected_parts)}.")
            else:
                st.warning("⚠ No recognised items found in the list.")
            if skipped_count > 0:
                with st.expander(f"ℹ️ {skipped_count} item(s) were skipped (not tracked)"):
                    for line in skipped:
                        st.text(line)
            st.rerun()

elif page == "📋 Deal Templates":
    st.header("📋 Deal Templates")

    if st.session_state.is_read_only:
        st.info("🔒 Read-only mode — templates cannot be saved or modified.")

    templates = db.load_templates(company_id=company_id)

    st.subheader("💾 Save Current Deal as Template")
    with st.form("save_template_form"):
        col_t1, col_t2, col_t3, col_t4, col_t5 = st.columns(5)
        with col_t1:
            template_name = st.text_input("Template name:", placeholder="e.g. 40 Iron 40 Gold")
        with col_t2:
            t_iron = st.number_input("Iron (ingots)", min_value=0.0, step=1.0, value=0.0)
        with col_t3:
            t_gold = st.number_input("Gold (ingots)", min_value=0.0, step=1.0, value=0.0)
        with col_t4:
            t_diamond = st.number_input("Diamonds (items)", min_value=0.0, step=1.0, value=0.0)
        with col_t5:
            t_offer = st.number_input("Offered price ($)", min_value=0.0, step=0.5, value=0.0)
        save_template_clicked = st.form_submit_button(
            "💾 Save Template",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.is_read_only,
        )

    if save_template_clicked:
        if template_name.strip():
            if db.save_template(
                template_name.strip(),
                t_iron,
                t_gold,
                t_diamond,
                t_offer,
                company_id=company_id,
            ):
                st.success(f"✅ Template '{template_name}' saved!")
                st.rerun()
        else:
            st.warning("⚠ Please enter a template name.")

    if templates:
        st.subheader("📋 Saved Templates")
        for tmpl in templates:
            col_t1, col_t2, col_t3, col_t4, col_t5, col_t6 = st.columns([2, 1, 1, 1, 1, 1])
            with col_t1:
                st.write(f"**{tmpl['name']}**")
            with col_t2:
                st.write(f"Fe: {tmpl['iron_ingots']:.0f}")
            with col_t3:
                st.write(f"Au: {tmpl['gold_ingots']:.0f}")
            with col_t4:
                st.write(f"Di: {tmpl['diamond_items']:.0f}")
            with col_t5:
                st.write(f"${tmpl['offered_price']:.2f}")
            with col_t6:
                if st.button(
                    "📥 Load",
                    key=f"load_tmpl_{tmpl['name']}_{tmpl['company_id']}",
                    use_container_width=True,
                ):
                    st.session_state.template_load = tmpl
                    st.success(f"✅ Template '{tmpl['name']}' loaded! Go to Deal Calculator.")
                    st.rerun()
                if not st.session_state.is_read_only:
                    if st.button("🗑️", key=f"del_tmpl_{tmpl['name']}_{tmpl['company_id']}"):
                        db.delete_template(tmpl["name"], company_id=company_id)
                        st.rerun()

        if st.session_state.template_load:
            tmpl = st.session_state.template_load
            st.info(
                f"📥 **Loaded template:** {tmpl['name']} – Iron: {tmpl['iron_ingots']:.0f}, Gold: {tmpl['gold_ingots']:.0f}, Diamonds: {tmpl['diamond_items']:.0f}, Offer: ${tmpl['offered_price']:.2f}"
            )
            if st.button("🧹 Clear loaded template"):
                st.session_state.template_load = None
                st.rerun()
    else:
        st.info("No templates saved yet. Create one above!")

elif page == "🔍 Item Lookup":
    st.header("🔍 Item Lookup")
    st.markdown("Look up any item from the DemocracyCraft economy API and run a deal analysis.")

    col_search, col_btn = st.columns([4, 1])
    with col_search:
        item_name = st.text_input(
            "Item name",
            placeholder="e.g. Saddle, Netherite Ingot",
            key="item_lookup_name",
        )
    with col_btn:
        st.markdown("##### &nbsp;")
        lookup_clicked = st.button("🔍 Lookup", type="primary", use_container_width=True)

    if lookup_clicked and item_name.strip():
        with st.spinner(f"⏳ Looking up '{item_name}' …"):
            cache = MarketDeal.load_cache()
            info_val = MarketDeal.lookup_item(item_name.strip(), cache)
            MarketDeal.save_cache(cache)
            st.session_state._lookup_info = info_val

        if info_val.get("error"):
            st.error(f"❌ {info_val['error']}")
        elif info_val.get("cached"):
            st.info("📦 Results from cache — cached price shown below.")
            st.metric("Avg. Unit Price", f"${info_val['avg_unit_price']:.2f}")
        else:
            st.success("✅ Item found!")
            col_i1, col_i2, col_i3, col_i4 = st.columns(4)
            avg_price = info_val.get("avg_unit_price")
            col_i1.metric("💰 Avg. Unit Price", f"${avg_price:.2f}" if avg_price else "N/A")
            col_i2.metric("🏪 Active Shops", info_val.get("shop_count", 0))
            col_i3.metric(
                "📉 Min Price",
                f"${info_val['min_price']:.2f}" if info_val.get("min_price") else "N/A",
            )
            col_i4.metric(
                "📈 Max Price",
                f"${info_val['max_price']:.2f}" if info_val.get("max_price") else "N/A",
            )
            col_trades = st.columns([1])
            col_trades[0].metric("📊 Total Trades (30d)", info_val.get("total_trades", 0))
            if info_val.get("cheapest_shops"):
                with st.expander("🏪 Cheapest Shops", expanded=False):
                    shop_rows = []
                    for s in info_val["cheapest_shops"]:
                        shop_rows.append(
                            {
                                "Shop": s.get("shopName", "?"),
                                "Buy Price": f"${float(s['buyPrice']):.2f}" if s.get("buyPrice") else "?",
                                "Sell Price": f"${float(s['sellPrice']):.2f}" if s.get("sellPrice") else "?",
                                "Stock": s.get("stock", "?"),
                            }
                        )
                    st.table(shop_rows)
            st.markdown("---")
            st.subheader("💼 Deal Analysis")

    info_val = st.session_state.get("_lookup_info")
    item_name = st.session_state.get("item_lookup_name", "")

    if info_val and info_val.get("avg_unit_price"):
        avg_price = info_val["avg_unit_price"]

        if "item_lookup_qty" not in st.session_state:
            st.session_state.item_lookup_qty = 1
        if "item_lookup_offer" not in st.session_state:
            st.session_state.item_lookup_offer = 0.0

        col_q, col_o = st.columns(2)
        with col_q:
            quantity = st.number_input(
                f"Quantity ({item_name})",
                min_value=1,
                step=1,
                key="item_lookup_qty_input",
            )
        with col_o:
            offered_price_input = st.number_input(
                "💰 Offered Price ($)",
                min_value=0.0,
                step=0.5,
                key="item_lookup_offer_input",
            )

        if st.button(
            "📊 Calculate",
            type="primary",
            use_container_width=True,
            key="item_lookup_calc",
        ):
            total_value = quantity * avg_price
            profit = offered_price_input - total_value
            min_acceptable = total_value * MarketDeal.MIN_ACCEPTABLE_PERCENT

            if offered_price_input >= total_value:
                status = "ACCEPTED (PROFIT)"
                status_msg = f"✅ +${profit:.2f} profit over market value (${total_value:.2f})."
            elif offered_price_input >= min_acceptable:
                status = "ACCEPTED (BULK)"
                status_msg = f"🟡 OK! Within bulk discount (${abs(profit):.2f} discount from ${total_value:.2f})."
            else:
                status = "REJECTED"
                status_msg = f"❌ Too cheap! Need ${min_acceptable - offered_price_input:.2f} more."

            st.session_state.item_lookup_result = {
                "item_name": item_name,
                "quantity": quantity,
                "unit_price": avg_price,
                "total_value": total_value,
                "offered_price": offered_price_input,
                "status": status,
                "status_msg": status_msg,
                "profit": profit,
                "min_acceptable": min_acceptable,
            }

        if "item_lookup_result" in st.session_state and st.session_state.item_lookup_result:
            r = st.session_state.item_lookup_result
            st.markdown("---")
            col_r1, col_r2, col_r3 = st.columns(3)
            col_r1.metric("Market Value", f"${r['total_value']:.2f}")
            col_r2.metric("Your Offer", f"${r['offered_price']:.2f}")
            col_r3.metric("Profit / Loss", f"${r['profit']:.2f}", delta=f"${r['profit']:.2f}")
            st.markdown(f"### {r['status']}")
            st.markdown(f"**{r['status_msg']}**")

            if not st.session_state.is_read_only:
                st.markdown("---")
                st.subheader("💾 Save Deal")

                col_log1, col_log2 = st.columns([1, 1])
                with col_log1:
                    auto_status = r["status"]
                    status_options = [
                        f"Auto: {auto_status}",
                        "ACCEPTED (PROFIT)",
                        "ACCEPTED (BULK)",
                        "REJECTED",
                        "CUSTOM",
                    ]
                    selected_status = st.selectbox("Deal Status", status_options, key="item_lookup_status_select")
                    if selected_status == f"Auto: {auto_status}":
                        final_status = auto_status
                    elif selected_status == "CUSTOM":
                        final_status = st.text_input("Enter custom status:", key="item_lookup_custom_status")
                        if not final_status.strip():
                            final_status = auto_status
                    else:
                        final_status = selected_status

                with col_log2:
                    manual_offer = st.number_input(
                        "Offered Price ($) (override)",
                        min_value=0.0,
                        step=0.5,
                        value=r["offered_price"],
                        key="item_lookup_manual_offer",
                    )

                if st.button(
                    "💾 Log this deal to database",
                    key="item_lookup_log",
                    use_container_width=True,
                ):
                    calc_profit = manual_offer - r["total_value"]
                    db.log_item_deal(
                        item_name=r["item_name"],
                        quantity=r["quantity"],
                        unit_price=r["unit_price"],
                        total_value=r["total_value"],
                        offered_price=manual_offer,
                        status=final_status,
                        profit=calc_profit,
                        company_id=company_id,
                    )
                    st.success(f"✅ Item lookup deal logged to database as '{final_status}'!")
            else:
                st.info("🔒 Read-only mode — deals cannot be saved.")

    # Lookup Deal History
    st.markdown("---")
    st.subheader("📋 Lookup Deal History")
    lookup_deals = db.get_item_lookup_deals(limit=50, company_id=company_id)
    if lookup_deals:
        df_lookup = pd.DataFrame(lookup_deals)
        df_lookup["Date/Time"] = pd.to_datetime(df_lookup["timestamp"])
        df_lookup = df_lookup.sort_values("Date/Time", ascending=False)
        df_display = df_lookup.rename(
            columns={
                "item_name": "Item",
                "quantity": "Qty",
                "unit_price": "Unit Price",
                "total_value": "Market Value",
                "offered_price": "Offered",
                "status": "Status",
                "profit": "Profit",
            }
        )
        df_display = df_display.drop(columns=["id", "company_id", "timestamp"], errors="ignore")
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        lookup_stats = db.get_item_lookup_stats(company_id=company_id)
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        col_s1.metric("Total Lookup Deals", lookup_stats["total_deals"])
        col_s2.metric("Accepted", lookup_stats["accepted"])
        col_s3.metric("Total Profit", f"${lookup_stats['total_profit']:,.2f}")
        col_s4.metric("Avg Profit/Deal", f"${lookup_stats['avg_profit']:,.2f}")

        if not st.session_state.is_read_only:
            deal_ids = [d["id"] for d in lookup_deals]
            if deal_ids:
                del_id = st.selectbox("Delete a lookup deal by ID:", deal_ids, key="item_lookup_del")
                if st.button("🗑️ Delete", key="item_lookup_del_btn"):
                    if db.delete_item_lookup_deal(del_id, company_id=company_id):
                        st.success(f"✅ Deal #{del_id} deleted!")
                        st.rerun()
    else:
        st.info("No item lookup deals saved yet.")

elif page == "📈 Price History":
    st.header("📈 Price History")
    st.markdown("Track prices over time. Every time prices are fetched, a snapshot is saved.")

    if st.button("📸 Save current prices as snapshot", type="primary", use_container_width=True):
        db.save_price_snapshot(price_iron, price_gold, price_diamond, company_id=company_id)
        st.success("✅ Price snapshot saved!")

    days = st.slider("Show history for last N days:", min_value=1, max_value=90, value=30)
    history = db.get_price_history(days=days, company_id=company_id)

    if history:
        df = pd.DataFrame(history)
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        st.subheader("📊 Price Over Time")
        chart_df = df.set_index("timestamp")
        chart_df = chart_df.rename(
            columns={
                "iron_price": "Iron Ingot ($)",
                "gold_price": "Gold Ingot ($)",
                "diamond_price": "Diamond ($)",
            }
        )
        st.line_chart(chart_df[["Iron Ingot ($)", "Gold Ingot ($)", "Diamond ($)"]])

        st.subheader("📋 All Price Snapshots")
        df_display = df.rename(
            columns={
                "timestamp": "Date/Time",
                "iron_price": "Iron ($)",
                "gold_price": "Gold ($)",
                "diamond_price": "Diamond ($)",
            }
        )
        df_display = df_display.sort_values("Date/Time", ascending=False)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        if len(history) > 1:
            st.subheader("📈 Price Changes")
            first = history[0]
            last = history[-1]
            col_p1, col_p2, col_p3 = st.columns(3)
            iron_change = last["iron_price"] - first["iron_price"]
            gold_change = last["gold_price"] - first["gold_price"]
            diamond_change = last["diamond_price"] - first["diamond_price"]
            col_p1.metric("Iron Change", f"${last['iron_price']:.2f}", f"{iron_change:+.2f}")
            col_p2.metric("Gold Change", f"${last['gold_price']:.2f}", f"{gold_change:+.2f}")
            col_p3.metric(
                "Diamond Change",
                f"${last['diamond_price']:.2f}",
                f"{diamond_change:+.2f}",
            )
    else:
        st.info("No price history yet. Click 'Save current prices as snapshot' to start tracking!")

elif page == "👤 My Profile":
    st.header("👤 My Profile")

    company = db.get_company_by_id(company_id)

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("🔗 Discord Account")
        avatar = st.session_state.discord_avatar_url
        if avatar:
            st.markdown(
                f"<img src='{avatar}' width='64' height='64' style='border-radius:50%'>",
                unsafe_allow_html=True,
            )
        st.markdown(f"**Username:** {st.session_state.discord_username}")
        st.markdown(f"**Role:** {'🛡️ Admin' if st.session_state.is_admin else '👤 User'}")

        if company:
            st.markdown("---")
            st.subheader("🏢 Company")
            current_name = company.get("company_name", "") or ""
            new_name = st.text_input("Company name", value=current_name, key="profile_company_name")
            if st.button("💾 Save Name", type="primary", use_container_width=True):
                if new_name.strip() and new_name.strip() != current_name:
                    if db.update_company_name(company_id, new_name.strip()):
                        st.success("✅ Company name updated!")
                        st.rerun()
                    else:
                        st.error("Failed to update company name.")

    with col_right:
        if company:
            st.subheader("🔑 API Key")
            api_key = company.get("api_key", "")
            show_key = st.checkbox("Show API key", value=False, key="profile_show_key")
            if show_key:
                st.code(api_key, language="text")
                st.caption("Keep this key secret — it grants access to your data via the REST API.")
            else:
                st.code("dc_••••••••••••••", language="text")

            if not st.session_state.is_read_only:
                if st.button("🔄 Regenerate API Key", type="secondary", use_container_width=True):
                    new_key = db.regenerate_api_key(company_id)
                    if new_key:
                        st.success(f"✅ New API key generated! Copy it now: `{new_key}`")
                        st.rerun()
                    else:
                        st.error("Failed to regenerate API key.")

            st.markdown("---")
            st.subheader("🎟️ Invite Code")
            invite_code = company.get("invite_code", "")
            st.markdown(
                "Share this code with someone so they can join your company. "
                'They can enter it on the login page under **"Have an invite code?"**.'
            )
            if invite_code:
                st.code(invite_code, language="text")
                if not st.session_state.is_read_only:
                    if st.button(
                        "🔄 Regenerate Invite Code",
                        type="secondary",
                        use_container_width=True,
                        key="regenerate_invite",
                    ):
                        new_code = db.generate_company_invite_code(company_id)
                        if new_code:
                            st.success(f"✅ New invite code generated! Share it: `{new_code}`")
                            st.rerun()
                        else:
                            st.error("Failed to regenerate invite code.")
            else:
                st.info("No invite code set.")
                if not st.session_state.is_read_only:
                    if st.button(
                        "🔗 Generate Invite Code",
                        type="secondary",
                        use_container_width=True,
                        key="generate_invite",
                    ):
                        new_code = db.generate_company_invite_code(company_id)
                        if new_code:
                            st.success(f"✅ Invite code generated! Share it: `{new_code}`")
                            st.rerun()
                        else:
                            st.error("Failed to generate invite code.")

            st.markdown("---")
            st.subheader("📅 Access")
            expires_at = company.get("access_expires_at")
            is_trial = company.get("trial_used", 0) == 1
            is_active = company.get("is_active", 1)

            if not is_active:
                st.error("❌ **Deactivated** — contact Fishy Business.")
            elif expires_at:
                try:
                    expiry = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                    remaining = (expiry - datetime.now(timezone.utc)).days
                    if remaining < 0:
                        st.warning(f"⚠️ **Expired** — access ended on {expires_at}")
                    else:
                        st.success(f"✅ **Active** — expires in **{remaining} days** ({expires_at})")
                        if is_trial:
                            st.info("🎁 Trial account — contact Fishy Business to upgrade.")
                except (ValueError, TypeError):
                    st.info(f"Expires: {expires_at}")
            else:
                st.success("✅ **Active** — no expiry date (permanent access)")
