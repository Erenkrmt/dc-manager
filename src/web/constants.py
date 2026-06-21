"""
Shared string constants for the web UI module.

Avoids SonarQube S1192 ("define a constant instead of duplicating this literal")
by centralising frequently reused labels, menu titles, and column headers.
"""

from __future__ import annotations

# ── Page / Menu labels ──────────────────────────────────────────────────────

MENU_DEAL_CALCULATOR = "💰 Deal Calculator"
MENU_QUICK_CONVERTER = "⚡ Quick Converter"
MENU_DEAL_HISTORY = "📊 Deal History"
MENU_SHULKER_SCANNER = "📦 Shulker Scanner"
MENU_STASH_MANAGER = "📦 Stash Manager"
MENU_ITEM_LOOKUP = "🔍 Item Lookup"
MENU_PRICE_HISTORY = "📈 Price History"
MENU_DEAL_TEMPLATES = "📋 Deal Templates"
MENU_MY_PROFILE = "👤 My Profile"
MENU_COMPANY_MANAGEMENT = "🏢 Company Management"

# ── Table / chart column headers ────────────────────────────────────────────

COL_DATE_TIME = "Date/Time"
COL_MARKET_VALUE = "Market Value"
COL_YOUR_OFFER = "Your Offer"
COL_PROFIT_LOSS = "Profit / Loss"
COL_DIAMOND = "Diamond ($)"

# ── Deal status labels ──────────────────────────────────────────────────────

STATUS_ACCEPTED_PROFIT = "ACCEPTED (PROFIT)"
STATUS_ACCEPTED_BULK = "ACCEPTED (BULK)"
STATUS_REJECTED = "REJECTED"

# ── Material labels ─────────────────────────────────────────────────────────

LBL_IRON = "Iron"
LBL_GOLD = "Gold"
LBL_DIAMOND = "Diamond"

# ── Prompt messages ─────────────────────────────────────────────────────────

PROMPT_ENTER_RAW_NUMBERS = (
    "   (Enter raw numbers – not stacks. Leave empty to keep stash value.)"
)

# ── Company settings labels ─────────────────────────────────────────────────

LBL_DIAMOND_BLOCKS = "Diamond blocks"
LBL_DIAMOND_ITEMS = "Diamond items"
LBL_IRON_BLOCKS = "Iron blocks"
LBL_IRON_INGOTS = "Iron ingots"
LBL_GOLD_BLOCKS = "Gold blocks"
LBL_GOLD_INGOTS = "Gold ingots"
