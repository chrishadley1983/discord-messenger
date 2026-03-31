#!/bin/bash
# Decrypt .env.sops → .env using age key
# Run this after cloning or when .env.sops is updated
#
# Usage: bash scripts/decrypt-env.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SOPS_FILE="$PROJECT_ROOT/.env.sops"
ENV_FILE="$PROJECT_ROOT/.env"
AGE_KEY="${SOPS_AGE_KEY_FILE:-$HOME/.sops/age-key.txt}"

if [ ! -f "$SOPS_FILE" ]; then
    echo "ERROR: $SOPS_FILE not found"
    exit 1
fi

if [ ! -f "$AGE_KEY" ]; then
    echo "ERROR: Age key not found at $AGE_KEY"
    echo "Generate one with: age-keygen -o $AGE_KEY"
    exit 1
fi

export SOPS_AGE_KEY_FILE="$AGE_KEY"

# Decrypt and restore comments/structure
echo "# Decrypted from .env.sops — DO NOT commit this file" > "$ENV_FILE"
echo "# Re-encrypt after changes: bash scripts/encrypt-env.sh" >> "$ENV_FILE"
echo "" >> "$ENV_FILE"
sops --decrypt --input-type dotenv --output-type dotenv "$SOPS_FILE" >> "$ENV_FILE"

echo "Decrypted $SOPS_FILE → $ENV_FILE ($(grep -c '=' "$ENV_FILE") keys)"
