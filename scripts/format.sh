#!/usr/bin/env bash
# Format the entire codebase: Black for backend Python, Prettier for frontend assets.
# Writes changes in-place. Exit non-zero only on tool failure.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Formatting backend (black)"
uv run black backend/

echo
echo "==> Formatting frontend (prettier)"
npx --no-install prettier --write "frontend/**/*.{js,html,css,json,md}"

echo
echo "Done."
