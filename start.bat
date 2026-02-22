@echo off
REM ############################################################################
REM Naga-7 Startup Script for Windows
REM 
REM This script starts all Naga-7 services with a single command:
REM - Infrastructure services (NATS, PostgreSQL, Redis) via Docker Compose
REM - N7-Core services
REM - N7-Sentinels agent
REM - N7-Strikers agent
REM - N7-Dashboard
REM
REM Usage: start.bat [--skip-deps]
REM   --skip-deps: Skip dependency installation (faster restarts)
REM ############################################################################

setlocal enabledelayedexpansion

REM Parse command line arguments
set SKIP_DEPS=false
:parse_args
if "%1"=="--skip-deps" set SKIP_DEPS=true
shift
if not "%1"=="" goto parse_args

REM Get script directory
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Create logs directory
if not exist "logs" mkdir logs

REM ASCII Art Banner
echo.
echo     ███╗   ██╗ █████╗  ██████╗  █████╗       ███████╗
echo     ████╗  ██║██╔══██╗██╔════╝ ██╔══██╗      ╚════██║
echo     ██╔██╗ ██║███████║██║  ███╗███████║█████╗  ███╔═╝
echo     ██║╚██╗██║██╔══██║██║   ██║██╔══██║╚════╝██╔══╝  
echo     ██║ ╚████║██║  ██║╚██████╔╝██║  ██║      ██║
echo     ╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝      ╚═╝
echo.
echo     Multi-Level AI Agent Security System
echo     Starting All Services...
echo.

REM ============================================================================
REM Step 1: Check Prerequisites
REM ============================================================================
echo [STEP] Step 1/7: Checking prerequisites...

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed. Please install Python 3.9 or higher.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [SUCCESS] Python %PYTHON_VERSION% found

REM Check for Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is not installed. Please install Node.js 18 or higher.
    pause
    exit /b 1
)
for /f "tokens=1" %%i in ('node --version') do set NODE_VERSION=%%i
echo [SUCCESS] Node.js %NODE_VERSION% found

REM Check for Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not installed. Please install Docker Desktop.
    pause
    exit /b 1
)
echo [SUCCESS] Docker found

REM Check for Docker Compose
docker-compose --version >nul 2>&1
if errorlevel 1 (
    docker compose version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Docker Compose is not installed. Please install Docker Compose.
        pause
        exit /b 1
    )
)
echo [SUCCESS] Docker Compose found

REM ============================================================================
REM Step 2: Install Python Dependencies
REM ============================================================================
if "%SKIP_DEPS%"=="false" (
    echo.
    echo [STEP] Step 2/8: Installing Python dependencies...
    
    echo [INFO] Installing n7-core dependencies...
    cd /d "%SCRIPT_DIR%\n7-core"
    pip install -r requirements.txt > "%SCRIPT_DIR%\logs\pip-core.log" 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to install n7-core dependencies. Check logs\pip-core.log
        pause
        exit /b 1
    )
    
    echo [INFO] Installing n7-sentinels dependencies...
    cd /d "%SCRIPT_DIR%\n7-sentinels"
    pip install -r requirements.txt > "%SCRIPT_DIR%\logs\pip-sentinels.log" 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to install n7-sentinels dependencies. Check logs\pip-sentinels.log
        pause
        exit /b 1
    )
    
    echo [INFO] Installing n7-strikers dependencies...
    cd /d "%SCRIPT_DIR%\n7-strikers"
    pip install -r requirements.txt > "%SCRIPT_DIR%\logs\pip-strikers.log" 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to install n7-strikers dependencies. Check logs\pip-strikers.log
        pause
        exit /b 1
    )
    
    echo [SUCCESS] Python dependencies installed
    cd /d "%SCRIPT_DIR%"
) else (
    echo [WARNING] Skipping Python dependency installation (--skip-deps)
)

REM ============================================================================
REM Step 3: Generate Certificates and NATS Auth
REM ============================================================================
echo.
echo [STEP] Step 3/8: Generating Certificates and NATS JWTs...
cd /d "%SCRIPT_DIR%\scripts"
python generate_certs_and_jwt.py
if errorlevel 1 (
    echo [ERROR] Failed to generate certificates.
    pause
    exit /b 1
)
cd /d "%SCRIPT_DIR%"

REM ============================================================================
REM Step 4: Start Infrastructure Services
REM ============================================================================
echo.
echo [STEP] Step 4/8: Starting infrastructure services (NATS, PostgreSQL, Redis)...

cd /d "%SCRIPT_DIR%\deploy"
docker-compose up -d
if errorlevel 1 (
    echo [ERROR] Failed to start infrastructure services
    pause
    exit /b 1
)

REM Wait for services to be ready
echo [INFO] Waiting for services to be ready...
timeout /t 5 /nobreak >nul

echo [SUCCESS] Infrastructure services started
echo [INFO]   - NATS: localhost:4222 (monitoring: localhost:8222)
echo [INFO]   - PostgreSQL: localhost:5432
echo [INFO]   - Redis: localhost:6379

cd /d "%SCRIPT_DIR%"

REM ============================================================================
REM Step 4: Install Dashboard Dependencies
REM ============================================================================
if "%SKIP_DEPS%"=="false" (
    echo.
    echo [STEP] Step 4/7: Installing dashboard dependencies...
    
    cd /d "%SCRIPT_DIR%\n7-dashboard"
    call npm install > "%SCRIPT_DIR%\logs\npm-install.log" 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to install dashboard dependencies. Check logs\npm-install.log
        pause
        exit /b 1
    )
    
    echo [SUCCESS] Dashboard dependencies installed
    cd /d "%SCRIPT_DIR%"
) else (
    echo [WARNING] Skipping dashboard dependency installation (--skip-deps)
)

REM ============================================================================
REM Step 5: Start N7-Core
REM ============================================================================
echo.
echo [STEP] Step 5/7: Starting N7-Core services...

cd /d "%SCRIPT_DIR%\n7-core"
start "N7-Core" /min cmd /c "python main.py > ..\logs\n7-core.log 2>&1"
echo [SUCCESS] N7-Core started
echo [INFO]   Logs: logs\n7-core.log

REM Give core services time to initialize
timeout /t 3 /nobreak >nul

REM ============================================================================
REM Step 6: Start N7-Sentinels and N7-Strikers
REM ============================================================================
echo.
echo [STEP] Step 6/7: Starting N7-Sentinels and N7-Strikers...

cd /d "%SCRIPT_DIR%\n7-sentinels"
start "N7-Sentinels" /min cmd /c "python main.py > ..\logs\n7-sentinels.log 2>&1"
echo [SUCCESS] N7-Sentinels started
echo [INFO]   Logs: logs\n7-sentinels.log

cd /d "%SCRIPT_DIR%\n7-strikers"
start "N7-Strikers" /min cmd /c "python main.py > ..\logs\n7-strikers.log 2>&1"
echo [SUCCESS] N7-Strikers started
echo [INFO]   Logs: logs\n7-strikers.log

REM ============================================================================
REM Step 7: Start N7-Dashboard
REM ============================================================================
echo.
echo [STEP] Step 7/7: Starting N7-Dashboard...

cd /d "%SCRIPT_DIR%\n7-dashboard"
start "N7-Dashboard" /min cmd /c "npm run dev > ..\logs\n7-dashboard.log 2>&1"
echo [SUCCESS] N7-Dashboard started
echo [INFO]   Logs: logs\n7-dashboard.log

cd /d "%SCRIPT_DIR%"

REM ============================================================================
REM All Services Started
REM ============================================================================
timeout /t 2 /nobreak >nul

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║                 ALL SERVICES STARTED                        ║
echo ╚════════════════════════════════════════════════════════════╝
echo.
echo Access Points:
echo   Dashboard:       http://localhost:5173
echo   API Gateway:     http://localhost:8000
echo   API Docs:        http://localhost:8000/docs
echo   NATS Monitor:    http://localhost:8222
echo.
echo Service Status:
echo   √ Infrastructure (NATS, PostgreSQL, Redis)
echo   √ N7-Core
echo   √ N7-Sentinels
echo   √ N7-Strikers
echo   √ N7-Dashboard
echo.
echo Logs:
echo   View all logs in: logs\
echo.
echo Services are running in separate windows.
echo To stop services, close the individual windows or run: scripts\stop.bat
echo.
pause
