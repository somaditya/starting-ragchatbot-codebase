#!/usr/bin/env bash
# Verify the codebase is properly formatted without modifying files.
# Exits non-zero if any file would be reformatted. Suitable for CI / pre-push.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

status=0

echo "==> Checking backend formatting (black --check)"
if ! uv run black --check backend/; then
    status=1
fi

echo
echo "==> Checking frontend formatting (prettier --check)"
if ! npx --no-install prettier --check "frontend/**/*.{js,html,css,json,md}"; then
    status=1
fi

echo
if [ "$status" -eq 0 ]; then
    echo "All quality checks passed."
else
    echo "Quality checks FAILED. Run scripts/format.sh to fix."
fi

exit "$status"
