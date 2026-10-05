@echo off
rem Start Arqade (after setup.bat). Extra args go to `python -m arqade`, e.g. run.bat --port 9000
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m arqade %*
