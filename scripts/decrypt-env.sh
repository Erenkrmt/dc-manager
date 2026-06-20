#!/usr/bin/env bash
# =============================================================================
# decrypt-env.sh – Decrypt .env.encrypted to .env for local use
#
# Prerequisites:
#   1. Install sops:         brew install sops   /   apt install sops
#   2. Install age:          brew install age    /   apt install age
#   3. Have your age private key available (the one that matches the
#      public key in .sops.yaml)
#
# Usage:
#   ./scripts/decrypt-env.sh
#
# This creates/overwrites .env with the decrypted values.
# You can then copy the contents into Dockge's "Environment" tab.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

ENCRYPTED=".env.encrypted"
DECRYPTED=".env"

if [ ! -f "$ENCRYPTED" ]; then
    echo "❌ Error: $ENCRYPTED not found in $PROJECT_ROOT"
    exit 1
fi

echo "🔓 Decrypting $ENCRYPTED → $DECRYPTED ..."
sops -d "$ENCRYPTED" > "$DECRYPTED"
echo "✅ Done! Decrypted environment written to $DECRYPTED"
echo ""
echo "➡️  Now copy the contents of $DECRYPTED into Dockge's 'Environment' tab."
echo "   IMPORTANT: Never commit $DECRYPTED to git (it's in .gitignore)."