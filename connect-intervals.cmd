@echo off
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Install VitalDock in .venv first. See README.md.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m vitaldock connect-intervals
pause
