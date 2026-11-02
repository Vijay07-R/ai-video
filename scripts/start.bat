@echo off
REM Animal Video Engine - one-click start for Windows (no Docker needed).
REM Needs: Python 3.10+ and FFmpeg on PATH. Node.js only for the first UI build.
setlocal
cd /d "%~dp0\.."

where ffmpeg >nul 2>nul || (echo [!] FFmpeg not found. Install it: winget install Gyan.FFmpeg  & pause & exit /b 1)

if not exist backend\.venv (
  echo Creating Python environment...
  python -m venv backend\.venv || (echo [!] Python not found. Install Python 3.10+ from python.org & pause & exit /b 1)
)
call backend\.venv\Scripts\activate.bat
pip install -q -r backend\requirements.txt

if not exist backend\.env copy backend\.env.example backend\.env >nul

if not exist frontend\dist\index.html (
  where npm >nul 2>nul || (echo [!] Node.js needed once to build the UI: winget install OpenJS.NodeJS.LTS & pause & exit /b 1)
  pushd frontend
  call npm install --no-audit --no-fund
  call npm run build
  popd
)

echo.
echo  Engine running at  http://localhost:8000   (Ctrl+C to stop)
echo.
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
