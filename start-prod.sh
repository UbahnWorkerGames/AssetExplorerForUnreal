#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
DIST_DIR="$FRONTEND_DIR/dist"
VENV_DIR="$BACKEND_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
REPAIR_NO_PIC_ON_STARTUP=0

for arg in "$@"; do
  case "$arg" in
    --repair-no-pic)
      REPAIR_NO_PIC_ON_STARTUP=1
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

open_browser() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
    return
  fi
  if command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  fi
}

echo "[1/4] Checking prerequisites..."
require_cmd python3
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10+ is required." >&2
  python3 -c 'import sys; print("Detected:", sys.version.replace("\n"," "))'
  exit 1
fi

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
export ASSET_UI_DIST="../frontend/dist"
export ASSET_SERVER_HOST=0.0.0.0
export ASSET_SERVER_PORT=7985
export ASSET_SERVER_LOG_LEVEL=info
export ASSET_SERVER_RELOAD=0
export ASSET_SERVER_CWD="$BACKEND_DIR"
if [[ "$REPAIR_NO_PIC_ON_STARTUP" == "1" ]]; then
  export ASSET_NO_PIC_REPAIR_ON_STARTUP=1
fi

  cd "$BACKEND_DIR"
  (
    for _ in $(seq 1 120); do
    if "$VENV_PYTHON" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7985/health', timeout=1)"; then
      open_browser "http://localhost:7985"
      break
    fi
    sleep 0.5
  done
) >/dev/null 2>&1 &
exec "$VENV_PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 7985 --log-level info
