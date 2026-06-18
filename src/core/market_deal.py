import os
import sys
import time
import requests
import logging
from typing import Optional

from src.core.settings import get_settings
from src.core import database as db
from dotenv import load_dotenv

load_dotenv()

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

logger = logging.getLogger(__name__)


def get_api_key() -> str:
    """Return the API key from the environment variable."""
    api_key = os.getenv("DC_API_KEY")
    if not api_key:
        logger.error(
            "❌ NO API KEY FOUND! "
            "Please set 'DC_API_KEY=your_key' in your .env file."
        )
        sys.exit(1)
    return api_key


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
        encoded_name = item_name.replace(" ", "%20").strip()

        api_key = get_api_key()
        url = (
            f"https://api.democracycraft.net/economy/api/v1/chestshop/items/"
            f"{encoded_name}?days={PRICE_DAYS_LOOKBACK}"
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

        fetched_price: Optional[float] = None

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
                    attempt, API_RETRIES, response.status_code,
                )

            except requests.RequestException as exc:
                logger.warning(
                    "API attempt %d/%d – Error: %s",
                    attempt, API_RETRIES, exc,
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
    ) -> None:
        """Log a deal to the SQLite database."""
        db.log_deal(iron, gold, diamonds, market_value, offered_val, status,
                    iron_price, gold_price, diamond_price)

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
        encoded_name = item_name.replace(" ", "%20").strip()

        api_key = get_api_key()
        url = (
            f"https://api.democracycraft.net/economy/api/v1/chestshop/items/"
            f"{encoded_name}?days={PRICE_DAYS_LOOKBACK}"
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

        result: Optional[dict] = None

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
                    attempt, API_RETRIES, response.status_code,
                )

            except requests.RequestException as exc:
                logger.warning(
                    "API attempt %d/%d – Error: %s",
                    attempt, API_RETRIES, exc,
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
