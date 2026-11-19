@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ENV_CONFIG.bat"
if not exist "%GLPHOTO_VENV%\Scripts\python.exe" (
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
"%GLPHOTO_VENV%\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 (
  echo Could not install PyInstaller.
  pause
  exit /b 1
)
"%GLPHOTO_VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name GuiaLankaPhotoManager --collect-all PySide6 --collect-all cv2 --collect-all PIL --collect-all numpy launch.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
echo Executable folder: dist\GuiaLankaPhotoManager
pause
