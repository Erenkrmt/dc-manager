# src/core/constants.py
import os
from dotenv import load_dotenv

load_dotenv()

# Database
DB_DIR = "data"
DB_FILE = os.path.join(DB_DIR, "dc_trade.db")
os.makedirs(DB_DIR, exist_ok=True)

# Company branding – set COMPANY_NAME in .env to customise every display string
COMPANY_NAME = os.getenv("COMPANY_NAME", "Fishy Business")

# Price cache
CACHE_DURATION = 6 * 60 * 60  # 6 hours in seconds

# Trading thresholds
MIN_ACCEPTABLE_PERCENT = 0.85

# Minecraft item units
ITEMS_PER_STACK = 64
ITEMS_PER_SHULKER = 1728  # 27 stacks * 64
INGOTS_PER_BLOCK = 9
NUGGETS_PER_INGOT = 9

# API settings
API_TIMEOUT = 10
API_RETRIES = 3
API_RETRY_DELAY = 2  # seconds

# Fallback prices
FALLBACK_PRICES = {
    "Iron Ingot": 1.20,
    "Gold Ingot": 2.50,
    "Diamond": 15.00,
}

# ---------------------------------------------------------------------------
# Item import mapping – used by the "Import from List" stash feature
# Maps raw item names (as they appear in the game dump) to stash database fields.
# To add a new tracked resource, simply add an entry here; the stash table will
# need a corresponding column (with a migration in database.py).
# ---------------------------------------------------------------------------
IMPORT_ITEM_MAPPING = {
    "Block of Raw Iron":   "raw_iron_blocks",
    "Block of Iron":        "iron_blocks",
    "Iron Ingot":           "iron_ingots",
    "Block of Raw Gold":    "raw_gold_blocks",
    "Block of Gold":        "gold_blocks",
    "Gold Ingot":           "gold_ingots",
    "Block of Diamond":     "diamond_blocks",
    "Diamond":              "diamond_items",
}
# If an item value ends with one of these suffixes, multiply the count by the factor.
# Useful for items that are counted differently in the dump vs. stored in the stash.
IMPORT_ITEM_FACTORS = {
    # Example (uncomment when needed):
    # "nugget": 1 / NUGGETS_PER_INGOT,
}