#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
DIST_DIR="$FRONTEND_DIR/dist"
VENV_DIR="$BACKEND_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

echo "[1/4] Checking prerequisites..."
require_cmd python3

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "[2/4] Creating backend virtualenv..."
  (cd "$BACKEND_DIR" && python3 -m venv .venv)
else
  echo "[2/4] Backend virtualenv exists."
fi

echo "[3/4] Installing backend dependencies..."
(
  cd "$BACKEND_DIR"
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -r requirements.txt
)

if [[ ! -f "$DIST_DIR/index.html" ]]; then
  echo "Frontend build not found: $DIST_DIR/index.html" >&2
  echo "Build once before runtime deployment." >&2
  exit 1
fi
if ! grep -q "/ui/assets/" "$DIST_DIR/index.html"; then
  echo "Frontend dist seems built with wrong base path." >&2
  echo "Expected '/ui/assets/' in $DIST_DIR/index.html" >&2
  echo "Run ./build-ui.sh to rebuild with VITE_BASE=/ui/" >&2
  exit 1
fi

echo "[4/4] Starting backend with bundled UI..."
export ASSET_UI=true
export ASSET_UI_DIST="$DIST_DIR"
export ASSET_SERVER_HOST=0.0.0.0
export ASSET_SERVER_PORT=8008
export ASSET_SERVER_LOG_LEVEL=info
export ASSET_SERVER_RELOAD=0
export ASSET_SERVER_CWD="$BACKEND_DIR"

cd "$BACKEND_DIR"
exec "$VENV_PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8008 --log-level info
