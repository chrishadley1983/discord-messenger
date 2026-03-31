#!/bin/bash
# Encrypt .env → .env.sops using age key
# Run this after modifying .env to update the encrypted version
#
# Usage: bash scripts/encrypt-env.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"
SOPS_FILE="$PROJECT_ROOT/.env.sops"
AGE_KEY="${SOPS_AGE_KEY_FILE:-$HOME/.sops/age-key.txt}"
AGE_RECIPIENT="age13hvt9lnfgk0t7z5trulrwtldmcnan83f6tecalqh8q6vqyudhf4snyrusk"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found"
    exit 1
fi

if [ ! -f "$AGE_KEY" ]; then
    echo "ERROR: Age key not found at $AGE_KEY"
    exit 1
fi

export SOPS_AGE_KEY_FILE="$AGE_KEY"

# Strip comments and blank lines (SOPS dotenv can't handle them)
# Use a temp file in project root so SOPS can find .sops.yaml
CLEAN="$PROJECT_ROOT/.env.clean.tmp"
grep -v '^#' "$ENV_FILE" | grep -v '^$' | grep '=' > "$CLEAN"

sops --encrypt --age "$AGE_RECIPIENT" --input-type dotenv --output-type dotenv "$CLEAN" > "$SOPS_FILE"
rm -f "$CLEAN"

echo "Encrypted $ENV_FILE → $SOPS_FILE ($(grep -c '=' "$SOPS_FILE") keys)"
