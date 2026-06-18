"""
DemocracyCraft Trading Toolbox – Streamlit Web Interface
"""

import sys
import os
import logging
import subprocess
import threading
from pathlib import Path

# Ensure the project root is on sys.path so src.* imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd

from src.core.market_deal import MarketDeal
from src.core import constants
from src.core import database as db

# Initialize database schema on startup
db.init_db()


def _start_api_server():
    """Start the FastAPI server in a background thread."""
    project_root = Path(__file__).resolve().parents[2]
    try:
        subprocess.run(
            [sys.executable, "-m", "uvicorn", "src.web.api:app", "--host", "0.0.0.0", "--port", "8000"],
            cwd=str(project_root),
            check=False,
        )
    except Exception:
        pass


# Kick off the API server in a daemon thread (it will die when the main process exits)
api_thread = threading.Thread(target=_start_api_server, daemon=True)
api_thread.start()


def main() -> None:
    """Entry point for `dc-trade-web` CLI command."""
    # Streamlit handles its own execution; this function exists so
    # pyproject.toml can reference src.web.app:main
    pass

# Page config
st.set_page_config(
    page_title=f"{constants.COMPANY_NAME} Toolbox",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Helper: fetch live prices (cached)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=constants.CACHE_DURATION, show_spinner="⏳ Fetching live prices...")
def fetch_prices() -> tuple[float, float, float]:
    cache = MarketDeal.load_cache()
    p_iron = MarketDeal.get_price("Iron Ingot", cache)
    p_gold = MarketDeal.get_price("Gold Ingot", cache)
    p_diamond = MarketDeal.get_price("Diamond", cache)
    MarketDeal.save_cache(cache)
    return p_iron, p_gold, p_diamond


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title(f"⛏️ {constants.COMPANY_NAME} Toolbox")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    [
        "💰 Deal Calculator",
        "📦 Shulker Scanner",
        "⚡ Quick Converter",
        "📊 Deal History",
        "📦 Stash Manager",
        "📋 Deal Templates",
        "📈 Price History",
    ],
)

st.sidebar.markdown("---")

# Fetch prices (with caching)
price_iron, price_gold, price_diamond = fetch_prices()

st.sidebar.subheader("📈 Live Prices")
st.sidebar.metric("Iron Ingot", f"${price_iron:.2f}")
st.sidebar.metric("Gold Ingot", f"${price_gold:.2f}")
st.sidebar.metric("Diamond", f"${price_diamond:.2f}")

# Block and stack-of-blocks prices
iron_block_price = price_iron * constants.INGOTS_PER_BLOCK
gold_block_price = price_gold * constants.INGOTS_PER_BLOCK
diamond_block_price = price_diamond * constants.INGOTS_PER_BLOCK

prices_block_col1, prices_block_col2 = st.sidebar.columns(2)
prices_block_col1.caption("💰 **Per Block**")
prices_block_col2.caption("💰 **Per Stack of Blocks**")

prices_block_col1.metric("Iron", f"${iron_block_price:.2f}")
prices_block_col2.metric("Iron", f"${iron_block_price * 64:,.2f}")
prices_block_col1.metric("Gold", f"${gold_block_price:.2f}")
prices_block_col2.metric("Gold", f"${gold_block_price * 64:,.2f}")
prices_block_col1.metric("Diamond", f"${diamond_block_price:.2f}")
prices_block_col2.metric("Diamond", f"${diamond_block_price * 64:,.2f}")

# Fetch and display stash in sidebar
stash_summary = db.load_stash()
st.sidebar.subheader("📦 Your Stash")

# Helper: compute total ingot equivalents including raw blocks (treated as same value)
def _total_iron_ingots(s: dict) -> int:
    return (s.get("iron_blocks", 0) + s.get("raw_iron_blocks", 0)) * constants.INGOTS_PER_BLOCK + s.get("iron_ingots", 0)
def _total_gold_ingots(s: dict) -> int:
    return (s.get("gold_blocks", 0) + s.get("raw_gold_blocks", 0)) * constants.INGOTS_PER_BLOCK + s.get("gold_ingots", 0)
def _total_diamond_items(s: dict) -> int:
    return s.get("diamond_blocks", 0) * constants.INGOTS_PER_BLOCK + s.get("diamond_items", 0)

if stash_summary.get("updated_at") != "never" and any(
    [stash_summary["iron_blocks"], stash_summary["iron_ingots"],
     stash_summary["gold_blocks"], stash_summary["gold_ingots"],
     stash_summary["diamond_blocks"], stash_summary["diamond_items"],
     stash_summary.get("raw_iron_blocks", 0), stash_summary.get("raw_gold_blocks", 0)]
):
    total_iron = _total_iron_ingots(stash_summary)
    total_gold = _total_gold_ingots(stash_summary)
    total_diamond = _total_diamond_items(stash_summary)
    iron_parts = []
    if stash_summary.get("raw_iron_blocks"):
        iron_parts.append(f"{stash_summary['raw_iron_blocks']} raw")
    if stash_summary["iron_blocks"]:
        iron_parts.append(f"{stash_summary['iron_blocks']}b")
    if stash_summary["iron_ingots"]:
        iron_parts.append(f"{stash_summary['iron_ingots']}i")
    iron_display = " + ".join(iron_parts) if iron_parts else "0"
    gold_parts = []
    if stash_summary.get("raw_gold_blocks"):
        gold_parts.append(f"{stash_summary['raw_gold_blocks']} raw")
    if stash_summary["gold_blocks"]:
        gold_parts.append(f"{stash_summary['gold_blocks']}b")
    if stash_summary["gold_ingots"]:
        gold_parts.append(f"{stash_summary['gold_ingots']}i")
    gold_display = " + ".join(gold_parts) if gold_parts else "0"
    diamond_parts = []
    if stash_summary["diamond_blocks"]:
        diamond_parts.append(f"{stash_summary['diamond_blocks']}b")
    if stash_summary["diamond_items"]:
        diamond_parts.append(f"{stash_summary['diamond_items']}i")
    diamond_display = " + ".join(diamond_parts) if diamond_parts else "0"
    st.sidebar.caption(
        f"⬜ Iron: {iron_display}\n"
        f"🟨 Gold: {gold_display}\n"
        f"💎 Diamond: {diamond_display}"
    )
    total_value = total_iron * price_iron + total_gold * price_gold + total_diamond * price_diamond
    st.sidebar.metric("Total Value", f"${total_value:,.2f}")
    st.sidebar.caption(f"Updated: {stash_summary.get('updated_at', 'never')}")
else:
    st.sidebar.caption("Empty — add materials in Stash Manager.")

st.sidebar.markdown("---")
st.sidebar.caption(f"Data cached for {constants.CACHE_DURATION // 3600}h")
st.sidebar.caption(f"Database: `{constants.DB_FILE}`")


# ---------------------------------------------------------------------------
# Helper: compute deal result
# ---------------------------------------------------------------------------
def analyze_deal(
    iron_ingots: float,
    gold_ingots: float,
    diamond_items: float,
    p_iron: float,
    p_gold: float,
    p_diamond: float,
    offered_price: float,
) -> dict:
    """Run the full deal analysis and return a results dict."""
    total_market = (
        iron_ingots * p_iron
        + gold_ingots * p_gold
        + diamond_items * p_diamond
    )
    min_needed = total_market * MarketDeal.MIN_ACCEPTABLE_PERCENT

    profit_loss = offered_price - total_market
    pct_of_market = (offered_price / total_market * 100) if total_market > 0 else 0

    if offered_price >= total_market:
        status = "ACCEPTED (PROFIT)"
        status_color = "green"
        status_msg = f"✅ SUPER DEAL! +{profit_loss:.2f}$ profit over market."
    elif offered_price >= min_needed:
        status = "ACCEPTED (BULK)"
        status_color = "orange"
        status_msg = f"🟡 OK! Within bulk discount ({abs(profit_loss):.2f}$ discount)."
    else:
        status = "REJECTED"
        status_color = "red"
        status_msg = f"❌ Too cheap! Need {min_needed - offered_price:.2f}$ more to your limit."

    stacks = (iron_ingots + gold_ingots + diamond_items) / float(constants.ITEMS_PER_STACK)
    shulkers = (iron_ingots + gold_ingots + diamond_items) / float(constants.ITEMS_PER_SHULKER)

    # Counter-offer logic
    counter_offer = None
    if status == "REJECTED":
        diamond_value = diamond_items * p_diamond
        remaining = offered_price - diamond_value
        total_metals = iron_ingots + gold_ingots
        if total_metals > 0 and remaining > 0:
            ratio = iron_ingots / total_metals
            fair_metals = remaining / ((ratio * p_iron) + ((1 - ratio) * p_gold))
            counter_offer = {
                "iron": MarketDeal.format_bulk_storage(fair_metals * ratio),
                "gold": MarketDeal.format_bulk_storage(fair_metals * (1 - ratio)),
                "diamond": MarketDeal.format_bulk_storage(diamond_items, is_diamond=True),
            }

    return {
        "total_market": total_market,
        "min_needed": min_needed,
        "offered": offered_price,
        "pct_of_market": pct_of_market,
        "profit_loss": profit_loss,
        "status": status,
        "status_color": status_color,
        "status_msg": status_msg,
        "stacks": stacks,
        "shulkers": shulkers,
        "counter_offer": counter_offer,
    }


# ---------------------------------------------------------------------------
# Helper: stash ingot equivalents
# ---------------------------------------------------------------------------
def stash_ingot_equivalents(stash: dict) -> tuple:
    """Return (iron_ingots, gold_ingots, diamond_items) from stash dict."""
    iron = stash["iron_blocks"] * constants.INGOTS_PER_BLOCK + stash["iron_ingots"]
    gold = stash["gold_blocks"] * constants.INGOTS_PER_BLOCK + stash["gold_ingots"]
    diamond = stash["diamond_blocks"] * constants.INGOTS_PER_BLOCK + stash["diamond_items"]
    return iron, gold, diamond


def _format_subtract_result(result: dict) -> str:
    """Format a subtract_from_stash result dict into a readable string."""
    parts = []
    if result["iron_blocks"] or result["iron_ingots"]:
        parts.append(f"Iron: {result['iron_blocks']} blocks + {result['iron_ingots']} ingots")
    if result["gold_blocks"] or result["gold_ingots"]:
        parts.append(f"Gold: {result['gold_blocks']} blocks + {result['gold_ingots']} ingots")
    if result["diamond_blocks"] or result["diamond_items"]:
        parts.append(f"Diamonds: {result['diamond_blocks']} blocks + {result['diamond_items']} items")
    return " | ".join(parts)


def _log_deal_with_all_fields(
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
    """Log a deal including original amounts and units."""
    profit = offered_price - market_value
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO deals
               (timestamp, iron_ingots, gold_ingots, diamond_items,
                iron_price, gold_price, diamond_price,
                market_value, offered_price, status, profit,
                iron_amount, iron_unit, gold_amount, gold_unit,
                diamond_amount, diamond_unit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date_str, iron_ingots, gold_ingots, diamond_items,
             iron_price, gold_price, diamond_price,
             market_value, offered_price, status, profit,
             iron_amount, iron_unit, gold_amount, gold_unit,
             diamond_amount, diamond_unit),
        )
        conn.commit()
        conn.close()
        import logging
        logging.getLogger(__name__).info("Deal logged to database: %s | %s", status, date_str)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Failed to log deal: %s", exc)


def _handle_deal_logging(
    iron_ingots: float,
    gold_ingots: float,
    diamond_items: float,
    result: dict,
    price_iron: float,
    price_gold: float,
    price_diamond: float,
    key_prefix: str,
    iron_amount_orig: float = 0.0,
    iron_unit_orig: str = "ingot",
    gold_amount_orig: float = 0.0,
    gold_unit_orig: str = "ingot",
    diamond_amount_orig: float = 0.0,
    diamond_unit_orig: str = "ingot",
) -> None:
    """Show logging UI and handle log-to-database with optional manual status override."""
    st.markdown("---")
    st.subheader("💾 Save Deal")

    col_log1, col_log2 = st.columns([1, 1])

    with col_log1:
        # Manual status override
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
            min_value=0.0, step=0.5,
            value=result["offered"],
            key=f"{key_prefix}_manual_offer",
        )

    # Use a button instead of checkbox to avoid double-logging on reruns
    log_clicked = st.button("💾 Log this deal to database", key=f"{key_prefix}_log_btn", use_container_width=True)

    if log_clicked:
        _log_deal_with_all_fields(
            iron_ingots, gold_ingots, diamond_items,
            result["total_market"], manual_offer, final_status,
            price_iron, price_gold, price_diamond,
            iron_amount_orig, iron_unit_orig,
            gold_amount_orig, gold_unit_orig,
            diamond_amount_orig, diamond_unit_orig,
        )
        st.success(f"✅ Deal logged to database as '{final_status}'!")

    # Stash subtraction
    auto_sub = db.get_auto_subtract()
    if auto_sub:
        sub_result = db.subtract_from_stash(int(iron_ingots), int(gold_ingots), int(diamond_items))
        st.info(f"📦 Auto-subtracted from stash: {_format_subtract_result(sub_result)}")
    else:
        col_sub1, col_sub2 = st.columns([1, 1])
        with col_sub1:
            subtract_choice = st.checkbox(
                "📦 Subtract these materials from stash?",
                value=False,
                key=f"{key_prefix}_subtract",
            )
        if subtract_choice:
            sub_result = db.subtract_from_stash(int(iron_ingots), int(gold_ingots), int(diamond_items))
            st.info(f"✅ Subtracted from stash: {_format_subtract_result(sub_result)}")

    return final_status


# ===========================================================================
# PAGE: Deal Calculator
# ===========================================================================
if page == "💰 Deal Calculator":
    st.header("💰 Deal Calculator")
    st.markdown("Enter raw material amounts and their units.")

    # Load from stash option
    load_from_stash = st.checkbox("📦 Load values from stash", value=False, key="deal_load_stash")
    stash = db.load_stash() if load_from_stash else None

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

    # Keep original user-input amounts (before conversion) for the log
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
        diamond_amount = st.number_input("Diamond amount", min_value=0.0, step=1.0, key="diamond_amt", value=default_diamond)
        diamond_unit = st.selectbox("Diamond unit", ["ingot", "block", "nugget"], key="diamond_unit", index=0)

    offered_price = st.number_input(
        "💰 Offered price ($)", min_value=0.0, step=0.5, value=0.0, key="deal_offer"
    )

    # Use session state to persist deal result across reruns
    if "deal_result" not in st.session_state:
        st.session_state.deal_result = None

    if st.button("📊 Calculate Deal", type="primary", use_container_width=True):
        iron_ingots = MarketDeal.convert_to_ingots(iron_amount, iron_unit)
        gold_ingots = MarketDeal.convert_to_ingots(gold_amount, gold_unit)
        diamond_items = MarketDeal.convert_to_ingots(diamond_amount, diamond_unit)

        # Store original amounts for logging
        st.session_state.deal_iron_amount_orig = iron_amount
        st.session_state.deal_iron_unit_orig = iron_unit
        st.session_state.deal_gold_amount_orig = gold_amount
        st.session_state.deal_gold_unit_orig = gold_unit
        st.session_state.deal_diamond_amount_orig = diamond_amount
        st.session_state.deal_diamond_unit_orig = diamond_unit

        if iron_ingots == 0 and gold_ingots == 0 and diamond_items == 0:
            st.warning("Please enter at least some materials.")
            st.session_state.deal_result = None
        else:
            result = analyze_deal(
                iron_ingots, gold_ingots, diamond_items,
                price_iron, price_gold, price_diamond,
                offered_price,
            )
            st.session_state.deal_result = {
                "iron_ingots": iron_ingots,
                "gold_ingots": gold_ingots,
                "diamond_items": diamond_items,
                "result": result,
                "price_iron": price_iron,
                "price_gold": price_gold,
                "price_diamond": price_diamond,
            }

    # Display result from session state (persists across reruns)
    if st.session_state.deal_result is not None:
        d = st.session_state.deal_result
        iron_ingots = d["iron_ingots"]
        gold_ingots = d["gold_ingots"]
        diamond_items = d["diamond_items"]
        result = d["result"]
        price_iron = d["price_iron"]
        price_gold = d["price_gold"]
        price_diamond = d["price_diamond"]

        st.markdown("---")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Market Value", f"${result['total_market']:.2f}")
        col_b.metric("Your Offer", f"${result['offered']:.2f}")
        col_c.metric(
            "Profit / Loss",
            f"${result['profit_loss']:.2f}",
            delta=f"${result['profit_loss']:.2f}",
        )

        st.markdown(f"### {result['status']}")
        st.markdown(f"**{result['status_msg']}**")
        st.markdown(f"Your offer is **{result['pct_of_market']:.1f}%** of market value.")
        st.markdown(
            f"Minimum acceptable ({MarketDeal.MIN_ACCEPTABLE_PERCENT*100:.0f}%): "
            f"**${result['min_needed']:.2f}**"
        )

        st.markdown("#### Logistics")
        st.write(f"~{result['stacks']:.1f} stacks ({result['shulkers']:.2f} shulker boxes)")
        if result['stacks'] > 0:
            st.write(
                f"${result['profit_loss']/result['stacks']:.2f} per stack | "
                f"${result['profit_loss']/result['shulkers']:.2f} per shulker"
            )

        if result["counter_offer"]:
            st.markdown("#### 💡 Counter-Offer Suggestion")
            co = result["counter_offer"]
            st.info(
                f"For ${result['offered']:.0f}, offer instead:\n"
                f"- Iron: {co['iron']}\n"
                f"- Gold: {co['gold']}\n"
                f"- Diamonds: {co['diamond']} (unchanged)"
            )

        # Deal logging UI with manual status override
        _handle_deal_logging(
            iron_ingots, gold_ingots, diamond_items,
            result, price_iron, price_gold, price_diamond,
            "deal",
            iron_amount_orig=st.session_state.deal_iron_amount_orig,
            iron_unit_orig=st.session_state.deal_iron_unit_orig,
            gold_amount_orig=st.session_state.deal_gold_amount_orig,
            gold_unit_orig=st.session_state.deal_gold_unit_orig,
            diamond_amount_orig=st.session_state.deal_diamond_amount_orig,
            diamond_unit_orig=st.session_state.deal_diamond_unit_orig,
        )


# ===========================================================================
# PAGE: Shulker Scanner
# ===========================================================================
elif page == "📦 Shulker Scanner":
    st.header("📦 Shulker Scanner")
    st.markdown("Enter materials as full stacks + remainder for blocks and items.")

    # Load from stash option
    load_from_stash = st.checkbox("📦 Load values from stash", value=False, key="shulker_load_stash")
    stash = db.load_stash() if load_from_stash else None

    # Default values from stash
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
        has_values = stash["iron_blocks"] > 0 or stash["iron_ingots"] > 0 or \
                     stash["gold_blocks"] > 0 or stash["gold_ingots"] > 0 or \
                     stash["diamond_blocks"] > 0 or stash["diamond_items"] > 0
        if has_values:
            st.info(
                f"📦 Loaded from stash: "
                f"Iron: {stash['iron_blocks']} blocks + {stash['iron_ingots']} ingots, "
                f"Gold: {stash['gold_blocks']} blocks + {stash['gold_ingots']} ingots, "
                f"Diamonds: {stash['diamond_blocks']} blocks + {stash['diamond_items']} items"
            )
            # Convert stash block counts to stacks (assuming each 9 blocks form 1 stack of blocks)
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
        di_blocks_stacks = st.number_input("Full stacks DIAMOND BLOCKS", min_value=0, step=1, key="di_b_s", value=di_blocks_stacks_default)
        di_blocks_rest = st.number_input("Remainder DIAMOND BLOCKS (0-63)", min_value=0, max_value=63, step=1, key="di_b_r", value=di_blocks_rest_default)
        di_items_stacks = st.number_input("Full stacks DIAMOND ITEMS", min_value=0, step=1, key="di_i_s", value=di_items_stacks_default)
        di_items_rest = st.number_input("Remainder DIAMOND ITEMS (0-63)", min_value=0, max_value=63, step=1, key="di_i_r", value=di_items_rest_default)
        total_diamond = (di_blocks_stacks * 64 + di_blocks_rest) * 9 + (di_items_stacks * 64 + di_items_rest)

    with col2:
        st.subheader("⬜ Iron")
        ir_blocks_stacks = st.number_input("Full stacks IRON BLOCKS", min_value=0, step=1, key="ir_b_s", value=ir_blocks_stacks_default)
        ir_blocks_rest = st.number_input("Remainder IRON BLOCKS (0-63)", min_value=0, max_value=63, step=1, key="ir_b_r", value=ir_blocks_rest_default)
        ir_items_stacks = st.number_input("Full stacks IRON ITEMS", min_value=0, step=1, key="ir_i_s", value=ir_items_stacks_default)
        ir_items_rest = st.number_input("Remainder IRON ITEMS (0-63)", min_value=0, max_value=63, step=1, key="ir_i_r", value=ir_items_rest_default)
        total_iron = (ir_blocks_stacks * 64 + ir_blocks_rest) * 9 + (ir_items_stacks * 64 + ir_items_rest)

    with col3:
        st.subheader("🟨 Gold")
        go_blocks_stacks = st.number_input("Full stacks GOLD BLOCKS", min_value=0, step=1, key="go_b_s", value=go_blocks_stacks_default)
        go_blocks_rest = st.number_input("Remainder GOLD BLOCKS (0-63)", min_value=0, max_value=63, step=1, key="go_b_r", value=go_blocks_rest_default)
        go_items_stacks = st.number_input("Full stacks GOLD ITEMS", min_value=0, step=1, key="go_i_s", value=go_items_stacks_default)
        go_items_rest = st.number_input("Remainder GOLD ITEMS (0-63)", min_value=0, max_value=63, step=1, key="go_i_r", value=go_items_rest_default)
        total_gold = (go_blocks_stacks * 64 + go_blocks_rest) * 9 + (go_items_stacks * 64 + go_items_rest)

    multiplier = st.number_input("Multiplier (how many times this chest config is delivered)", min_value=1, step=1, value=1)

    offered_price = st.number_input(
        "💰 Offered price ($)", min_value=0.0, step=0.5, value=0.0, key="shulker_offer"
    )

    # Use session state to persist shulker result across reruns
    if "shulker_result" not in st.session_state:
        st.session_state.shulker_result = None

    if st.button("📊 Scan Shulker", type="primary", use_container_width=True):
        iron_ingots = total_iron * multiplier
        gold_ingots = total_gold * multiplier
        diamond_items = total_diamond * multiplier

        if iron_ingots == 0 and gold_ingots == 0 and diamond_items == 0:
            st.warning("Please enter at least some materials.")
            st.session_state.shulker_result = None
        else:
            result = analyze_deal(
                iron_ingots, gold_ingots, diamond_items,
                price_iron, price_gold, price_diamond,
                offered_price,
            )
            st.session_state.shulker_result = {
                "iron_ingots": iron_ingots,
                "gold_ingots": gold_ingots,
                "diamond_items": diamond_items,
                "result": result,
                "price_iron": price_iron,
                "price_gold": price_gold,
                "price_diamond": price_diamond,
            }

    # Display result from session state (persists across reruns)
    if st.session_state.shulker_result is not None:
        d = st.session_state.shulker_result
        iron_ingots = d["iron_ingots"]
        gold_ingots = d["gold_ingots"]
        diamond_items = d["diamond_items"]
        result = d["result"]
        price_iron = d["price_iron"]
        price_gold = d["price_gold"]
        price_diamond = d["price_diamond"]

        st.markdown("---")
        st.write(f"Iron: {MarketDeal.format_bulk_storage(iron_ingots)}")
        st.write(f"Gold: {MarketDeal.format_bulk_storage(gold_ingots)}")
        st.write(f"Diamonds: {MarketDeal.format_bulk_storage(diamond_items, is_diamond=True)}")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Market Value", f"${result['total_market']:.2f}")
        col_b.metric("Your Offer", f"${result['offered']:.2f}")
        col_c.metric("Profit / Loss", f"${result['profit_loss']:.2f}", delta=f"${result['profit_loss']:.2f}")

        st.markdown(f"### {result['status']}")
        st.markdown(f"**{result['status_msg']}**")

        st.markdown("#### Logistics")
        st.write(f"~{result['stacks']:.1f} stacks ({result['shulkers']:.2f} shulker boxes)")

        if result["counter_offer"]:
            st.markdown("#### 💡 Counter-Offer")
            co = result["counter_offer"]
            st.info(
                f"For ${result['offered']:.0f}, offer instead:\n"
                f"- Iron: {co['iron']}\n"
                f"- Gold: {co['gold']}\n"
                f"- Diamonds: {co['diamond']}"
            )

        # Deal logging UI with manual status override
        _handle_deal_logging(
            iron_ingots, gold_ingots, diamond_items,
            result, price_iron, price_gold, price_diamond,
            "shulker",
        )


# ===========================================================================
# PAGE: Quick Converter
# ===========================================================================
elif page == "⚡ Quick Converter":
    st.header("⚡ Quick Converter")
    st.markdown("Convert item amounts between blocks, stacks, and shulkers.")

    base_amount = st.number_input("Amount per load", min_value=1, step=100, value=1500)
    multiplier = st.number_input("Multiplier", min_value=1, step=1, value=1)

    if st.button("🔄 Convert", type="primary", use_container_width=True):
        amount = base_amount * multiplier
        blocks = amount // constants.INGOTS_PER_BLOCK
        rest_ingots = amount % constants.INGOTS_PER_BLOCK
        stacks = amount // constants.ITEMS_PER_STACK
        rest_items = amount % constants.ITEMS_PER_STACK
        shulkers = amount / constants.ITEMS_PER_SHULKER

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


# ===========================================================================
# PAGE: Deal History
# ===========================================================================
elif page == "📊 Deal History":
    st.header("📊 Deal History")

    stats = db.get_deal_stats()
    deals = db.get_all_deals(limit=200)

    # Stats row
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Deals", stats["total_deals"])
    col2.metric("Accepted", stats["accepted"])
    col3.metric("Rejected", stats["rejected"])
    col4.metric("Total Profit", f"${stats['total_profit']:,.2f}")
    col5.metric("Avg Profit/Deal", f"${stats['avg_profit']:,.2f}")
    col6.metric("Total Market Value", f"${stats['total_market_value']:,.2f}")

    if deals:
        df = pd.DataFrame(deals)

        # Profit chart
        df_chart = df.copy()
        df_chart["Date/Time"] = pd.to_datetime(df_chart["timestamp"])
        df_chart = df_chart.sort_values("Date/Time").reset_index(drop=True)
        df_chart["Deal #"] = range(1, len(df_chart) + 1)

        st.subheader("📈 Profit Trends")
        chart_data = df_chart[["Deal #", "profit"]].rename(columns={"profit": "Profit ($)"})
        st.line_chart(chart_data.set_index("Deal #"))

        # Deal table with action buttons
        st.subheader("📋 All Deals")
        df_display = df.drop(columns=["id", "iron_amount", "iron_unit", "gold_amount", "gold_unit", "diamond_amount", "diamond_unit"], errors="ignore")
        df_display = df_display.rename(columns={
            "timestamp": "Date/Time",
            "iron_ingots": "Iron",
            "gold_ingots": "Gold",
            "diamond_items": "Diamonds",
            "market_value": "Market Value",
            "offered_price": "Offered",
            "status": "Status",
            "profit": "Profit",
        })
        df_display["Date/Time"] = pd.to_datetime(df_display["Date/Time"])
        df_display = df_display.sort_values("Date/Time", ascending=False)

        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # Download button
        csv = df_display.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇ Download CSV",
            csv,
            "dc_trade_deals.csv",
            "text/csv",
        )

        st.markdown("---")
        st.subheader("✏️ Edit or Delete a Deal")

        # Select deal to edit
        deal_options = {f"#{d['id']} – {d['status']} ({d['timestamp']})": d['id'] for d in deals[:50]}
        selected_label = st.selectbox("Select a deal to edit:", list(deal_options.keys()), key="deal_edit_select")
        selected_id = deal_options[selected_label]

        # Find the selected deal
        selected_deal = next((d for d in deals if d['id'] == selected_id), None)
        if selected_deal:
            col_edit1, col_edit2, col_edit3 = st.columns([2, 2, 1])
            with col_edit1:
                new_status = st.text_input("New status:", value=selected_deal["status"], key="deal_edit_status")
            with col_edit2:
                new_offer = st.number_input("New offered price ($):", min_value=0.0, step=0.5, value=float(selected_deal["offered_price"]), key="deal_edit_offer")
            with col_edit3:
                st.markdown("##### &nbsp;")
                if st.button("💾 Update Deal", key="deal_edit_update", use_container_width=True):
                    if db.update_deal(selected_id, new_status, new_offer):
                        st.success(f"✅ Deal #{selected_id} updated!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to update deal.")

            if st.button("🗑️ Delete Deal", key=f"deal_delete_{selected_id}", type="secondary"):
                if db.delete_deal(selected_id):
                    st.success(f"✅ Deal #{selected_id} deleted!")
                    st.rerun()
                else:
                    st.error("❌ Failed to delete deal.")
    else:
        st.info("No deals logged yet. Use one of the calculators above!")


# ===========================================================================
# PAGE: Stash Manager
# ===========================================================================
elif page == "📦 Stash Manager":
    st.header("📦 Stash Manager")
    st.markdown("Save and manage your current inventory for quick access.")

    stash = db.load_stash()

    # Helper: ingot totals including raw blocks (treated as same value)
    def _total_iron(s: dict) -> int:
        return (s.get("iron_blocks", 0) + s.get("raw_iron_blocks", 0)) * constants.INGOTS_PER_BLOCK + s.get("iron_ingots", 0)
    def _total_gold(s: dict) -> int:
        return (s.get("gold_blocks", 0) + s.get("raw_gold_blocks", 0)) * constants.INGOTS_PER_BLOCK + s.get("gold_ingots", 0)
    def _total_diamond(s: dict) -> int:
        return s.get("diamond_blocks", 0) * constants.INGOTS_PER_BLOCK + s.get("diamond_items", 0)

    total_iron = _total_iron(stash)
    total_gold = _total_gold(stash)
    total_diamond = _total_diamond(stash)

    # Market value
    iron_value = total_iron * price_iron
    gold_value = total_gold * price_gold
    diamond_value = total_diamond * price_diamond
    total_value = iron_value + gold_value + diamond_value

    stacks = (total_iron + total_gold + total_diamond) / float(constants.ITEMS_PER_STACK)
    shulkers = (total_iron + total_gold + total_diamond) / float(constants.ITEMS_PER_SHULKER)

    # Display current stash
    st.subheader("📦 Current Stash")
    last_updated = stash.get("updated_at", "never")
    st.caption(f"Last updated: {last_updated}")

    raw_iron_str = f" (+{stash.get('raw_iron_blocks', 0)} raw)" if stash.get("raw_iron_blocks", 0) else ""
    raw_gold_str = f" (+{stash.get('raw_gold_blocks', 0)} raw)" if stash.get("raw_gold_blocks", 0) else ""
    col1, col2, col3 = st.columns(3)
    col1.metric("Iron", f"{stash['iron_blocks']} blocks{raw_iron_str} + {stash['iron_ingots']} ingots", f"{MarketDeal.format_bulk_storage(total_iron)}")
    col2.metric("Gold", f"{stash['gold_blocks']} blocks{raw_gold_str} + {stash['gold_ingots']} ingots", f"{MarketDeal.format_bulk_storage(total_gold)}")
    col3.metric("Diamonds", f"{stash['diamond_blocks']} blocks + {stash['diamond_items']} items", f"{MarketDeal.format_bulk_storage(total_diamond, is_diamond=True)}")

    st.markdown("---")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Total Market Value", f"${total_value:,.2f}")
    col_b.metric("Iron Value", f"${iron_value:,.2f}")
    col_c.metric("Gold Value", f"${gold_value:,.2f}")
    col_d.metric("Diamond Value", f"${diamond_value:,.2f}")

    st.caption(f"🚚 Shipping: ~{stacks:.1f} stacks (~{shulkers:.2f} shulker boxes)")

    st.markdown("---")

    # Update stash form
    st.subheader("✏️ Update Stash")
    st.markdown("Enter your current inventory (values in blocks / ingots / items, NOT stacks)")

    # Auto-subtract toggle
    auto_sub = bool(stash.get("auto_subtract", 0))
    col_toggle1, col_toggle2 = st.columns([1, 3])
    with col_toggle1:
        new_auto_sub = st.checkbox("🔁 Auto-subtract", value=auto_sub,
                                   help="When enabled, materials are automatically subtracted from stash after every deal.")
    with col_toggle2:
        st.caption("When enabled, deal materials are automatically deducted from stash without asking.")
    if new_auto_sub != auto_sub:
        db.set_auto_subtract(new_auto_sub)
        st.success(f"Auto-subtract is now {'ON' if new_auto_sub else 'OFF'}!")
        st.rerun()

    st.markdown("---")

    with st.form("stash_form"):
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            iron_blocks = st.number_input("Iron blocks", min_value=0, step=1, value=int(stash["iron_blocks"]))
            raw_iron_blocks = st.number_input("Raw iron blocks", min_value=0, step=1, value=int(stash.get("raw_iron_blocks", 0)))
            gold_blocks = st.number_input("Gold blocks", min_value=0, step=1, value=int(stash["gold_blocks"]))
            raw_gold_blocks = st.number_input("Raw gold blocks", min_value=0, step=1, value=int(stash.get("raw_gold_blocks", 0)))
            diamond_blocks = st.number_input("Diamond blocks", min_value=0, step=1, value=int(stash["diamond_blocks"]))
        with col_i2:
            iron_ingots = st.number_input("Iron ingots", min_value=0, step=1, value=int(stash["iron_ingots"]))
            gold_ingots = st.number_input("Gold ingots", min_value=0, step=1, value=int(stash["gold_ingots"]))
            diamond_items = st.number_input("Diamond items", min_value=0, step=1, value=int(stash["diamond_items"]))

        submitted = st.form_submit_button("💾 Save Stash", type="primary", use_container_width=True)

    if submitted:
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
        db.save_stash(new_stash)
        st.success("✅ Stash saved!")
        st.rerun()

    st.markdown("---")

    # Add to stash section
    st.subheader("➕ Add Materials to Stash")
    st.markdown("Enter positive values to add to your existing stash.")
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

        add_submitted = st.form_submit_button("➕ Add to Stash", type="secondary", use_container_width=True)

    if add_submitted:
        has_values = any([
            add_iron_blocks, add_iron_ingots, add_gold_blocks,
            add_gold_ingots, add_diamond_blocks, add_diamond_items,
        ])
        if has_values:
            db.add_to_stash(
                iron_blocks=add_iron_blocks,
                iron_ingots=add_iron_ingots,
                gold_blocks=add_gold_blocks,
                gold_ingots=add_gold_ingots,
                diamond_blocks=add_diamond_blocks,
                diamond_items=add_diamond_items,
            )
            st.success("✅ Materials added to stash!")
            st.rerun()
        else:
            st.warning("⚠ Please enter at least one value to add.")

    st.markdown("---")

    # Clear stash button
    if st.button("🗑️ Clear Stash", type="secondary", use_container_width=True):
        if stash and (stash["iron_blocks"] or stash["iron_ingots"] or stash["gold_blocks"]
                      or stash["gold_ingots"] or stash["diamond_blocks"] or stash["diamond_items"]
                      or stash.get("raw_iron_blocks", 0) or stash.get("raw_gold_blocks", 0)):
            st.warning("Are you sure?")
            col_confirm1, col_confirm2 = st.columns(2)
            with col_confirm1:
                if st.button("Yes, clear it", type="primary"):
                    db.clear_stash()
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
        "Only recognised items (Iron, Gold, Diamond blocks/ingots/raw variants) will be imported – "
        "everything else is ignored. **This replaces the entire stash.**"
    )
    import_text = st.text_area(
        "Paste item list here",
        height=200,
        placeholder="Paste your item dump here...\nExample:\nBlock of Raw Iron:  713\nBlock of Iron:  176\nIron Ingot:  95\nBlock of Raw Gold:  86\nBlock of Gold:  67\nGold Ingot:  268\nBlock of Diamond:  183\nDiamond:  15",
        key="import_text",
    )
    if st.button("📥 Import & Replace Stash", type="primary", use_container_width=True):
        if not import_text.strip():
            st.warning("⚠ Please paste an item list first.")
        else:
            updated_stash, recognised, skipped = db.import_items_to_stash(import_text)
            skipped_count = len(skipped)
            # Build a summary of what was detected
            detected_parts = []
            if updated_stash.get("raw_iron_blocks"):
                detected_parts.append(f"{updated_stash['raw_iron_blocks']} raw iron blocks")
            if updated_stash["iron_blocks"]:
                detected_parts.append(f"{updated_stash['iron_blocks']} iron blocks")
            if updated_stash["iron_ingots"]:
                detected_parts.append(f"{updated_stash['iron_ingots']} iron ingots")
            if updated_stash.get("raw_gold_blocks"):
                detected_parts.append(f"{updated_stash['raw_gold_blocks']} raw gold blocks")
            if updated_stash["gold_blocks"]:
                detected_parts.append(f"{updated_stash['gold_blocks']} gold blocks")
            if updated_stash["gold_ingots"]:
                detected_parts.append(f"{updated_stash['gold_ingots']} gold ingots")
            if updated_stash["diamond_blocks"]:
                detected_parts.append(f"{updated_stash['diamond_blocks']} diamond blocks")
            if updated_stash["diamond_items"]:
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


# ===========================================================================
# PAGE: Deal Templates
# ===========================================================================
elif page == "📋 Deal Templates":
    st.header("📋 Deal Templates")
    st.markdown("Save and load common deal configurations.")

    templates = db.load_templates()

    # Save new template
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

        save_template_clicked = st.form_submit_button("💾 Save Template", type="primary", use_container_width=True)

    if save_template_clicked:
        if template_name.strip():
            if db.save_template(template_name.strip(), t_iron, t_gold, t_diamond, t_offer):
                st.success(f"✅ Template '{template_name}' saved!")
                st.rerun()
        else:
            st.warning("⚠ Please enter a template name.")

    # Load and use template
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
                load_key = f"load_tmpl_{tmpl['name']}"
                if st.button("📥 Load", key=load_key, use_container_width=True):
                    # Save template data to session state for deal calculator
                    st.session_state.template_load = tmpl
                    st.success(f"✅ Template '{tmpl['name']}' loaded! Go to Deal Calculator.")
                    st.rerun()

                del_key = f"del_tmpl_{tmpl['name']}"
                if st.button("🗑️", key=del_key):
                    db.delete_template(tmpl['name'])
                    st.rerun()

        # Show loaded template data
        if "template_load" in st.session_state and st.session_state.template_load:
            tmpl = st.session_state.template_load
            st.info(
                f"📥 **Loaded template:** {tmpl['name']} – "
                f"Iron: {tmpl['iron_ingots']:.0f}, "
                f"Gold: {tmpl['gold_ingots']:.0f}, "
                f"Diamonds: {tmpl['diamond_items']:.0f}, "
                f"Offer: ${tmpl['offered_price']:.2f}"
            )
            if st.button("🧹 Clear loaded template"):
                st.session_state.template_load = None
                st.rerun()
    else:
        st.info("No templates saved yet. Create one above!")


# ===========================================================================
# PAGE: Price History
# ===========================================================================
elif page == "📈 Price History":
    st.header("📈 Price History")
    st.markdown("Track prices over time. Every time prices are fetched, a snapshot is saved.")

    # Save current prices as snapshot
    if st.button("📸 Save current prices as snapshot", type="primary", use_container_width=True):
        db.save_price_snapshot(price_iron, price_gold, price_diamond)
        st.success("✅ Price snapshot saved!")

    days = st.slider("Show history for last N days:", min_value=1, max_value=90, value=30)
    history = db.get_price_history(days=days)

    if history:
        df = pd.DataFrame(history)
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        st.subheader("📊 Price Over Time")
        chart_df = df.set_index("timestamp")
        chart_df = chart_df.rename(columns={
            "iron_price": "Iron Ingot ($)",
            "gold_price": "Gold Ingot ($)",
            "diamond_price": "Diamond ($)",
        })
        st.line_chart(chart_df[["Iron Ingot ($)", "Gold Ingot ($)", "Diamond ($)"]])

        st.subheader("📋 All Price Snapshots")
        df_display = df.rename(columns={
            "timestamp": "Date/Time",
            "iron_price": "Iron ($)",
            "gold_price": "Gold ($)",
            "diamond_price": "Diamond ($)",
        })
        df_display = df_display.sort_values("Date/Time", ascending=False)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # Stats
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
            col_p3.metric("Diamond Change", f"${last['diamond_price']:.2f}", f"{diamond_change:+.2f}")
    else:
        st.info("No price history yet. Click 'Save current prices as snapshot' to start tracking!")
