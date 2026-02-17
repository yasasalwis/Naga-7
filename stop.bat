@echo off
REM ############################################################################
REM Naga-7 Stop Script for Windows
REM 
REM This script stops all Naga-7 services:
REM - All Python services (N7-Core, N7-Sentinels, N7-Strikers)
REM - Dashboard service
REM - Infrastructure services (NATS, PostgreSQL, Redis) via Docker Compose
REM
REM Usage: stop.bat [--keep-infra]
REM   --keep-infra: Keep infrastructure services running (only stop app services)
REM ############################################################################

setlocal enabledelayedexpansion

REM Parse command line arguments
set KEEP_INFRA=false
:parse_args
if "%1"=="--keep-infra" set KEEP_INFRA=true
shift
if not "%1"=="" goto parse_args

REM Get script directory
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo [INFO] Stopping Naga-7 services...
echo.

REM Stop application services by window title
echo [INFO] Stopping application services...
taskkill /FI "WINDOWTITLE eq N7-Core*" /F >nul 2>&1
if not errorlevel 1 echo [SUCCESS] Stopped N7-Core

taskkill /FI "WINDOWTITLE eq N7-Sentinels*" /F >nul 2>&1
if not errorlevel 1 echo [SUCCESS] Stopped N7-Sentinels

taskkill /FI "WINDOWTITLE eq N7-Strikers*" /F >nul 2>&1
if not errorlevel 1 echo [SUCCESS] Stopped N7-Strikers

taskkill /FI "WINDOWTITLE eq N7-Dashboard*" /F >nul 2>&1
if not errorlevel 1 echo [SUCCESS] Stopped N7-Dashboard

REM Stop infrastructure services
if "%KEEP_INFRA%"=="false" (
    echo [INFO] Stopping infrastructure services...
    cd /d "%SCRIPT_DIR%\deploy"
    docker-compose down >nul 2>&1
    if not errorlevel 1 echo [SUCCESS] Infrastructure services stopped
) else (
    echo [WARNING] Keeping infrastructure services running (--keep-infra)
)

cd /d "%SCRIPT_DIR%"

echo.
echo [SUCCESS] All services stopped successfully
echo.
pause
