import os
import sys
import time
import requests
import logging
from typing import Optional

from src.core import constants
from src.core import database as db
from dotenv import load_dotenv

load_dotenv()

MIN_ACCEPTABLE_PERCENT = constants.MIN_ACCEPTABLE_PERCENT
FALLBACK_PRICES = constants.FALLBACK_PRICES
CACHE_DURATION = constants.CACHE_DURATION
INGOTS_PER_BLOCK = constants.INGOTS_PER_BLOCK
NUGGETS_PER_INGOT = constants.NUGGETS_PER_INGOT
API_TIMEOUT = constants.API_TIMEOUT
API_RETRIES = constants.API_RETRIES
API_RETRY_DELAY = constants.API_RETRY_DELAY

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
            f"{encoded_name}?days=30"
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
