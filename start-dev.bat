@echo off
setlocal
set SQL_TRACE=1

set ROOT_DIR=%~dp0
set BACKEND_DIR=%ROOT_DIR%backend
set FRONTEND_DIR=%ROOT_DIR%frontend
set VENV_DIR=%BACKEND_DIR%\.venv
set PYTHON=%VENV_DIR%\Scripts\python.exe
set "REPAIR_NO_PIC_ON_STARTUP=0"

:parse_args
if "%~1"=="" goto :args_done
if /I "%~1"=="--repair-no-pic" (
  set "REPAIR_NO_PIC_ON_STARTUP=1"
) else (
  echo [error] Unknown argument: %~1
  pause
  exit /b 1
)
shift
goto :parse_args

:args_done

where python >nul 2>nul
if errorlevel 1 (
  echo [error] python is not in PATH
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [error] npm is not in PATH
  pause
  exit /b 1
)

if not exist "%PYTHON%" (
  echo [setup] Creating backend venv...
  cd /d "%BACKEND_DIR%"
  python -m venv .venv
  if errorlevel 1 (
    echo [error] Failed to create backend venv
    pause
    exit /b 1
  )
)

echo [setup] Installing backend dependencies...
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

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [setup] Installing frontend dependencies...
  cd /d "%FRONTEND_DIR%"
  call npm.cmd install
  if errorlevel 1 (
    echo [error] Failed to install frontend dependencies
    pause
    exit /b 1
  )
)

echo [start] Starting frontend Vite dev server...
start "UnrealAssetExplorer Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && call npm.cmd run dev"

echo [start] Starting backend (foreground)...
cd /d "%BACKEND_DIR%"
set ASSET_SERVER_HOST=127.0.0.1
set ASSET_SERVER_PORT=7985
set ASSET_SERVER_LOG_LEVEL=info
set ASSET_SERVER_RELOAD=1
set ASSET_SERVER_CWD=%BACKEND_DIR%
if "%REPAIR_NO_PIC_ON_STARTUP%"=="1" set ASSET_NO_PIC_REPAIR_ON_STARTUP=1
start "" cmd /c "timeout /t 2 /nobreak >nul && start \"\" \"http://localhost:7985\""
call "%PYTHON%" -m uvicorn main:app --reload --host 127.0.0.1 --port 7985 --log-level info

echo Backend exited.
pause
endlocal
