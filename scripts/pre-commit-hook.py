#!/usr/bin/env python3
"""
pre-commit-hook.py — Git pre-commit hook.

Automatically encrypts .env → .env.encrypted before each commit
if .env has been modified (staged or unstaged).

OS-agnostic: works on Windows, macOS, and Linux.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_age_key_file() -> Path:
    """Return the path to the age private key file."""
    env_var = os.environ.get("SOPS_AGE_KEY_FILE")
    if env_var:
        return Path(env_var)
    return Path.home() / ".config" / "sops" / "age" / "keys.txt"


def main():
    project_root = Path(__file__).resolve().parent.parent

    # Only re-encrypt if .env exists and has uncommitted changes
    env_file = project_root / ".env"
    if not env_file.exists():
        return 0

    # Check if .env has unstaged or staged changes
    result = subprocess.run(
        ["git", "diff", "--name-only", "--", ".env"],
        capture_output=True, text=True, cwd=project_root,
    )
    staged = result.stdout.strip()

    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", ".env"],
        capture_output=True, text=True, cwd=project_root,
    )
    cached = result.stdout.strip()

    if not staged and not cached:
        return 0  # .env hasn't changed, nothing to encrypt

    # Check sops is available
    sops_path = shutil.which("sops")
    if not sops_path:
        print("⚠️  .env changed, but 'sops' not found. Skipping auto-encryption.")
        print("   Install sops and run: python scripts/encrypt_env.py")
        return 0  # Don't block the commit, just warn

    # Check for age key
    key_file = get_age_key_file()
    if not key_file.exists():
        print(f"⚠️  .env changed, but age key not found at {key_file}. Skipping auto-encryption.")
        return 0

    # Encrypt
    env = os.environ.copy()
    env["SOPS_AGE_KEY_FILE"] = str(key_file)

    encrypted_file = project_root / ".env.encrypted"
    result = subprocess.run(
        [sops_path, "--encrypt", "--input-type", "dotenv", "--output-type", "dotenv", str(env_file)],
        capture_output=True, text=True, env=env,
    )

    if result.returncode != 0:
        print(f"❌ Auto-encryption failed:\n{result.stderr}")
        print("   Commit blocked. Fix the issue or run: git commit --no-verify")
        return 1

    encrypted_file.write_text(result.stdout, encoding="utf-8")

    # Stage the updated .env.encrypted so it's included in the commit
    subprocess.run(["git", "add", str(encrypted_file)], cwd=project_root)

    return 0


if __name__ == "__main__":
    sys.exit(main())