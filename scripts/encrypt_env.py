#!/usr/bin/env python3
"""
encrypt_env.py — Encrypt .env → .env.encrypted using SOPS + age.

OS-agnostic: works on Windows, macOS, and Linux.
Requires `sops` CLI to be installed and an age private key available.

The age key is resolved in this order:
  1. SOPS_AGE_KEY_FILE environment variable (if set)
  2. ~/.config/sops/age/keys.txt (cross-platform home directory)
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
    env_file = project_root / ".env"
    encrypted_file = project_root / ".env.encrypted"

    if not env_file.exists():
        print(f"❌ {env_file} not found. Nothing to encrypt.")
        sys.exit(1)

    # Check if sops is available
    sops_path = shutil.which("sops")
    if not sops_path:
        print(
            "❌ 'sops' command not found. Please install it:\n"
            "   macOS: brew install sops\n"
            "   Linux: https://github.com/getsops/sops/releases\n"
            "   Windows: winget install sops"
        )
        sys.exit(1)

    # Check for age key
    key_file = get_age_key_file()
    if not key_file.exists():
        print(
            f"❌ Age private key not found at {key_file}\n\n"
            f"   Create the directory and place your AGE-SECRET-KEY-... in it.\n"
            f"   mkdir -p {key_file.parent}"
        )
        sys.exit(1)

    # Encrypt
    env = os.environ.copy()
    env["SOPS_AGE_KEY_FILE"] = str(key_file)

    result = subprocess.run(
        [sops_path, "--encrypt", "--input-type", "dotenv", "--output-type", "dotenv", str(env_file)],
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        print(f"❌ Encryption failed:\n{result.stderr}")
        sys.exit(1)

    encrypted_file.write_text(result.stdout, encoding="utf-8")

    print(f"✅ Encrypted {env_file} → {encrypted_file}")
    print(f"   SOPS config: {project_root / '.sops.yaml'}")
    print(f"   Age key: {key_file}")


if __name__ == "__main__":
    main()