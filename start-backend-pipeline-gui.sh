#!/usr/bin/env bash
# GLM Coding Helper - macOS GUI launcher
# Port of start-backend-pipeline-gui.cmd / .ps1.
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

# Check / free port 8888.
if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:8888 -sTCP:LISTEN >/dev/null 2>&1; then
        PID="$(lsof -nP -iTCP:8888 -sTCP:LISTEN -t | head -1)"
        echo "[WARN] Port 8888 already in use by PID $PID."
        read -rp "Kill it and restart? [y/N] " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            kill -9 "$PID" 2>/dev/null || true
            sleep 2
        else
            exit 1
        fi
    fi
fi

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
# Force CPU on Mac (Paddle has no MPS support; ultralytics would try CUDA
# otherwise).
export CNCAPTCHA_OCR_MODE="${CNCAPTCHA_OCR_MODE:-cpu}"
export CNCAPTCHA_YOLO_DEVICE="${CNCAPTCHA_YOLO_DEVICE:-cpu}"

echo "==> Launching GLM Coding Helper backend (GUI mode)..."
exec "$PY" "$ROOT/backend/gui.py"
