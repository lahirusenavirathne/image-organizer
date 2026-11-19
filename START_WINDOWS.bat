@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ENV_CONFIG.bat"
if not exist "%GLPHOTO_VENV%\Scripts\python.exe" (
  echo Environment not found: %GLPHOTO_VENV%
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
"%GLPHOTO_VENV%\Scripts\python.exe" -m app.main
if errorlevel 1 pause
