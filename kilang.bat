@echo off
setlocal
cd /d "%~dp0"
set "CURRENT_DIR=%CD%"
if not defined HOST set "HOST=127.0.0.1"
if not defined PORT set "PORT=8501"

set "PY_CMD="
if exist "%CURRENT_DIR%\.venv\Scripts\python.exe" (
    "%CURRENT_DIR%\.venv\Scripts\python.exe" -c "import streamlit" >nul 2>nul
    if not errorlevel 1 (
        set "PY_CMD=%CURRENT_DIR%\.venv\Scripts\python.exe"
    )
)

if not defined PY_CMD (
    if exist "%APPDATA%\uv\python\cpython-3.11-windows-x86_64-none\python.exe" (
        set "PYTHONPATH=%CURRENT_DIR%;%CURRENT_DIR%\.venv\Lib\site-packages"
        "%APPDATA%\uv\python\cpython-3.11-windows-x86_64-none\python.exe" -c "import streamlit" >nul 2>nul
        if not errorlevel 1 (
            set "PY_CMD=%APPDATA%\uv\python\cpython-3.11-windows-x86_64-none\python.exe"
        )
    )
)

set "THEME_FLAGS=--theme.base=dark --theme.primaryColor=#10B981 --theme.backgroundColor=#0B1120 --theme.secondaryBackgroundColor=#111C33 --theme.textColor=#F1F5F9"

if not defined PY_CMD (
    where uv >nul 2>nul
    if not errorlevel 1 (
        echo ***** Memulakan Kilang Pemasaran melalui uv... *****
        uv run streamlit run webui\KilangStudio.py --server.address=%HOST% --server.port=%PORT% --browser.gatherUsageStats=false %THEME_FLAGS%
        exit /b %errorlevel%
    )
)

if not defined PY_CMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHONPATH=%CURRENT_DIR%;%CURRENT_DIR%\.venv\Lib\site-packages"
        set "PY_CMD=python"
    )
)

if not defined PY_CMD (
    echo ***** Python / venv tidak dijumpai. Sila jalankan 'uv sync --frozen' dahulu. *****
    pause
    exit /b 1
)

echo ***** Kilang Pemasaran WebUI: http://%HOST%:%PORT% *****
"%PY_CMD%" -m streamlit run webui\KilangStudio.py --server.address=%HOST% --server.port=%PORT% --browser.gatherUsageStats=false %THEME_FLAGS%
