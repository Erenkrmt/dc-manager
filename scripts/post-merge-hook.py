#!/usr/bin/env python3
"""
post-merge-hook.py — Git post-merge / post-checkout hook.

Automatically decrypts .env.encrypted → .env after git pull, merge, or checkout
if .env is missing or older than .env.encrypted.

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


def needs_decrypt(env_file: Path, encrypted_file: Path) -> bool:
    """Return True if decryption should run (.env missing or stale)."""
    if not env_file.exists():
        return True
    if not encrypted_file.exists():
        return False
    # Decrypt if encrypted file is newer than decrypted file
    return encrypted_file.stat().st_mtime > env_file.stat().st_mtime


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    env_file = project_root / ".env"
    encrypted_file = project_root / ".env.encrypted"

    if not encrypted_file.exists():
        # Nothing encrypted to decrypt, silently exit
        return 0

    if not needs_decrypt(env_file, encrypted_file):
        # .env already exists and is up-to-date
        return 0

    # Check sops is available
    sops_path = shutil.which("sops")
    if not sops_path:
        print("ℹ️  .env.encrypted found but 'sops' not installed.")
        print("   Install sops and run: make env")
        return 0  # Non-blocking

    # Check for age key
    key_file = get_age_key_file()
    if not key_file.exists():
        print(f"ℹ️  .env.encrypted found but age key not found at {key_file}")
        return 0  # Non-blocking

    # Decrypt
    env = os.environ.copy()
    env["SOPS_AGE_KEY_FILE"] = str(key_file)

    result = subprocess.run(
        [
            sops_path,
            "--decrypt",
            "--input-type",
            "dotenv",
            "--output-type",
            "dotenv",
            str(encrypted_file),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        print(f"⚠️  Auto-decrypt failed after pull:\n{result.stderr}")
        return 0  # Non-blocking

    env_file.write_text(result.stdout, encoding="utf-8")
    print(f"✅ Auto-decrypted {encrypted_file} → {env_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
