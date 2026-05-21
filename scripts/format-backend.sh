#!/usr/bin/env bash
# Format only the backend (backend/**/*.py) using Black.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Formatting backend (black)"
uv run black backend/
