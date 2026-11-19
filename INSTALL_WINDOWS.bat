@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ENV_CONFIG.bat"
echo.
echo Guia Lanka Photo Manager - Windows installer v1.0.0-rc1
echo Virtual environment: %GLPHOTO_VENV%
echo.
where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python launcher not found.
  echo Install 64-bit Python 3.11, 3.12 or 3.13 from python.org.
  echo Include the Python launcher during installation.
  pause
  exit /b 1
)
set "PY_VER="
py -3.13 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY_VER=-3.13"
if not defined PY_VER (
  py -3.12 -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PY_VER=-3.12"
)
if not defined PY_VER (
  py -3.11 -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PY_VER=-3.11"
)
if not defined PY_VER (
  echo ERROR: No supported Python version found.
  echo Install 64-bit Python 3.11, 3.12 or 3.13.
  pause
  exit /b 1
)
if not exist "%GLPHOTO_VENV%\Scripts\python.exe" (
  echo Creating short-path environment with Python %PY_VER% ...
  py %PY_VER% -m venv "%GLPHOTO_VENV%"
  if errorlevel 1 (
    echo ERROR: Could not create Python environment.
    pause
    exit /b 1
  )
)
echo Upgrading pip ...
"%GLPHOTO_VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo ERROR: Could not upgrade pip.
  pause
  exit /b 1
)
echo Installing application libraries ...
"%GLPHOTO_VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERROR: Installation failed. Check the message above.
  echo Note: This version installs into a short path to avoid PySide6 path errors.
  pause
  exit /b 1
)
echo.
echo Installation completed successfully.
echo Run START_WINDOWS.bat to launch the app.
echo IMPORTANT: Image recognition is NOT installed by this base setup.
echo For AI tagging run INSTALL_AI_WINDOWS.bat, then DIAGNOSE_AI_WINDOWS.bat.
echo Older .venv folders inside the project are no longer used and can be deleted.
pause
