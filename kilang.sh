#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8501}"
export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:$PYTHONPATH}"

if [ -x "${SCRIPT_DIR}/.venv/bin/python" ]; then
  exec "${SCRIPT_DIR}/.venv/bin/python" -m streamlit run webui/KilangStudio.py \
    --server.address="$HOST" \
    --server.port="$PORT" \
    --server.headless=true \
    --browser.gatherUsageStats=false
elif command -v uv >/dev/null 2>&1; then
  exec uv run streamlit run webui/KilangStudio.py \
    --server.address="$HOST" \
    --server.port="$PORT" \
    --server.headless=true \
    --browser.gatherUsageStats=false
else
  exec streamlit run webui/KilangStudio.py \
    --server.address="$HOST" \
    --server.port="$PORT" \
    --server.headless=true \
    --browser.gatherUsageStats=false
fi
