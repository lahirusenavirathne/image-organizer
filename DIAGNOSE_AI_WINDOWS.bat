@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ENV_CONFIG.bat"
echo.
echo Checking local AI installation and running a model test...
echo This may download the pretrained model on the first run.
echo.
if not exist "%GLPHOTO_VENV%\Scripts\python.exe" (
  echo ERROR: Python environment missing. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
set "LOG=%TEMP%\GLPhoto_AI_Diagnostics.txt"
"%GLPHOTO_VENV%\Scripts\python.exe" -m app.ai_doctor --model > "%LOG%" 2>&1
set "CHECK_RC=%ERRORLEVEL%"
type "%LOG%"
echo.
echo Diagnostics saved to: %LOG%
if not "%CHECK_RC%"=="0" (
  echo.
  echo AI diagnostic FAILED. Copy the error above and send it for support.
  pause
  exit /b 1
)
echo.
echo AI diagnostic PASSED.
pause
