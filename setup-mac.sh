#!/usr/bin/env bash
# GLM Coding Helper - macOS one-click setup
# Creates .venv_paddle and installs CPU-only dependencies (Paddle has no MPS
# support, so this project is CPU-only on Mac).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY_BIN="${PYTHON:-python3}"

if ! command -v "$PY_BIN" >/dev/null 2>&1; then
    cat >&2 <<EOF
[FAIL] python3 not found. Install via Homebrew:
    brew install python@3.12 python-tk@3.12
EOF
    exit 1
fi

if ! "$PY_BIN" -c "import tkinter" >/dev/null 2>&1; then
    cat >&2 <<EOF
[WARN] tkinter is missing. The Tk GUI won't start without it.
    Install with: brew install python-tk@3.12
EOF
fi

ARCH="$(uname -m)"
echo "==> GLM Coding Helper setup (macOS, $ARCH)"
echo "    Python: $($PY_BIN --version)"
echo "    Root:   $ROOT"

# Use the Tsinghua mirror by default; pass PIP_INDEX_URL=... to override.
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

"$PY_BIN" scripts/setup_backend.py \
    --target cpu \
    --pip-arg=-i \
    --pip-arg="$PIP_INDEX_URL"

cat <<EOF

==> Setup complete.

Next steps:
  ./start-backend-pipeline-gui.sh      # launch Tk GUI + FastAPI
  ./start-backend-headless.sh          # headless (no Tk window)

Then install the Tampermonkey userscript in Chrome/Edge/Safari and visit
https://www.bigmodel.cn/glm-coding
EOF
