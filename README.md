# UnrealAssetExplorer

UnrealAssetExplorer is the management tool for Unreal Engine asset packs.
It combines a FastAPI backend with a React frontend and adds workflows for:

- project and asset indexing
- preview images/screenshots
- metadata and tag management
- LLM/OpenAI-assisted tag generation and translation
- semantic search (embeddings)
- import/export/sync flows for UE asset packs

## Unreal Integration

For Unreal-side interaction you need:

- https://github.com/UbahnWorkerGames/UnrealAssetExplorerBridge

The bridge is currently shipped for UE 5.7.

Important:

- the exporter needs UnrealAssetExplorer running during export
- ports are configurable in both places:
  - Unreal plugin settings
  - UnrealAssetExplorer settings

## Tech Stack

- Backend: Python, FastAPI, SQLite
- Frontend: React + Vite (built as static files)
- Data storage: `data/` directory (database, media, batch outputs)

## Repository Layout

- `backend/` - API server and processing logic
- `frontend/` - React UI source
- `data/` - runtime data (created/used by backend)
- `build-ui.bat` - one-time frontend build (Windows)
- `start-dev.bat` - dev mode (Vite + backend reload)
- `start-prod.bat` - production runtime on Windows (Python-only)
- `start-prod.sh` - production runtime on Linux (Python-only)

## Requirements

### Development

- Python 3.10+
- Node.js + npm

### Production Runtime

- Python 3.10+
- Prebuilt frontend `frontend/dist`

Node is only required to build the frontend once.

## Quick Start

### 1) Dev mode (Windows)

```bat
start-dev.bat
```

This starts:

- Vite dev server for frontend
- FastAPI backend with auto-reload on `127.0.0.1:8008`

### 2) Build frontend once (Windows)

```bat
build-ui.bat
```

Creates `frontend/dist`.

### 3) Production runtime (Windows)

```bat
start-prod.bat
```

- creates/uses backend venv
- installs Python deps
- serves built UI from `frontend/dist`
- starts backend on `0.0.0.0:8008`

### 4) Production runtime (Linux)

```bash
chmod +x start-prod.sh
./start-prod.sh
```

## UI Delivery Modes

- Dev: frontend served by Vite
- Prod: frontend served by backend from `frontend/dist`

If UI assets fail to load after a new build, rebuild frontend and hard-refresh browser cache.

## Notes

- SQLite is used by default; long-running write tasks can temporarily lock DB operations.
- Startup may process archived batch outputs before all write endpoints are available.
- API health endpoint: `GET /health`

## License

See `LICENSE`.

## Support

- Patreon: https://patreon.com/UbahnWorkerGames

## Extras

- You may also buy the Epic import script.
