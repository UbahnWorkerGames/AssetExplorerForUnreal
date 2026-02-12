@echo off
setlocal

set ROOT_DIR=%~dp0
set FRONTEND_DIR=%ROOT_DIR%frontend

where npm >nul 2>nul
if errorlevel 1 (
  echo [error] npm is not in PATH
  pause
  exit /b 1
)

echo [build] Installing frontend dependencies...
cd /d "%FRONTEND_DIR%"
if exist package-lock.json (
  call npm ci
) else (
  call npm install
)
if errorlevel 1 (
  echo [error] Frontend dependency install failed
  pause
  exit /b 1
)

echo [build] Building frontend dist...
set VITE_BASE=/ui/
call npm run build
set VITE_BASE=
if errorlevel 1 (
  echo [error] Frontend build failed
  pause
  exit /b 1
)

echo [ok] Built frontend: %FRONTEND_DIR%\dist
pause
endlocal
