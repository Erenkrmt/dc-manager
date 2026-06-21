"""Input helpers for the CLI – safe number parsing, unit prompts, etc."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


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
    Returns ``'ingot'`` if *amount* is zero or the input is unrecognised.
    """
    if amount <= 0:
        return "ingot"
    unit = input(f"  -> Unit for {name} (block/ingot/nugget): ").strip().lower()
    if unit not in ("block", "ingot", "nugget"):
        logger.info("Unknown unit '%s' – defaulting to 'ingot'.", unit)
        return "ingot"
    return unit


def clear_screen() -> None:
    """Clear the terminal screen (cross-platform)."""
    import os

    os.system("cls" if os.name == "nt" else "clear")


def press_enter_to_continue() -> None:
    """Prompt the user to press Enter before continuing."""
    input("\nPress Enter to continue...")
