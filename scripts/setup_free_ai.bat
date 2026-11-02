@echo off
REM One-time setup of the free AI pieces (Gemini key, Tamil/English voices, image model).
cd /d "%~dp0\.."
if not exist backend\.venv\Scripts\python.exe (
  echo Please run scripts\start.bat once first, then run this again.
  pause
  exit /b 1
)
backend\.venv\Scripts\python.exe scripts\setup_free_ai.py
