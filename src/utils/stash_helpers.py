"""Shared helpers for stash loading and material prompting used by both Deal Calculator and Shulker Scanner."""

from __future__ import annotations

import logging

from src.core.market_deal import MarketDeal, stash_ingot_equivalents
from src.utils.input_helpers import safe_float_input, input_unit
from src.utils.session import SessionContext

logger = logging.getLogger(__name__)


def _override_int(prompt: str, stash_val: int) -> int:
    """
    Prompt for an override integer value.  Returns *stash_val* if the user
    enters an empty line or invalid value.
    """
    raw = input(prompt).strip()
    if raw == "":
        return stash_val
    try:
        return int(raw)
    except ValueError:
        return stash_val


def load_materials_from_stash(
    ctx: SessionContext,
) -> tuple[int, int, int, bool]:
    """
    Prompt the user to load material values from the saved stash.

    Returns ``(total_iron_ingots, total_gold_ingots, total_diamond_items, used_stash)``
    where *used_stash* indicates whether the stash was actually loaded.
    """
    stash = ctx.load_stash()
    total_iron, total_gold, total_diamond = stash_ingot_equivalents(stash)

    if (
        stash
        and stash.get("updated_at") != "never"
        and (total_iron or total_gold or total_diamond)
    ):
        used_stash = True
        print("\n📦 Loaded from stash (you can override individual values):")
        print(
            f"💎 DIAMONDS: {stash['diamond_blocks']} blocks, {stash['diamond_items']} items"
        )
        print("   (Enter raw numbers – not stacks. Leave empty to keep stash value.)")
        di_blocks = _override_int("   Diamond blocks: ", stash["diamond_blocks"])
        di_items = _override_int("   Diamond items:  ", stash["diamond_items"])
        total_diamond = di_blocks * 9 + di_items

        print(
            f"\n⬜ IRON: {stash['iron_blocks']} blocks, {stash['iron_ingots']} ingots"
        )
        print("   (Enter raw numbers – not stacks. Leave empty to keep stash value.)")
        ir_blocks = _override_int("   Iron blocks: ", stash["iron_blocks"])
        ir_ingots = _override_int("   Iron ingots: ", stash["iron_ingots"])
        total_iron = ir_blocks * 9 + ir_ingots

        print(
            f"\n🟨 GOLD: {stash['gold_blocks']} blocks, {stash['gold_ingots']} ingots"
        )
        print("   (Enter raw numbers – not stacks. Leave empty to keep stash value.)")
        go_blocks = _override_int("   Gold blocks: ", stash["gold_blocks"])
        go_ingots = _override_int("   Gold ingots: ", stash["gold_ingots"])
        total_gold = go_blocks * 9 + go_ingots
    else:
        used_stash = False
        print("⚠ No stash found. Please enter values manually.")

    return total_iron, total_gold, total_diamond, used_stash


def prompt_material_values_manual() -> tuple[float, float, float]:
    """Prompt the user for raw iron/gold/diamond amounts and units manually."""
    iron_amount = safe_float_input("\nIron amount (0 if none): ")
    iron_unit = input_unit("Iron", iron_amount)
    gold_amount = safe_float_input("Gold amount (0 if none): ")
    gold_unit = input_unit("Gold", gold_amount)
    diamond_amount = safe_float_input("Diamond amount (0 if none): ")
    diamond_unit = input_unit("Diamond", diamond_amount)

    iron_ingots = MarketDeal.convert_to_ingots(iron_amount, iron_unit)
    gold_ingots = MarketDeal.convert_to_ingots(gold_amount, gold_unit)
    diamond_items = MarketDeal.convert_to_ingots(diamond_amount, diamond_unit)
    return iron_ingots, gold_ingots, diamond_items
