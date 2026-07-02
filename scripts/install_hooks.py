#!/usr/bin/env python3
"""
install_hooks.py — Install git hooks for the project.

Installs:
  1. pre-commit hook   → auto-encrypt .env before every commit
  2. post-merge hook   → auto-decrypt .env after every pull/merge/checkout

OS-agnostic: works on Windows, macOS, and Linux.
"""

import sys
from pathlib import Path


HOOKS = [
    (
        "pre-commit",
        "scripts/pre-commit-hook.py",
        ".env will auto-encrypt → .env.encrypted on every commit.",
    ),
    (
        "post-merge",
        "scripts/post-merge-hook.py",
        ".env will auto-decrypt ← .env.encrypted after every pull/merge/checkout.",
    ),
]


def main():
    project_root = Path(__file__).resolve().parent.parent
    hooks_dir = project_root / ".git" / "hooks"

    if not hooks_dir.exists():
        print("❌ .git/hooks directory not found. Are you in a git repository?")
        sys.exit(1)

    # Erkennen, ob wir in einer virtuellen Umgebung sind
    import os

    venv_path = os.environ.get("VIRTUAL_ENV")
    python_executable = "python3"  # Standard-Fallback

    if venv_path:
        # Unter Windows liegt die python.exe in 'Scripts', sonst in 'bin'
        win_python = Path(venv_path) / "Scripts" / "python.exe"
        unix_python = Path(venv_path) / "bin" / "python"

        if win_python.exists():
            # Git Bash benötigt Vorwärts-Slashes für den Shebang
            python_executable = f"/{win_python.as_posix().replace(':', '')}"
        elif unix_python.exists():
            python_executable = str(unix_python)

    for hook_name, source_relpath, description in HOOKS:
        source = project_root / source_relpath
        target = hooks_dir / hook_name

        if not source.exists():
            print(f"❌ {source} not found. Skipping {hook_name} hook.")
            continue

        # Inhalt lesen und Shebang dynamisch anpassen
        lines = source.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].startswith("#!"):
            lines[0] = f"#!{python_executable}"

        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        target.chmod(0o755)

        print(f"✅ Installed {hook_name} hook at {target}")
        print(f"   {description}")


if __name__ == "__main__":
    main()
