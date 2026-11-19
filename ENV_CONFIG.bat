@echo off
rem Keep the environment in a short path to avoid Windows MAX_PATH failures
rem when pip installs deeply nested PySide6 files.
set "GLPHOTO_VENV=%LOCALAPPDATA%\GLPvenv"
