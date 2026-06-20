#!/usr/bin/env python3
"""
install_hooks.py — Install git hooks for the project.

Copies scripts/pre-commit-hook.py as the .git/hooks/pre-commit
so encryption runs automatically on every commit.

OS-agnostic: works on Windows, macOS, and Linux.
"""

import subprocess
import sys
from pathlib import Path


def main():
    project_root = Path(__file__).resolve().parent.parent
    hooks_dir = project_root / ".git" / "hooks"
    hook_source = project_root / "scripts" / "pre-commit-hook.py"
    hook_target = hooks_dir / "pre-commit"

    if not hooks_dir.exists():
        print("❌ .git/hooks directory not found. Are you in a git repository?")
        sys.exit(1)

    if not hook_source.exists():
        print(f"❌ {hook_source} not found.")
        sys.exit(1)

    # Write the hook script
    hook_target.write_text(hook_source.read_text(encoding="utf-8"), encoding="utf-8")

    # Make executable (needed on macOS/Linux; harmless on Windows)
    hook_target.chmod(0o755)

    print(f"✅ Installed pre-commit hook at {hook_target}")
    print("   .env will auto-encrypt → .env.encrypted on every commit.")
    print("   To uninstall: rm .git/hooks/pre-commit")


if __name__ == "__main__":
    main()