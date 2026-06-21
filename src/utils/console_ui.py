# src/utils/console_ui.py
"""
Main CLI loop for the DemocracyCraft Trading Toolbox.

Routes to the four interactive modes and handles the top-level menu.
Session state (company_id, read-only flag) is managed via a
:class:`SessionContext` dataclass imported from :mod:`src.utils.session`.
"""

from __future__ import annotations

import logging

from src.core.market_deal import (
    MarketDeal,
    analyze_deal,
    format_subtract_result,
    handle_stash_subtraction,
    fetch_live_prices,
)
from src.core.settings import get_settings
from src.core import database as db
from src.utils.input_helpers import (
    safe_int_input,
    safe_float_input,
    input_unit,
    clear_screen,
    press_enter_to_continue,
)
from src.utils.session import SessionContext, resolve_company
from src.utils.stash_helpers import (
    load_materials_from_stash,
    prompt_material_values_manual,
)

_settings = get_settings()
ITEMS_PER_STACK = _settings.ITEMS_PER_STACK
ITEMS_PER_SHULKER = _settings.ITEMS_PER_SHULKER
INGOTS_PER_BLOCK = _settings.INGOTS_PER_BLOCK

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stash subtraction helper (shared by Mode 1 and Mode 2)
# ---------------------------------------------------------------------------
def _offer_stash_subtraction(
    ctx: SessionContext,
    iron_ingots: int,
    gold_ingots: int,
    diamond_items: int,
    used_stash: bool = False,
) -> None:
    """
    After a deal, offer to subtract materials from stash.
    If auto-subtract is ON, do it silently. Otherwise ask.
    """
    result = handle_stash_subtraction(
        iron_ingots,
        gold_ingots,
        diamond_items,
        company_id=ctx.company_id,
    )
    if result is None:
        return

    if "pending" in result:
        # Not auto – ask user
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
            result = db.subtract_from_stash(
                iron_ingots, gold_ingots, diamond_items, company_id=ctx.company_id
            )
            formatted = format_subtract_result(result)
            if formatted:
                print(f"✅ Subtracted from stash: {formatted}")
        else:
            print("⏩ Stash unchanged.")
        return

    formatted = format_subtract_result(result)
    if formatted:
        print(f"📦 Auto-subtracted from stash: {formatted}")


def _get_material_count(name: str, is_block: bool) -> int:
    """Read full stacks and remainder for a material from the user."""
    type_str = "BLOCKS" if is_block else "INGOTS/ITEMS"
    full_stacks = safe_int_input(f"  -> Full stacks (64) {name}-{type_str}: ")
    rest = safe_int_input(
        f"     Partial remainder stack (0-63) {name}-{type_str}: ",
    )
    total = (full_stacks * ITEMS_PER_STACK) + rest
    return total * INGOTS_PER_BLOCK if is_block else total


# ---------------------------------------------------------------------------
# Mode 1 – Deal Calculator
# ---------------------------------------------------------------------------
def deal_calculator(
    ctx: SessionContext,
    price_iron: float,
    price_gold: float,
    price_diamond: float,
) -> None:
    """Interactive deal calculator – user enters raw material amounts and units."""
    print("\n--- 💰 DEAL CALCULATOR ---")

    used_stash = False
    load_stash_choice = input("\nLoad values from stash? (y/n): ").strip().lower()
    if load_stash_choice == "y":
        total_iron, total_gold, total_diamond, used_stash = load_materials_from_stash(
            ctx
        )
        if used_stash:
            print("\n📦 Loaded from stash:")
            print(f"   Iron:     {MarketDeal.format_bulk_storage(total_iron)}")
            print(f"   Gold:     {MarketDeal.format_bulk_storage(total_gold)}")
            print(
                f"   Diamonds: {MarketDeal.format_bulk_storage(total_diamond, is_diamond=True)}"
            )

            override_iron = safe_float_input(
                "Override iron amount (leave empty to keep): "
            )
            if override_iron > 0:
                iron_amount = override_iron
                iron_unit = input_unit("Iron (override)", iron_amount)
                iron_ingots = MarketDeal.convert_to_ingots(iron_amount, iron_unit)
            else:
                iron_ingots = float(total_iron)

            override_gold = safe_float_input(
                "Override gold amount (leave empty to keep): "
            )
            if override_gold > 0:
                gold_amount = override_gold
                gold_unit = input_unit("Gold (override)", gold_amount)
                gold_ingots = MarketDeal.convert_to_ingots(gold_amount, gold_unit)
            else:
                gold_ingots = float(total_gold)

            override_diamond = safe_float_input(
                "Override diamond amount (leave empty to keep): "
            )
            if override_diamond > 0:
                diamond_amount = override_diamond
                diamond_unit = input_unit("Diamond (override)", diamond_amount)
                diamond_items = MarketDeal.convert_to_ingots(
                    diamond_amount, diamond_unit
                )
            else:
                diamond_items = float(total_diamond)
        else:
            iron_ingots, gold_ingots, diamond_items = prompt_material_values_manual()
    else:
        iron_ingots, gold_ingots, diamond_items = prompt_material_values_manual()

    _calculate_and_show_result(
        ctx,
        iron_ingots,
        gold_ingots,
        diamond_items,
        price_iron,
        price_gold,
        price_diamond,
    )

    _offer_stash_subtraction(
        ctx, int(iron_ingots), int(gold_ingots), int(diamond_items), used_stash
    )


# ---------------------------------------------------------------------------
# Mode 2 – Shulker Scanner
# ---------------------------------------------------------------------------
def shulker_scanner(
    ctx: SessionContext,
    price_iron: float,
    price_gold: float,
    price_diamond: float,
) -> None:
    """
    Interactive shulker-box scanner.
    User enters full stacks + remainder for blocks and items of each material.
    """
    print("\n--- 📦 QUICK SHULKER BOX SCANNER ---")

    total_diamond = 0
    total_iron = 0
    total_gold = 0
    used_stash = False

    load_stash_choice = input("\nLoad values from stash? (y/n): ").strip().lower()
    if load_stash_choice == "y":
        total_iron, total_gold, total_diamond, used_stash = load_materials_from_stash(
            ctx
        )
        if not used_stash:
            print("⚠ No stash found. Please enter values manually.")
            print("\n💎 DIAMONDS:")
            total_diamond = _get_material_count(
                "DIAMOND", is_block=True
            ) + _get_material_count("DIAMOND", is_block=False)
            print("\n⬜ IRON:")
            total_iron = _get_material_count(
                "IRON", is_block=True
            ) + _get_material_count("IRON", is_block=False)
            print("\n🟨 GOLD:")
            total_gold = _get_material_count(
                "GOLD", is_block=True
            ) + _get_material_count("GOLD", is_block=False)
    else:
        print("\n💎 DIAMONDS:")
        total_diamond = _get_material_count(
            "DIAMOND", is_block=True
        ) + _get_material_count("DIAMOND", is_block=False)
        print("\n⬜ IRON:")
        total_iron = _get_material_count("IRON", is_block=True) + _get_material_count(
            "IRON", is_block=False
        )
        print("\n🟨 GOLD:")
        total_gold = _get_material_count("GOLD", is_block=True) + _get_material_count(
            "GOLD", is_block=False
        )

    multiplier = safe_int_input(
        "\nHow many times is this chest configuration delivered? (Multiplier, default = 1): ",
        default=1,
    )

    iron_ingots = total_iron * multiplier
    gold_ingots = total_gold * multiplier
    diamond_items = total_diamond * multiplier

    _calculate_and_show_result(
        ctx,
        iron_ingots,
        gold_ingots,
        diamond_items,
        price_iron,
        price_gold,
        price_diamond,
    )

    _offer_stash_subtraction(
        ctx, int(iron_ingots), int(gold_ingots), int(diamond_items), used_stash
    )


# ---------------------------------------------------------------------------
# Core calculation & result display (shared by Mode 1 and Mode 2)
# ---------------------------------------------------------------------------
def _calculate_and_show_result(
    ctx: SessionContext,
    iron_ingots: float,
    gold_ingots: float,
    diamond_items: float,
    price_iron: float,
    price_gold: float,
    price_diamond: float,
) -> None:
    """
    Compute the market value, compare against the user's offered price,
    display the result, and log the deal to the database.
    """
    total_market_value = (
        (iron_ingots * price_iron)
        + (gold_ingots * price_gold)
        + (diamond_items * price_diamond)
    )
    min_needed_price = total_market_value * MarketDeal.MIN_ACCEPTABLE_PERCENT

    print("\n" + "-" * 40)
    print(f"📊 INTERIM TOTAL (Market Value): {total_market_value:.2f}$")
    print(f"📉 Your Minimum (incl. discount): {min_needed_price:.2f}$")
    print("-" * 40)

    offered_price = safe_float_input(
        "\nWhat is the buyer offering for these goods? ($): "
    )

    result = analyze_deal(
        iron_ingots,
        gold_ingots,
        diamond_items,
        price_iron,
        price_gold,
        price_diamond,
        offered_price=offered_price,
    )

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
    print(
        f"📦 Diamond total:   {MarketDeal.format_bulk_storage(diamond_items, is_diamond=True)}"
    )
    print(
        f"🚚 Shipping volume: ~{result['stacks']:.1f} stacks "
        f"({result['shulkers']:.2f} shulker boxes)"
    )

    if result["stacks"] > 0:
        print(
            f"📊 Margin:          {result['profit_loss'] / result['stacks']:.2f}$ per stack | "
            f"{result['profit_loss'] / result['shulkers']:.2f}$ per shulker"
        )

    print("\n== FINANCIAL CHECK ==")
    print(f"Market value:    {result['market_value']:.2f}$")
    print(
        f"Offered price:   {result['offered_price']:.2f}$ "
        f"({result['percent_of_market']:.1f}% of market)"
    )
    print(
        f"Your limit ({MarketDeal.MIN_ACCEPTABLE_PERCENT * 100:.0f}%): "
        f"{result['min_needed_price']:.2f}$"
    )
    print("-" * 40)
    print(f"{result['status_emoji']} {result['status']}")
    print(f"   {result['status_msg']}")

    # Smart counter-offer logic on rejection
    if result["status"] == "REJECTED":
        counter = result.get("counter_offer")
        if counter is None:
            print(
                "\n💡 COUNTER-OFFER NOT POSSIBLE: The offer doesn't even cover the diamond value!"
            )
        elif counter:
            print("\n💡 COUNTER-OFFER SUGGESTION:")
            print(
                f"For ${result['offered_price']:.0f}, offer instead just the following:"
            )
            if result["iron_ingots"] > 0:
                print(
                    f" -> Iron:      {MarketDeal.format_bulk_storage(counter['iron'])}"
                )
            if result["gold_ingots"] > 0:
                print(
                    f" -> Gold:      {MarketDeal.format_bulk_storage(counter['gold'])}"
                )
            if result["diamond_items"] > 0:
                print(
                    f" -> Diamonds:  {MarketDeal.format_bulk_storage(counter['diamond'], is_diamond=True)} "
                    f"(unchanged)"
                )

    MarketDeal.log_deal(
        iron_ingots,
        gold_ingots,
        diamond_items,
        result["market_value"],
        offered_price,
        result["status"],
        price_iron,
        price_gold,
        price_diamond,
        company_id=ctx.company_id,
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
    print("💰 Estimated market value (current live prices):")
    print(f"   Iron:     {iron_value:>10.2f}$")
    print(f"   Gold:      {gold_value:>10.2f}$")
    print(f"   Diamonds: {diamond_value:>10.2f}$")
    print("============================================")


# ---------------------------------------------------------------------------
# Mode 4 – Stash Manager
# ---------------------------------------------------------------------------
def stash_manager(
    ctx: SessionContext,
    price_iron: float,
    price_gold: float,
    price_diamond: float,
) -> None:
    """Manage the saved inventory stash."""
    while True:
        clear_screen()
        print("=" * 50)
        print("     📦 STASH MANAGER")
        print("=" * 50)
        stash = ctx.load_stash()

        total_iron = stash.get("iron_blocks", 0) * INGOTS_PER_BLOCK + stash.get(
            "iron_ingots", 0
        )
        total_gold = stash.get("gold_blocks", 0) * INGOTS_PER_BLOCK + stash.get(
            "gold_ingots", 0
        )
        total_diamond = stash.get("diamond_blocks", 0) * INGOTS_PER_BLOCK + stash.get(
            "diamond_items", 0
        )

        iron_value = total_iron * price_iron
        gold_value = total_gold * price_gold
        diamond_value = total_diamond * price_diamond
        total_value = iron_value + gold_value + diamond_value

        stacks = (total_iron + total_gold + total_diamond) / float(ITEMS_PER_STACK)
        shulkers = (total_iron + total_gold + total_diamond) / float(ITEMS_PER_SHULKER)

        auto_sub = ctx.stash_auto_subtract()

        print(f"\n📦 CURRENT STASH (last updated: {stash.get('updated_at', 'never')})")
        print("-" * 40)
        print(
            f"  Iron:     {stash['iron_blocks']} blocks + {stash['iron_ingots']} ingots"
        )
        print(f"           ({MarketDeal.format_bulk_storage(total_iron)})")
        print(
            f"  Gold:     {stash['gold_blocks']} blocks + {stash['gold_ingots']} ingots"
        )
        print(f"           ({MarketDeal.format_bulk_storage(total_gold)})")
        print(
            f"  Diamonds: {stash['diamond_blocks']} blocks + {stash['diamond_items']} items"
        )
        print(
            f"           ({MarketDeal.format_bulk_storage(total_diamond, is_diamond=True)})"
        )
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
            ctx.save_stash(new_stash)
            print("\n✅ Stash updated!")

        elif choice == "2":
            confirm = (
                input("Are you sure you want to clear the stash? (y/n): ")
                .strip()
                .lower()
            )
            if confirm == "y":
                ctx.clear_stash()
                print("\n✅ Stash cleared!")
            else:
                print("\n⏩ Canceled.")

        elif choice == "3":
            ctx.set_auto_subtract(not auto_sub)
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
    ctx = resolve_company()
    if ctx is None:
        press_enter_to_continue()
        return

    if ctx.is_read_only:
        print("\n⚠️  Running in READ-ONLY mode. You can view data but cannot modify.")

    while True:
        clear_screen()
        print("=" * 50)
        print("     DEMOCRACYCRAFT TOOLBOX v3.2")
        print("=" * 50)
        print("  [1] Deal Calculator (enter total amounts)")
        print("  [2] Shulker Box Scanner (enter FULL STACKS)")
        print("  [3] Quick Converter (split desired amounts)")
        print("  [4] 📦 Stash Manager (saved inventory)")
        if ctx.is_read_only:
            print("     ⚠️  READ-ONLY MODE")
        print("  [5] ❌ Exit")
        choice = input("  Choice (1/2/3/4/5): ").strip()

        if choice == "5":
            print("\nGoodbye! 👋")
            break

        if choice in ("1", "2", "3", "4"):
            print("\n⏳ Loading current prices ...")
            price_iron, price_gold, price_diamond, _ = fetch_live_prices()
            print("✓ Prices loaded.\n")
        else:
            logger.warning("Invalid menu choice '%s'.", choice)
            press_enter_to_continue()
            continue

        if choice == "1":
            deal_calculator(ctx, price_iron, price_gold, price_diamond)
        elif choice == "2":
            shulker_scanner(ctx, price_iron, price_gold, price_diamond)
        elif choice == "3":
            quick_converter(price_iron, price_gold, price_diamond)
        elif choice == "4":
            stash_manager(ctx, price_iron, price_gold, price_diamond)

        press_enter_to_continue()
