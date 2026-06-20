#!/usr/bin/env python3
"""Entry point for the DC Trade API – CLI tool."""

import sys
from src.core import database as db
from src.utils.console_ui import main_loop


def main() -> None:
    """Run the main CLI loop."""
    db.init_db()
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n\nProgram terminated by user. 👋")
        sys.exit(0)


if __name__ == "__main__":
    main()
