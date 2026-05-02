#!/usr/bin/env bash
set -euo pipefail

# CodeAsk start script for bare-metal / local-dev deployments.
# Usage:
#   export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
#   ./start.sh

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [[ -z "${CODEASK_DATA_KEY:-}" ]]; then
    cat >&2 <<EOF
ERROR: CODEASK_DATA_KEY is not set.

Generate one (and save it — losing it makes encrypted DB fields unreadable):

    export CODEASK_DATA_KEY="\$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

Then re-run ./start.sh.
EOF
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: 'uv' not found. Install from https://docs.astral.sh/uv/ first." >&2
    exit 1
fi

# Avoid LiteLLM startup network access to GitHub for model pricing metadata.
export LITELLM_LOCAL_MODEL_COST_MAP=True

uv sync --frozen 2>/dev/null || uv sync

FRONTEND_DIST="${CODEASK_FRONTEND_DIST:-frontend/dist}"
DIST_INDEX="$FRONTEND_DIST/index.html"

if [[ ! -f "$DIST_INDEX" ]]; then
    if [[ -z "${CODEASK_FRONTEND_DIST:-}" ]] && command -v corepack >/dev/null 2>&1; then
        echo "frontend/dist not found — building frontend with pnpm..."
        corepack pnpm --dir frontend install --frozen-lockfile
        corepack pnpm --dir frontend build
    else
        cat >&2 <<EOF
WARNING: frontend/dist/index.html not found.

The backend will still start and /api/* will work.
To serve the SPA, build the frontend first:
    cd frontend
    corepack pnpm install --frozen-lockfile
    corepack pnpm build

Or run the frontend dev server while the backend is running:
    cd frontend
    corepack pnpm dev
EOF
    fi
fi

echo "Starting CodeAsk on ${CODEASK_HOST:-127.0.0.1}:${CODEASK_PORT:-8000}"
echo "Data dir: ${CODEASK_DATA_DIR:-$HOME/.codeask}"

exec uv run codeask
