@echo off
cd /d "%~dp0"
set "MONITOR_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%MONITOR_PY%" (
  start "" "%MONITOR_PY%" "%~dp0pc_monitor.py"
  exit /b
)
py -3.12 "%~dp0pc_monitor.py"
if errorlevel 1 pause
