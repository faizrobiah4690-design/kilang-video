#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8501}"
export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:$PYTHONPATH}"

THEME_ARGS=(
  --theme.base=dark
  --theme.primaryColor="#10B981"
  --theme.backgroundColor="#0B1120"
  --theme.secondaryBackgroundColor="#111C33"
  --theme.textColor="#F1F5F9"
)

if [ -x "${SCRIPT_DIR}/.venv/bin/python" ]; then
  exec "${SCRIPT_DIR}/.venv/bin/python" -m streamlit run webui/KilangStudio.py \
    --server.address="$HOST" \
    --server.port="$PORT" \
    --server.headless=true \
    --browser.gatherUsageStats=false \
    "${THEME_ARGS[@]}"
elif command -v uv >/dev/null 2>&1; then
  exec uv run streamlit run webui/KilangStudio.py \
    --server.address="$HOST" \
    --server.port="$PORT" \
    --server.headless=true \
    --browser.gatherUsageStats=false \
    "${THEME_ARGS[@]}"
else
  exec streamlit run webui/KilangStudio.py \
    --server.address="$HOST" \
    --server.port="$PORT" \
    --server.headless=true \
    --browser.gatherUsageStats=false \
    "${THEME_ARGS[@]}"
fi
