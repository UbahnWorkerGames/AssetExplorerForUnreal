@echo off
setlocal

set ROOT_DIR=%~dp0
set BACKEND_DIR=%ROOT_DIR%backend
set FRONTEND_DIR=%ROOT_DIR%frontend
set DIST_DIR=%FRONTEND_DIR%\dist
set VENV_DIR=%BACKEND_DIR%\.venv
set PYTHON=%VENV_DIR%\Scripts\python.exe

where python >nul 2>nul
if errorlevel 1 (
  echo [error] python is not in PATH
  pause
  exit /b 1
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo [error] Python 3.10+ is required.
  python -c "import sys; print('Detected:', sys.version.replace('\n',' '))"
  pause
  exit /b 1
)

if not exist "%PYTHON%" (
  echo [1/4] Creating backend venv...
  cd /d "%BACKEND_DIR%"
  python -m venv .venv
  if errorlevel 1 (
    echo [error] Failed to create backend venv
    pause
    exit /b 1
  )
) else (
  echo [1/4] Backend venv exists.
)

echo [2/4] Installing backend dependencies...
cd /d "%BACKEND_DIR%"
call "%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
  echo [error] Failed to upgrade pip
  pause
  exit /b 1
)
call "%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [error] Failed to install backend requirements
  pause
  exit /b 1
)

cd /d "%ROOT_DIR%"
if not exist "frontend\dist\index.html" (
  echo [error] Frontend build missing: frontend\dist\index.html
  echo         Build frontend once before runtime deployment.
  pause
  exit /b 1
)
findstr /C:"/ui/assets/" "frontend\dist\index.html" >nul
if errorlevel 1 (
  echo [error] Frontend dist seems built with wrong base path.
  echo         Expected "/ui/assets/" in frontend\dist\index.html
  echo         Run build-ui.bat to rebuild with VITE_BASE=/ui/
  pause
  exit /b 1
)

echo [3/4] Starting backend with bundled UI...
set ASSET_UI=true
set ASSET_UI_DIST=..\frontend\dist
set ASSET_SERVER_HOST=0.0.0.0
set ASSET_SERVER_PORT=8008
set ASSET_SERVER_LOG_LEVEL=info
set ASSET_SERVER_RELOAD=0
set ASSET_SERVER_CWD=%BACKEND_DIR%

set PORT_PID=
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /C:":8008" ^| findstr /C:"LISTENING"') do (
  set PORT_PID=%%P
  goto :port_check_done
)
:port_check_done
if defined PORT_PID (
  echo [error] Port 8008 is already in use by PID %PORT_PID%.
  echo         Stop that process first.
  pause
  exit /b 1
)

echo [4/4] Backend running on http://0.0.0.0:8008
start "" powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; for($i=0;$i -lt 120;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8008/health' -TimeoutSec 2; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 500){ Start-Process 'http://localhost:8008'; break } } catch {}; Start-Sleep -Milliseconds 500 }"
cd /d "%BACKEND_DIR%"
call "%PYTHON%" -m uvicorn main:app --host 0.0.0.0 --port 8008 --log-level info

endlocal
cmd
