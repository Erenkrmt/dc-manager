#!/usr/bin/env python3
"""
decrypt_env.py — Decrypt .env.encrypted → .env using SOPS + age.

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
    encrypted_file = project_root / ".env.encrypted"
    decrypted_file = project_root / ".env"

    if not encrypted_file.exists():
        print(f"❌ {encrypted_file} not found. Nothing to decrypt.")
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

    # Normalize line endings: SOPS' Go parser chokes on Windows CRLF (\r\n).
    # Read the encrypted file and strip all \r characters to ensure LF-only.
    raw = encrypted_file.read_bytes()
    if b"\r\n" in raw or b"\r" in raw:
        normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        encrypted_file.write_bytes(normalized)
        print("   ℹ Normalized CRLF → LF in encrypted file")

    # Decrypt
    env = os.environ.copy()
    env["SOPS_AGE_KEY_FILE"] = str(key_file)

    result = subprocess.run(
        [sops_path, "--decrypt", "--input-type", "dotenv", "--output-type", "dotenv", str(encrypted_file)],
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        print(f"❌ Decryption failed:\n{result.stderr}")
        sys.exit(1)

    decrypted_file.write_text(result.stdout, encoding="utf-8")

    print(f"✅ Decrypted {encrypted_file} → {decrypted_file}")
    print(f"   SOPS config: {project_root / '.sops.yaml'}")
    print(f"   Age key: {key_file}")


if __name__ == "__main__":
    main()