#!/usr/bin/env bash
# GLM Coding Helper - macOS headless launcher
# Starts the FastAPI pipeline server without the Tk window. Useful for
# running over SSH or in the background.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PY="$ROOT/.venv_paddle/bin/python"

if [[ ! -x "$PY" ]]; then
    echo "[WARN] venv not found at $PY. Falling back to system python3."
    PY="$(command -v python3)"
    if [[ -z "$PY" ]]; then
        echo "[FAIL] python3 not found. Run ./setup-mac.sh first." >&2
        exit 1
    fi
fi

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export CNCAPTCHA_OCR_MODE="${CNCAPTCHA_OCR_MODE:-cpu}"
export CNCAPTCHA_YOLO_DEVICE="${CNCAPTCHA_YOLO_DEVICE:-cpu}"

echo "==> Launching GLM Coding Helper backend (headless, port 8888)..."
exec "$PY" -m backend.server
