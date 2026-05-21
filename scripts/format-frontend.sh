#!/usr/bin/env bash
# Format only the frontend (frontend/**/*.{js,html,css,json,md}) using Prettier.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Formatting frontend (prettier)"
npx --no-install prettier --write "frontend/**/*.{js,html,css,json,md}"
