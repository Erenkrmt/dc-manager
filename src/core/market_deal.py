# src/core/market_deal.py
"""
Core business logic for the DemocracyCraft Trading Toolbox.
Price fetching, unit conversions, deal analysis, and stash utilities.
"""

import os
import sys
import time
import logging
from urllib.parse import quote

import requests

from src.core.settings import get_settings
from src.core import database as db

_settings = get_settings()

MIN_ACCEPTABLE_PERCENT = _settings.MIN_ACCEPTABLE_PERCENT
FALLBACK_PRICES = _settings.FALLBACK_PRICES
CACHE_DURATION = _settings.CACHE_DURATION
INGOTS_PER_BLOCK = _settings.INGOTS_PER_BLOCK
NUGGETS_PER_INGOT = _settings.NUGGETS_PER_INGOT
API_TIMEOUT = _settings.API_TIMEOUT
API_RETRIES = _settings.API_RETRIES
API_RETRY_DELAY = _settings.API_RETRY_DELAY
PRICE_DAYS_LOOKBACK = _settings.PRICE_DAYS_LOOKBACK
ITEMS_PER_STACK = _settings.ITEMS_PER_STACK
ITEMS_PER_SHULKER = _settings.ITEMS_PER_SHULKER

logger = logging.getLogger(__name__)


def get_api_key() -> str:
    """Return the API key from the environment variable."""
    api_key = os.getenv("DC_API_KEY")
    if not api_key:
        logger.error(
            "❌ NO API KEY FOUND! Please set 'DC_API_KEY=your_key' in your .env file."
        )
        sys.exit(1)
    return api_key


# ═══════════════════════════════════════════════════════════════════════════
# Deal Analysis — shared by both CLI and Web UI
# ═══════════════════════════════════════════════════════════════════════════


def analyze_deal(
    iron_ingots: float,
    gold_ingots: float,
    diamond_items: float,
    price_iron: float,
    price_gold: float,
    price_diamond: float,
    offered_price: float | None = None,
) -> dict:
    """
    Compute market value, status, profit, and shipping info for a deal.

    Returns a dict with keys:
      market_value, min_needed_price, offered_price, percent_of_market,
      profit_loss, status, status_emoji, status_msg, stacks, shulkers,
      counter_offer (optional)
    """
    total_market_value = (
        (iron_ingots * price_iron)
        + (gold_ingots * price_gold)
        + (diamond_items * price_diamond)
    )
    min_needed_price = total_market_value * MIN_ACCEPTABLE_PERCENT
    offered_price = offered_price or 0.0

    percent_of_market = (
        (offered_price / total_market_value) * 100 if total_market_value > 0 else 0
    )
    profit_loss = offered_price - total_market_value

    stacks = (iron_ingots + gold_ingots + diamond_items) / float(ITEMS_PER_STACK)
    shulkers = (iron_ingots + gold_ingots + diamond_items) / float(ITEMS_PER_SHULKER)

    # Determine deal status
    if offered_price >= total_market_value:
        status = "ACCEPTED (PROFIT)"
        status_emoji = "🟩"
        status_msg = f"SUPER DEAL! +{profit_loss:.2f}$ profit over market price."
    elif offered_price >= min_needed_price:
        status = "ACCEPTED (BULK)"
        status_emoji = "🟨"
        status_msg = (
            f"OK! Within bulk discount range (discount: {abs(profit_loss):.2f}$)"
        )
    else:
        status = "REJECTED"
        status_emoji = "🟥"
        status_msg = (
            f"TOO CHEAP! You are missing "
            f"{min_needed_price - offered_price:.2f}$ to reach your limit."
        )

    result: dict = {
        "market_value": total_market_value,
        "min_needed_price": min_needed_price,
        "offered_price": offered_price,
        "percent_of_market": percent_of_market,
        "profit_loss": profit_loss,
        "status": status,
        "status_emoji": status_emoji,
        "status_msg": status_msg,
        "stacks": stacks,
        "shulkers": shulkers,
        "iron_ingots": iron_ingots,
        "gold_ingots": gold_ingots,
        "diamond_items": diamond_items,
        "price_iron": price_iron,
        "price_gold": price_gold,
        "price_diamond": price_diamond,
    }

    # Smart counter-offer logic on rejection
    if status == "REJECTED":
        diamond_value = diamond_items * price_diamond
        remaining_budget = offered_price - diamond_value
        total_metals = iron_ingots + gold_ingots

        if total_metals > 0 and remaining_budget > 0:
            ratio = iron_ingots / total_metals
            fair_metals = remaining_budget / (
                (ratio * price_iron) + ((1 - ratio) * price_gold)
            )
            result["counter_offer"] = {
                "iron": fair_metals * ratio if iron_ingots > 0 else 0,
                "gold": fair_metals * (1 - ratio) if gold_ingots > 0 else 0,
                "diamond": diamond_items if diamond_items > 0 else 0,
            }
        elif remaining_budget <= 0 and total_market_value > 0:
            result["counter_offer"] = None

    return result


def stash_ingot_equivalents(stash: dict) -> tuple[int, int, int]:
    """
    Calculate total ingot/items from a stash dict.
    Returns (total_iron_ingots, total_gold_ingots, total_diamond_items).
    """
    total_iron = (
        stash.get("iron_blocks", 0) + stash.get("raw_iron_blocks", 0)
    ) * INGOTS_PER_BLOCK + stash.get("iron_ingots", 0)
    total_gold = (
        stash.get("gold_blocks", 0) + stash.get("raw_gold_blocks", 0)
    ) * INGOTS_PER_BLOCK + stash.get("gold_ingots", 0)
    total_diamond = stash.get("diamond_blocks", 0) * INGOTS_PER_BLOCK + stash.get(
        "diamond_items", 0
    )
    return total_iron, total_gold, total_diamond


def format_subtract_result(result: dict) -> str:
    """Format a stash subtraction result dict into a human-readable string."""
    parts = []
    if result.get("iron_blocks") or result.get("iron_ingots"):
        parts.append(
            f"Iron: {result['iron_blocks']} blocks + {result['iron_ingots']} ingots"
        )
    if result.get("gold_blocks") or result.get("gold_ingots"):
        parts.append(
            f"Gold: {result['gold_blocks']} blocks + {result['gold_ingots']} ingots"
        )
    if result.get("diamond_blocks") or result.get("diamond_items"):
        parts.append(
            f"Diamonds: {result['diamond_blocks']} blocks + {result['diamond_items']} items"
        )
    return ", ".join(parts)


def handle_stash_subtraction(
    iron_ingots: int,
    gold_ingots: int,
    diamond_items: int,
    company_id: int = 1,
    auto_confirm: bool = False,
) -> dict | None:
    """
    Handle stash subtraction after a deal.

    If auto_confirm is True, subtracts silently.
    Otherwise, returns a dict with subtraction info without subtracting
    (caller must handle prompt).

    Returns a dict with subtraction result if subtraction happened,
    or None if no subtraction was needed (total == 0).
    """
    total = iron_ingots + gold_ingots + diamond_items
    if total == 0:
        return None

    auto_sub = db.get_auto_subtract(company_id=company_id)

    if auto_sub or auto_confirm:
        result = db.subtract_from_stash(
            iron_ingots, gold_ingots, diamond_items, company_id=company_id
        )
        return result

    return {"pending": True}


def fetch_live_prices(cache: dict | None = None) -> tuple[float, float, float, dict]:
    """
    Fetch current prices for Iron Ingot, Gold Ingot, and Diamond.
    Returns (price_iron, price_gold, price_diamond, cache).
    """
    if cache is None:
        cache = MarketDeal.load_cache()
    p_iron = MarketDeal.get_price("Iron Ingot", cache)
    p_gold = MarketDeal.get_price("Gold Ingot", cache)
    p_diamond = MarketDeal.get_price("Diamond", cache)
    MarketDeal.save_cache(cache)
    return p_iron, p_gold, p_diamond, cache


def stash_market_value(stash: dict, prices: tuple[float, float, float]) -> float:
    """
    Calculate the total market value of a stash given (price_iron, price_gold, price_diamond).
    """
    total_iron, total_gold, total_diamond = stash_ingot_equivalents(stash)
    p_iron, p_gold, p_diamond = prices
    return total_iron * p_iron + total_gold * p_gold + total_diamond * p_diamond


def total_stash_shipping(stash: dict) -> tuple[float, float]:
    """
    Calculate shipping volume (stacks, shulkers) for a stash.
    """
    total_iron, total_gold, total_diamond = stash_ingot_equivalents(stash)
    total = total_iron + total_gold + total_diamond
    stacks = total / float(ITEMS_PER_STACK)
    shulkers = total / float(ITEMS_PER_SHULKER)
    return stacks, shulkers


class MarketDeal:
    """Core class for bulk trading calculations and API interactions."""

    MIN_ACCEPTABLE_PERCENT: float = MIN_ACCEPTABLE_PERCENT

    # ------------------------------------------------------------------
    # Cache helpers (delegated to SQLite via database module)
    # ------------------------------------------------------------------
    @staticmethod
    def load_cache() -> dict:
        return db.load_cache()

    @staticmethod
    def save_cache(cache_data: dict) -> None:
        db.save_cache(cache_data)

    # ------------------------------------------------------------------
    # Price fetching with retry logic
    # ------------------------------------------------------------------
    @staticmethod
    def get_price(item_name: str, cache: dict) -> float:
        """
        Fetch the current market price for *item_name* via the DemocracyCraft API.
        Uses in-memory caching (CACHE_DURATION) to avoid excessive API calls.
        Falls back to hardcoded default prices if all attempts fail.
        """
        current_time = time.time()

        # Return cached value if still valid
        if item_name in cache:
            entry = cache[item_name]
            if current_time - entry["timestamp"] < CACHE_DURATION:
                return entry["price"]

        logger.info("Fetching live price for '%s' …", item_name)
        encoded_name = quote(item_name.strip(), safe="")

        api_key = get_api_key()
        url = (
            f"https://api.democracycraft.net/economy/api/v1/chestshop/items/"
            f"{encoded_name}?days={PRICE_DAYS_LOOKBACK}"
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

        fetched_price: float | None = None

        # Retry loop
        for attempt in range(1, API_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    avg = data.get("avgUnitPrice")
                    if avg:
                        fetched_price = float(avg)
                        break

                    shops = data.get("cheapestShops", [])
                    if shops:
                        prices = [
                            float(s["buyPrice"])
                            for s in shops
                            if s.get("buyPrice") is not None
                        ]
                        if prices:
                            fetched_price = min(prices)
                            break

                logger.warning(
                    "API attempt %d/%d – Status %s",
                    attempt,
                    API_RETRIES,
                    response.status_code,
                )

            except requests.RequestException as exc:
                logger.warning(
                    "API attempt %d/%d – Error: %s",
                    attempt,
                    API_RETRIES,
                    exc,
                )

            # Wait before retrying (skip on the last attempt)
            if attempt < API_RETRIES:
                time.sleep(API_RETRY_DELAY)

        # Fallback if every attempt failed
        if fetched_price is None:
            logger.warning(
                "All API attempts failed. Using fallback price for %s.",
                item_name,
            )
            fetched_price = FALLBACK_PRICES.get(item_name, 5.00)

        cache[item_name] = {"price": fetched_price, "timestamp": current_time}
        return fetched_price

    # ------------------------------------------------------------------
    # Unit conversions
    # ------------------------------------------------------------------
    @staticmethod
    def convert_to_ingots(amount: float, unit: str) -> float:
        """Convert an amount in blocks/nuggets to its ingot equivalent."""
        if amount == 0:
            return 0.0
        unit = unit.lower()
        if unit == "block":
            return amount * INGOTS_PER_BLOCK
        if unit == "nugget":
            return amount / NUGGETS_PER_INGOT
        # Default: ingot (no conversion needed)
        return amount

    @staticmethod
    def format_bulk_storage(total_items: float, is_diamond: bool = False) -> str:
        """
        Format a total item count into a human-readable block/ingot representation.
        """
        total = int(total_items)
        if total == 0:
            return "0 Items"
        blocks = total // INGOTS_PER_BLOCK
        rest = total % INGOTS_PER_BLOCK
        unit_name = "Diamonds" if is_diamond else "Ingots"
        if rest > 0:
            return f"{blocks} blocks + {rest} {unit_name}"
        return f"{blocks} blocks"

    # ------------------------------------------------------------------
    # Deal logging (delegated to SQLite via database module)
    # ------------------------------------------------------------------
    @staticmethod
    def log_deal(
        iron: float,
        gold: float,
        diamonds: float,
        market_value: float,
        offered_val: float,
        status: str,
        iron_price: float = 0.0,
        gold_price: float = 0.0,
        diamond_price: float = 0.0,
        company_id: int = 1,
    ) -> None:
        """Log a deal to the SQLite database."""
        db.log_deal(
            iron,
            gold,
            diamonds,
            market_value,
            offered_val,
            status,
            iron_price,
            gold_price,
            diamond_price,
            company_id=company_id,
        )

    # ------------------------------------------------------------------
    # Item lookup (any item via API)
    # ------------------------------------------------------------------
    @staticmethod
    def lookup_item(item_name: str, cache: dict) -> dict:
        """
        Look up an arbitrary item via the DemocracyCraft API.
        Returns a dict with keys: item_name, avg_unit_price, cheapest_shops,
        total_trades, all_prices, min_price, max_price.
        Caches the avg_unit_price under 'item_name' in the cache dict.
        Falls back gracefully on failure.
        """
        current_time = time.time()

        # Return cached avg price if still valid
        if item_name in cache:
            entry = cache[item_name]
            if current_time - entry["timestamp"] < CACHE_DURATION:
                return {
                    "item_name": item_name,
                    "avg_unit_price": entry["price"],
                    "cached": True,
                }

        logger.info("Looking up item '%s' …", item_name)
        encoded_name = quote(item_name.strip(), safe="")

        api_key = get_api_key()
        url = (
            f"https://api.democracycraft.net/economy/api/v1/chestshop/items/"
            f"{encoded_name}?days={PRICE_DAYS_LOOKBACK}"
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

        result: dict | None = None

        for attempt in range(1, API_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    avg = data.get("avgUnitPrice")
                    shops = data.get("cheapestShops", [])
                    all_prices = []
                    for s in shops:
                        if s.get("buyPrice") is not None:
                            all_prices.append(float(s["buyPrice"]))

                    result = {
                        "item_name": item_name,
                        "avg_unit_price": float(avg) if avg else None,
                        "cheapest_shops": shops,
                        "total_trades": data.get("totalTrades", 0),
                        "all_prices": all_prices,
                        "min_price": min(all_prices) if all_prices else None,
                        "max_price": max(all_prices) if all_prices else None,
                        "shop_count": len(shops),
                        "cached": False,
                    }

                    # Cache the avg price for future quick lookups
                    if avg:
                        cache[item_name] = {
                            "price": float(avg),
                            "timestamp": current_time,
                        }

                    logger.info(
                        "Item '%s' — avg: %s, shops: %d, trades: %s",
                        item_name,
                        f"${float(avg):.2f}" if avg else "N/A",
                        len(shops),
                        data.get("totalTrades", "N/A"),
                    )
                    break

                logger.warning(
                    "API attempt %d/%d – Status %s",
                    attempt,
                    API_RETRIES,
                    response.status_code,
                )

            except requests.RequestException as exc:
                logger.warning(
                    "API attempt %d/%d – Error: %s",
                    attempt,
                    API_RETRIES,
                    exc,
                )

            if attempt < API_RETRIES:
                time.sleep(API_RETRY_DELAY)

        # Fallback
        if result is None:
            fallback_price = FALLBACK_PRICES.get(item_name, None)
            if fallback_price is not None:
                logger.warning("Using fallback price for '%s'.", item_name)
                result = {
                    "item_name": item_name,
                    "avg_unit_price": fallback_price,
                    "cheapest_shops": [],
                    "total_trades": 0,
                    "all_prices": [],
                    "min_price": fallback_price,
                    "max_price": fallback_price,
                    "shop_count": 0,
                    "cached": False,
                }
            else:
                logger.warning("No data available for '%s'.", item_name)
                result = {
                    "item_name": item_name,
                    "avg_unit_price": None,
                    "cheapest_shops": [],
                    "total_trades": 0,
                    "all_prices": [],
                    "min_price": None,
                    "max_price": None,
                    "shop_count": 0,
                    "cached": False,
                    "error": "No price data available for this item.",
                }

        return result
