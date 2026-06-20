#!/usr/bin/env python3
"""
install_hooks.py — Install git hooks for the project.

Installs:
  1. pre-commit hook   → auto-encrypt .env before every commit
  2. post-merge hook   → auto-decrypt .env after every pull/merge/checkout

OS-agnostic: works on Windows, macOS, and Linux.
"""

import subprocess
import sys
from pathlib import Path


HOOKS = [
    ("pre-commit", "scripts/pre-commit-hook.py", ".env will auto-encrypt → .env.encrypted on every commit."),
    ("post-merge", "scripts/post-merge-hook.py", ".env will auto-decrypt ← .env.encrypted after every pull/merge/checkout."),
]


def main():
    project_root = Path(__file__).resolve().parent.parent
    hooks_dir = project_root / ".git" / "hooks"

    if not hooks_dir.exists():
        print("❌ .git/hooks directory not found. Are you in a git repository?")
        sys.exit(1)

    for hook_name, source_relpath, description in HOOKS:
        source = project_root / source_relpath
        target = hooks_dir / hook_name

        if not source.exists():
            print(f"❌ {source} not found. Skipping {hook_name} hook.")
            continue

        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        target.chmod(0o755)  # Harmless on Windows

        print(f"✅ Installed {hook_name} hook at {target}")
        print(f"   {description}")

    print("\n🔗 Both hooks installed. To uninstall:")
    print("   rm .git/hooks/pre-commit .git/hooks/post-merge")


if __name__ == "__main__":
    main()
