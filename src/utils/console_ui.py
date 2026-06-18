# src/utils/console_ui.py
import os
import sys
import logging
from src.core.market_deal import MarketDeal
from src.core.settings import get_settings
from src.core import database as db

_settings = get_settings()
ITEMS_PER_STACK = _settings.ITEMS_PER_STACK
ITEMS_PER_SHULKER = _settings.ITEMS_PER_SHULKER
INGOTS_PER_BLOCK = _settings.INGOTS_PER_BLOCK

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def clear_screen() -> None:
    """Clear the terminal screen (cross-platform)."""
    os.system("cls" if os.name == "nt" else "clear")


def press_enter_to_continue() -> None:
    """Prompt the user to press Enter before continuing."""
    input("\nPress Enter to continue...")


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------
def safe_float_input(prompt: str, default: float = 0.0) -> float:
    """Read a float from stdin; return *default* on empty or invalid input."""
    try:
        val = input(prompt).strip()
        if val == "":
            return default
        return float(val)
    except ValueError:
        logger.warning("Invalid number input – using %s.", default)
        return default


def safe_int_input(prompt: str, default: int = 0) -> int:
    """Read an int from stdin; return *default* on empty or invalid input."""
    try:
        val = input(prompt).strip()
        if val == "":
            return default
        return int(val)
    except ValueError:
        logger.warning("Invalid number input – using %s.", default)
        return default


def input_unit(name: str, amount: float) -> str:
    """
    Prompt the user for a unit (block/ingot/nugget) for *name*.
    Returns 'ingot' if amount is zero or the input is unrecognised.
    """
    if amount <= 0:
        return "ingot"
    unit = input(f"  -> Unit for {name} (block/ingot/nugget): ").strip().lower()
    if unit not in ("block", "ingot", "nugget"):
        logger.info("Unknown unit '%s' – defaulting to 'ingot'.", unit)
        return "ingot"
    return unit


# ---------------------------------------------------------------------------
# Stash subtraction helper (shared by Mode 1 and Mode 2)
# ---------------------------------------------------------------------------
def _offer_stash_subtraction(iron_ingots: int, gold_ingots: int, diamond_items: int, used_stash: bool = False) -> None:
    """
    After a deal, offer to subtract materials from stash.
    If auto-subtract is ON, do it silently. Otherwise ask.
    """
    total = iron_ingots + gold_ingots + diamond_items
    if total == 0:
        return

    auto_sub = db.get_auto_subtract()

    if auto_sub:
        result = db.subtract_from_stash(iron_ingots, gold_ingots, diamond_items)
        parts = []
        if result["iron_blocks"] or result["iron_ingots"]:
            parts.append(f"Iron: {result['iron_blocks']} blocks + {result['iron_ingots']} ingots")
        if result["gold_blocks"] or result["gold_ingots"]:
            parts.append(f"Gold: {result['gold_blocks']} blocks + {result['gold_ingots']} ingots")
        if result["diamond_blocks"] or result["diamond_items"]:
            parts.append(f"Diamonds: {result['diamond_blocks']} blocks + {result['diamond_items']} items")
        if parts:
            print(f"📦 Auto-subtracted from stash: {', '.join(parts)}")
        return

    # Not auto – ask
    if used_stash:
        default_choice = "y"
        prompt_str = "Subtract these materials from stash? (Y/n): "
    else:
        default_choice = "n"
        prompt_str = "Subtract these materials from stash? (y/N): "

    choice = input(f"\n{prompt_str}").strip().lower()
    if choice == "":
        choice = default_choice

    if choice == "y":
        result = db.subtract_from_stash(iron_ingots, gold_ingots, diamond_items)
        parts = []
        if result["iron_blocks"] or result["iron_ingots"]:
            parts.append(f"Iron: {result['iron_blocks']} blocks + {result['iron_ingots']} ingots")
        if result["gold_blocks"] or result["gold_ingots"]:
            parts.append(f"Gold: {result['gold_blocks']} blocks + {result['gold_ingots']} ingots")
        if result["diamond_blocks"] or result["diamond_items"]:
            parts.append(f"Diamonds: {result['diamond_blocks']} blocks + {result['diamond_items']} items")
        if parts:
            print(f"✅ Subtracted from stash: {', '.join(parts)}")
    else:
        print("⏩ Stash unchanged.")


# ---------------------------------------------------------------------------
# Mode 1 – Deal Calculator
# ---------------------------------------------------------------------------
def deal_calculator(price_iron: float, price_gold: float, price_diamond: float) -> None:
    """Interactive deal calculator – user enters raw material amounts and units."""
    print("\n--- 💰 DEAL CALCULATOR ---")

    # Option to load from stash
    iron_amount, iron_unit = 0.0, "ingot"
    gold_amount, gold_unit = 0.0, "ingot"
    diamond_amount, diamond_unit = 0.0, "ingot"
    used_stash = False

    load_stash_choice = input("\nLoad values from stash? (y/n): ").strip().lower()
    if load_stash_choice == "y":
        stash = db.load_stash()
        if stash and stash.get("updated_at") != "never":
            used_stash = True
            total_iron = stash["iron_blocks"] * INGOTS_PER_BLOCK + stash["iron_ingots"]
            total_gold = stash["gold_blocks"] * INGOTS_PER_BLOCK + stash["gold_ingots"]
            total_diamond = stash["diamond_blocks"] * INGOTS_PER_BLOCK + stash["diamond_items"]
            print(f"\n📦 Loaded from stash:")
            print(f"   Iron:     {MarketDeal.format_bulk_storage(total_iron)}")
            print(f"   Gold:     {MarketDeal.format_bulk_storage(total_gold)}")
            print(f"   Diamonds: {MarketDeal.format_bulk_storage(total_diamond, is_diamond=True)}")

            override_iron = safe_float_input("Override iron amount (leave empty to keep): ")
            if override_iron > 0:
                iron_amount = override_iron
                iron_unit = input_unit("Iron (override)", iron_amount)
            else:
                iron_amount = float(total_iron)

            override_gold = safe_float_input("Override gold amount (leave empty to keep): ")
            if override_gold > 0:
                gold_amount = override_gold
                gold_unit = input_unit("Gold (override)", gold_amount)
            else:
                gold_amount = float(total_gold)

            override_diamond = safe_float_input("Override diamond amount (leave empty to keep): ")
            if override_diamond > 0:
                diamond_amount = override_diamond
                diamond_unit = input_unit("Diamond (override)", diamond_amount)
            else:
                diamond_amount = float(total_diamond)
        else:
            print("⚠ No stash found. Please enter values manually.")
            iron_amount = safe_float_input("\nIron amount (0 if none): ")
            iron_unit = input_unit("Iron", iron_amount)
            gold_amount = safe_float_input("Gold amount (0 if none): ")
            gold_unit = input_unit("Gold", gold_amount)
            diamond_amount = safe_float_input("Diamond amount (0 if none): ")
            diamond_unit = input_unit("Diamond", diamond_amount)
    else:
        iron_amount = safe_float_input("\nIron amount (0 if none): ")
        iron_unit = input_unit("Iron", iron_amount)
        gold_amount = safe_float_input("Gold amount (0 if none): ")
        gold_unit = input_unit("Gold", gold_amount)
        diamond_amount = safe_float_input("Diamond amount (0 if none): ")
        diamond_unit = input_unit("Diamond", diamond_amount)

    iron_ingots = MarketDeal.convert_to_ingots(iron_amount, iron_unit)
    gold_ingots = MarketDeal.convert_to_ingots(gold_amount, gold_unit)
    diamond_items = MarketDeal.convert_to_ingots(diamond_amount, diamond_unit)

    _calculate_and_show_result(
        iron_ingots, gold_ingots, diamond_items,
        price_iron, price_gold, price_diamond,
    )

    # Offer stash subtraction
    _offer_stash_subtraction(int(iron_ingots), int(gold_ingots), int(diamond_items), used_stash)


# ---------------------------------------------------------------------------
# Mode 2 – Shulker Scanner
# ---------------------------------------------------------------------------
def shulker_scanner(price_iron: float, price_gold: float, price_diamond: float) -> None:
    """
    Interactive shulker-box scanner.
    User enters full stacks + remainder for blocks and items of each material.
    """
    print("\n--- 📦 QUICK SHULKER BOX SCANNER ---")

    def get_material_count(name: str, is_block: bool) -> int:
        """Read full stacks and remainder for a material from the user."""
        type_str = "BLOCKS" if is_block else "INGOTS/ITEMS"
        full_stacks = safe_int_input(
            f"  -> Full stacks (64) {name}-{type_str}: "
        )
        rest = safe_int_input(
            f"     Partial remainder stack (0-63) {name}-{type_str}: ",
        )
        total = (full_stacks * ITEMS_PER_STACK) + rest
        return total * INGOTS_PER_BLOCK if is_block else total

    total_diamond = 0
    total_iron = 0
    total_gold = 0
    used_stash = False

    load_stash_choice = input("\nLoad values from stash? (y/n): ").strip().lower()
    if load_stash_choice == "y":
        stash = db.load_stash()
        if stash and stash.get("updated_at") != "never" and (
            stash["iron_blocks"] or stash["iron_ingots"] or
            stash["gold_blocks"] or stash["gold_ingots"] or
            stash["diamond_blocks"] or stash["diamond_items"]
        ):
            used_stash = True
            print(f"\n📦 Loaded from stash (you can override individual values):")

            # Helper: ask override for a value, keep stash if empty
            def _override_val(prompt: str, stash_val: int) -> int:
                raw = input(prompt).strip()
                if raw == "":
                    return stash_val
                try:
                    return int(raw)
                except ValueError:
                    return stash_val

            # Diamond
            di_blocks_count = stash["diamond_blocks"]
            di_items_count = stash["diamond_items"]
            print(f"\n💎 DIAMONDS: {di_blocks_count} blocks, {di_items_count} items")
            print("   (Enter raw numbers – not stacks. Leave empty to keep stash value.)")
            di_blocks_count = _override_val("   Diamond blocks: ", di_blocks_count)
            di_items_count = _override_val("   Diamond items:  ", di_items_count)
            total_diamond = di_blocks_count * INGOTS_PER_BLOCK + di_items_count

            # Iron
            ir_blocks_count = stash["iron_blocks"]
            ir_items_count = stash["iron_ingots"]
            print(f"\n⬜ IRON: {ir_blocks_count} blocks, {ir_items_count} ingots")
            print("   (Enter raw numbers – not stacks. Leave empty to keep stash value.)")
            ir_blocks_count = _override_val("   Iron blocks: ", ir_blocks_count)
            ir_items_count = _override_val("   Iron ingots: ", ir_items_count)
            total_iron = ir_blocks_count * INGOTS_PER_BLOCK + ir_items_count

            # Gold
            go_blocks_count = stash["gold_blocks"]
            go_items_count = stash["gold_ingots"]
            print(f"\n🟨 GOLD: {go_blocks_count} blocks, {go_items_count} ingots")
            print("   (Enter raw numbers – not stacks. Leave empty to keep stash value.)")
            go_blocks_count = _override_val("   Gold blocks: ", go_blocks_count)
            go_items_count = _override_val("   Gold ingots: ", go_items_count)
            total_gold = go_blocks_count * INGOTS_PER_BLOCK + go_items_count
        else:
            print("⚠ No stash found. Please enter values manually.")
            print("\n💎 DIAMONDS:")
            total_diamond = get_material_count("DIAMOND", is_block=True) + \
                            get_material_count("DIAMOND", is_block=False)
            print("\n⬜ IRON:")
            total_iron = get_material_count("IRON", is_block=True) + \
                         get_material_count("IRON", is_block=False)
            print("\n🟨 GOLD:")
            total_gold = get_material_count("GOLD", is_block=True) + \
                         get_material_count("GOLD", is_block=False)
    else:
        print("\n💎 DIAMONDS:")
        total_diamond = get_material_count("DIAMOND", is_block=True) + \
                        get_material_count("DIAMOND", is_block=False)
        print("\n⬜ IRON:")
        total_iron = get_material_count("IRON", is_block=True) + \
                     get_material_count("IRON", is_block=False)
        print("\n🟨 GOLD:")
        total_gold = get_material_count("GOLD", is_block=True) + \
                     get_material_count("GOLD", is_block=False)

    multiplier = safe_int_input(
        "\nHow many times is this chest configuration delivered? (Multiplier, default = 1): ",
        default=1,
    )

    iron_ingots = total_iron * multiplier
    gold_ingots = total_gold * multiplier
    diamond_items = total_diamond * multiplier

    _calculate_and_show_result(
        iron_ingots, gold_ingots, diamond_items,
        price_iron, price_gold, price_diamond,
    )

    # Offer stash subtraction
    _offer_stash_subtraction(int(iron_ingots), int(gold_ingots), int(diamond_items), used_stash)


# ---------------------------------------------------------------------------
# Core calculation & result display (shared by Mode 1 and Mode 2)
# ---------------------------------------------------------------------------
def _calculate_and_show_result(
    iron_ingots: float,
    gold_ingots: float,
    diamond_items: float,
    price_iron: float,
    price_gold: float,
    price_diamond: float,
) -> None:
    """
    Compute the market value, compare against the user's offered price,
    display the result, and log the deal to CSV.
    """
    total_market_value = (
        (iron_ingots * price_iron)
        + (gold_ingots * price_gold)
        + (diamond_items * price_diamond)
    )
    min_needed_price = total_market_value * MarketDeal.MIN_ACCEPTABLE_PERCENT

    # Intermediate summary
    print("\n" + "-" * 40)
    print(f"📊 INTERIM TOTAL (Market Value): {total_market_value:.2f}$")
    print(f"📉 Your Minimum (incl. discount): {min_needed_price:.2f}$")
    print("-" * 40)

    offered_price = safe_float_input("\nWhat is the buyer offering for these goods? ($): ")

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
            f"OK! Within bulk discount range "
            f"(discount: {abs(profit_loss):.2f}$)"
        )
    else:
        status = "REJECTED"
        status_emoji = "🟥"
        status_msg = (
            f"TOO CHEAP! You are missing "
            f"{min_needed_price - offered_price:.2f}$ to reach your limit."
        )

    # Output
    print("\n" + "=" * 60)
    print(
        f"PROJECT: Bulk Trading Analyzer v3.1 (Live Price Check)\n"
        f"Prices: Fe: {price_iron:.2f}$ | Au: {price_gold:.2f}$ | "
        f"Di: {price_diamond:.2f}$"
    )
    print("=" * 60)

    print("\n== DELIVERY CONTENTS ==")
    print(f"📦 Iron total:      {MarketDeal.format_bulk_storage(iron_ingots)}")
    print(f"📦 Gold total:      {MarketDeal.format_bulk_storage(gold_ingots)}")
    print(f"📦 Diamond total:   {MarketDeal.format_bulk_storage(diamond_items, is_diamond=True)}")
    print(
        f"🚚 Shipping volume: ~{stacks:.1f} stacks "
        f"({shulkers:.2f} shulker boxes)"
    )

    if stacks > 0:
        print(f"📊 Margin:          {profit_loss / stacks:.2f}$ per stack | {profit_loss / shulkers:.2f}$ per shulker")

    print("\n== FINANCIAL CHECK ==")
    print(f"Market value:    {total_market_value:.2f}$")
    print(f"Offered price:   {offered_price:.2f}$ ({percent_of_market:.1f}% of market)")
    print(f"Your limit ({MarketDeal.MIN_ACCEPTABLE_PERCENT * 100:.0f}%): {min_needed_price:.2f}$")
    print("-" * 40)
    print(f"{status_emoji} {status}")
    print(f"   {status_msg}")

    # Smart counter-offer logic on rejection
    if status == "REJECTED":
        diamond_value = diamond_items * price_diamond
        remaining_budget = offered_price - diamond_value
        total_metals = iron_ingots + gold_ingots

        if total_metals > 0 and remaining_budget > 0:
            ratio = iron_ingots / total_metals
            fair_metals = remaining_budget / ((ratio * price_iron) + ((1 - ratio) * price_gold))

            print("\n💡 COUNTER-OFFER SUGGESTION:")
            print(f"For ${offered_price:.0f}, offer instead just the following:")
            if iron_ingots > 0: print(f" -> Iron:      {MarketDeal.format_bulk_storage(fair_metals * ratio)}")
            if gold_ingots > 0: print(f" -> Gold:      {MarketDeal.format_bulk_storage(fair_metals * (1 - ratio))}")
            if diamond_items > 0: print(f" -> Diamonds:  {MarketDeal.format_bulk_storage(diamond_items, is_diamond=True)} (unchanged)")
        elif remaining_budget <= 0 and total_market_value > 0:
            print("\n💡 COUNTER-OFFER NOT POSSIBLE: The offer doesn't even cover the diamond value!")

    MarketDeal.log_deal(
        iron_ingots, gold_ingots, diamond_items,
        total_market_value, offered_price, status,
        price_iron, price_gold, price_diamond,
    )
    print(f"\n💾 Deal saved to database ({_settings.DB_FILE}).")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Mode 3 – Quick Converter (enhanced with live-price estimates)
# ---------------------------------------------------------------------------
def quick_converter(
    price_iron: float,
    price_gold: float,
    price_diamond: float,
) -> None:
    """
    Quick unit converter – converts item amounts into blocks, stacks and shulkers.
    Also shows the estimated market value for each material.
    """
    print("\n--- ⚡ QUICK CONVERTER ---")

    base_amount = safe_int_input("How many ingots/items per load? (e.g. 1500): ")
    multiplier = safe_int_input(
        "How many times is this load needed? (Multiplier, default = 1): ",
        default=1,
    )

    amount = base_amount * multiplier
    blocks = amount // INGOTS_PER_BLOCK
    rest_ingots = amount % INGOTS_PER_BLOCK
    stacks = amount // ITEMS_PER_STACK
    rest_items = amount % ITEMS_PER_STACK
    shulkers = amount / ITEMS_PER_SHULKER

    # Estimate market value in each material for context
    iron_value = amount * price_iron
    gold_value = amount * price_gold
    diamond_value = amount * price_diamond

    print("\n================ CONVERSION ================")
    print(f"Amount per load:  {base_amount} × {multiplier}")
    print(f"Total items:      {amount}")
    print("--------------------------------------------")
    print(f"As blocks:       {blocks} blocks + {rest_ingots} ingots")
    print(f"As stacks:       {stacks} stacks + {rest_items} items")
    print(f"In shulkers:     ~{shulkers:.2f} shulker boxes")
    print("--------------------------------------------")
    print(f"💰 Estimated market value (current live prices):")
    print(f"   Iron:     {iron_value:>10.2f}$")
    print(f"   Gold:      {gold_value:>10.2f}$")
    print(f"   Diamonds: {diamond_value:>10.2f}$")
    print("============================================")


# ---------------------------------------------------------------------------
# Mode 4 – Stash Manager
# ---------------------------------------------------------------------------
def stash_manager(price_iron: float, price_gold: float, price_diamond: float) -> None:
    """Manage the saved inventory stash."""
    while True:
        clear_screen()
        print("=" * 50)
        print("     📦 STASH MANAGER")
        print("=" * 50)
        stash = db.load_stash()

        # Calculate ingot equivalents for display
        total_iron = stash["iron_blocks"] * INGOTS_PER_BLOCK + stash["iron_ingots"]
        total_gold = stash["gold_blocks"] * INGOTS_PER_BLOCK + stash["gold_ingots"]
        total_diamond = stash["diamond_blocks"] * INGOTS_PER_BLOCK + stash["diamond_items"]

        # Market value
        iron_value = total_iron * price_iron
        gold_value = total_gold * price_gold
        diamond_value = total_diamond * price_diamond
        total_value = iron_value + gold_value + diamond_value

        stacks = (total_iron + total_gold + total_diamond) / float(ITEMS_PER_STACK)
        shulkers = (total_iron + total_gold + total_diamond) / float(ITEMS_PER_SHULKER)

        auto_sub = bool(stash.get("auto_subtract", 0))

        print(f"\n📦 CURRENT STASH (last updated: {stash.get('updated_at', 'never')})")
        print("-" * 40)
        print(f"  Iron:     {stash['iron_blocks']} blocks + {stash['iron_ingots']} ingots")
        print(f"           ({MarketDeal.format_bulk_storage(total_iron)})")
        print(f"  Gold:     {stash['gold_blocks']} blocks + {stash['gold_ingots']} ingots")
        print(f"           ({MarketDeal.format_bulk_storage(total_gold)})")
        print(f"  Diamonds: {stash['diamond_blocks']} blocks + {stash['diamond_items']} items")
        print(f"           ({MarketDeal.format_bulk_storage(total_diamond, is_diamond=True)})")
        print("-" * 40)
        print(f"📊 Market value:  ${total_value:.2f}")
        print(f"   Iron:     ${iron_value:.2f}")
        print(f"   Gold:     ${gold_value:.2f}")
        print(f"   Diamonds: ${diamond_value:.2f}")
        print(f"🚚 Shipping:     ~{stacks:.1f} stacks (~{shulkers:.2f} shulker boxes)")
        print(f"⚙  Auto-subtract: {'ON ✅' if auto_sub else 'OFF ❌'}")
        print("=" * 50)

        print("\n  [1] Update stash (enter new values)")
        print("  [2] Clear stash (reset to zero)")
        print(f"  [3] Toggle auto-subtract (currently {'ON' if auto_sub else 'OFF'})")
        print("  [4] Back to main menu")
        choice = input("  Choice (1/2/3/4): ").strip()

        if choice == "1":
            print("\n--- Enter your current inventory ---")
            print("(Values are in blocks / ingots / items, NOT stacks)")
            iron_blocks = safe_int_input("Iron blocks: ")
            iron_ingots = safe_int_input("Iron ingots: ")
            gold_blocks = safe_int_input("Gold blocks: ")
            gold_ingots = safe_int_input("Gold ingots: ")
            diamond_blocks = safe_int_input("Diamond blocks: ")
            diamond_items = safe_int_input("Diamond items: ")

            new_stash = {
                "iron_blocks": iron_blocks,
                "iron_ingots": iron_ingots,
                "gold_blocks": gold_blocks,
                "gold_ingots": gold_ingots,
                "diamond_blocks": diamond_blocks,
                "diamond_items": diamond_items,
                "auto_subtract": 1 if auto_sub else 0,
            }
            db.save_stash(new_stash)
            print("\n✅ Stash updated!")

        elif choice == "2":
            confirm = input("Are you sure you want to clear the stash? (y/n): ").strip().lower()
            if confirm == "y":
                db.clear_stash()
                print("\n✅ Stash cleared!")
            else:
                print("\n⏩ Canceled.")

        elif choice == "3":
            db.set_auto_subtract(not auto_sub)
            print(f"\nAuto-subtract is now {'ON ✅' if not auto_sub else 'OFF ❌'}")

        elif choice == "4":
            break
        else:
            logger.warning("Invalid choice '%s'.", choice)

        if choice in ("1", "2", "3"):
            press_enter_to_continue()


# ---------------------------------------------------------------------------
# Main menu & navigation loop
# ---------------------------------------------------------------------------
def main_loop() -> None:
    """Display the main menu and route to the selected mode. Loops until the user quits."""

    while True:
        clear_screen()
        print("=" * 50)
        print("     DEMOCRACYCRAFT TOOLBOX v3.2")
        print("=" * 50)
        print("  [1] Deal Calculator (enter total amounts)")
        print("  [2] Shulker Box Scanner (enter FULL STACKS)")
        print("  [3] Quick Converter (split desired amounts)")
        print("  [4] 📦 Stash Manager (saved inventory)")
        print("  [5] ❌ Exit")
        choice = input("  Choice (1/2/3/4/5): ").strip()

        if choice == "5":
            print("\nGoodbye! 👋")
            break

        # Fetch / refresh prices for all modes that need them
        if choice in ("1", "2", "3", "4"):
            print("\n⏳ Loading current prices ...")
            cache = MarketDeal.load_cache()
            price_iron = MarketDeal.get_price("Iron Ingot", cache)
            price_gold = MarketDeal.get_price("Gold Ingot", cache)
            price_diamond = MarketDeal.get_price("Diamond", cache)
            MarketDeal.save_cache(cache)
            print("✓ Prices loaded.\n")
        else:
            logger.warning("Invalid menu choice '%s'.", choice)
            press_enter_to_continue()
            continue

        if choice == "1":
            deal_calculator(price_iron, price_gold, price_diamond)
        elif choice == "2":
            shulker_scanner(price_iron, price_gold, price_diamond)
        elif choice == "3":
            quick_converter(price_iron, price_gold, price_diamond)
        elif choice == "4":
            stash_manager(price_iron, price_gold, price_diamond)

        press_enter_to_continue()