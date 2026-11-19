@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ENV_CONFIG.bat"
echo.
echo ========================================================
echo Guia Lanka Photo Manager v0.1.2 - INSTALL LOCAL VISUAL AI
echo ========================================================
echo.
if not exist "%GLPHOTO_VENV%\Scripts\python.exe" (
  echo ERROR: Base application not installed. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
echo Step 1/3: Installing compatible CPU-only PyTorch and torchvision.
echo This is a large download; leave the window open until it finishes.
"%GLPHOTO_VENV%\Scripts\python.exe" -m pip install --upgrade --prefer-binary torch torchvision --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto failed
echo.
echo Step 2/3: Installing OpenCLIP and its supporting packages...
"%GLPHOTO_VENV%\Scripts\python.exe" -m pip install --prefer-binary -r requirements-ai.txt
if errorlevel 1 goto failed
echo.
echo Step 3/3: Verifying AI imports...
"%GLPHOTO_VENV%\Scripts\python.exe" -m app.ai_doctor
if errorlevel 1 goto failed
"%GLPHOTO_VENV%\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
echo.
echo SUCCESS: Local AI libraries are installed and import successfully.
echo Restart the application, select 2-5 photos, then click AI tag selected.
echo The first tagging run downloads trained model weights from the internet.
echo To verify the model separately, run DIAGNOSE_AI_WINDOWS.bat.
pause
exit /b 0
:failed
echo.
echo ERROR: Local AI installation or verification failed.
echo Run DIAGNOSE_AI_WINDOWS.bat and copy its output for troubleshooting.
pause
exit /b 1
