#!/usr/bin/env bash
set -euo pipefail

# CodeAsk start script: validates env, runs migrations via app lifespan, starts uvicorn.
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

uv sync --frozen 2>/dev/null || uv sync

echo "Starting CodeAsk on ${CODEASK_HOST:-127.0.0.1}:${CODEASK_PORT:-8000}"
echo "Data dir: ${CODEASK_DATA_DIR:-$HOME/.codeask}"

exec uv run codeask
