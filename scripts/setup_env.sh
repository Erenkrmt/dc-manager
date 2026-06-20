#!/bin/bash
# setup_env.sh — Decrypt the .env file from .env.encrypted using SOPS + age
#
# Requires:
#   - sops (brew install sops)
#   - age  (brew install age) — included as dep of sops
#   - Your age private key at ~/.config/sops/age/keys.txt
#
# First-time setup on a new machine:
#   1. brew install sops
#   2. Copy your age private key to ~/.config/sops/age/keys.txt
#      (the file should contain your AGE-SECRET-KEY-... line)
#   3. Run this script: ./scripts/setup_env.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

ENCRYPTED_FILE=".env.encrypted"
DECRYPTED_FILE=".env"

if [ ! -f "$ENCRYPTED_FILE" ]; then
    echo "❌ $ENCRYPTED_FILE not found. Nothing to decrypt."
    exit 1
fi

if [ ! -f "$HOME/.config/sops/age/keys.txt" ]; then
    echo "❌ Age private key not found at ~/.config/sops/age/keys.txt"
    echo ""
    echo "   On your NEW machine, run:"
    echo "     mkdir -p ~/.config/sops/age"
    echo "     # Then copy your AGE-SECRET-KEY-... into ~/.config/sops/age/keys.txt"
    echo ""
    echo "   On OLD machine, cat the key from: ~/.config/sops/age/keys.txt"
    exit 1
fi

# Decrypt
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
sops --decrypt --input-type dotenv --output-type dotenv "$ENCRYPTED_FILE" > "$DECRYPTED_FILE"

echo "✅ Decrypted $ENCRYPTED_FILE → $DECRYPTED_FILE"
echo "   SOPS config: .sops.yaml"
echo "   Age key: ~/.config/sops/age/keys.txt"