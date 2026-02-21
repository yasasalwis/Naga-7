@echo off
REM ############################################################################
REM N7-Sentinels Launcher (Windows)
REM Called by start.bat to run the Sentinels agent in its own console window.
REM Environment variables passed in by start.bat:
REM   N7_ROOT    — absolute path to the Naga-7 project root
REM   LOG_LEVEL  — INFO or DEBUG
REM ############################################################################

title N7-Sentinels

SET "SCRIPT_DIR=%N7_ROOT%"
IF "%SCRIPT_DIR%"=="" SET "SCRIPT_DIR=%~dp0"

SET "LOG_DIR=%SCRIPT_DIR%\logs"
IF NOT EXIST "%LOG_DIR%" MKDIR "%LOG_DIR%"

REM Resolve python
SET "PYTHON=python"
IF EXIST "%SCRIPT_DIR%\n7-sentinels\.venv\Scripts\python.exe" (
    SET "PYTHON=%SCRIPT_DIR%\n7-sentinels\.venv\Scripts\python.exe"
) ELSE IF EXIST "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    SET "PYTHON=%SCRIPT_DIR%\.venv\Scripts\python.exe"
)

IF "%LOG_LEVEL%"=="" SET "LOG_LEVEL=INFO"

CD /D "%SCRIPT_DIR%\n7-sentinels"
"%PYTHON%" main.py 2>&1 | tee "%LOG_DIR%\n7-sentinels.log"

echo.
echo --- N7-Sentinels process exited ---
pause
