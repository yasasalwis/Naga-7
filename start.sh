#!/bin/bash

################################################################################
# Naga-7 Startup Script
# 
# This script starts all Naga-7 services with a single command:
# - Infrastructure services (NATS, PostgreSQL, Redis) via Docker Compose
# - N7-Core services
# - N7-Sentinels agent
# - N7-Strikers agent
# - N7-Dashboard
#
# Usage: ./start.sh [--skip-deps] [--verbose]
#   --skip-deps: Skip dependency installation (faster restarts)
#   --verbose:   Show real-time logs from all services in terminal
################################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ASCII Art Banner
print_banner() {
    echo -e "${CYAN}"
    cat << "EOF"
    ███╗   ██╗ █████╗  ██████╗  █████╗       ███████╗
    ████╗  ██║██╔══██╗██╔════╝ ██╔══██╗      ╚════██║
    ██╔██╗ ██║███████║██║  ███╗███████║█████╗  ███╔═╝
    ██║╚██╗██║██╔══██║██║   ██║██╔══██║╚════╝██╔══╝  
    ██║ ╚████║██║  ██║╚██████╔╝██║  ██║      ██║
    ╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝      ╚═╝
    
    Multi-Level AI Agent Security System
    Starting All Services...
EOF
    echo -e "${NC}"
}

# Log functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${MAGENTA}[STEP]${NC} $1"
}

# Parse command line arguments
SKIP_DEPS=false
VERBOSE=false
for arg in "$@"; do
    case $arg in
        --skip-deps)
            SKIP_DEPS=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# PID file for tracking processes
PID_FILE="$SCRIPT_DIR/.naga7.pids"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Cleanup function
cleanup() {
    log_warning "Shutting down all services..."
    
    # Kill all processes tracked in PID file
    if [ -f "$PID_FILE" ]; then
        while read -r pid; do
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                log_info "Stopping process $pid and its children..."
                # Try graceful termination first (kills process group)
                kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
                
                # Wait a moment for graceful shutdown
                sleep 1
                
                # Force kill if still running
                if kill -0 "$pid" 2>/dev/null; then
                    log_info "Force killing process $pid..."
                    kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
                fi
            fi
        done < "$PID_FILE"
        rm "$PID_FILE"
    fi
    
    # Stop Docker services
    log_info "Stopping infrastructure services..."
    cd "$SCRIPT_DIR/deploy"
    docker-compose down 2>/dev/null || true
    
    log_success "All services stopped"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM EXIT

# Clear PID file
> "$PID_FILE"

print_banner

# ============================================================================
# Step 1: Check Prerequisites
# ============================================================================
log_step "Step 1/7: Checking prerequisites..."

# Check for Python
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
log_success "Python $PYTHON_VERSION found"

# Check for Node.js
if ! command -v node &> /dev/null; then
    log_error "Node.js is not installed. Please install Node.js 18 or higher."
    exit 1
fi
NODE_VERSION=$(node --version)
log_success "Node.js $NODE_VERSION found"

# Check for Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed. Please install Docker."
    exit 1
fi
log_success "Docker found"

# Check if Docker daemon is running (macOS specific)
if ! docker info &> /dev/null; then
    log_warning "Docker daemon is not running"
    
    # Check if running on macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        log_info "Attempting to start Docker Desktop..."
        
        # Start Docker Desktop
        open -a Docker
        
        # Wait for Docker to start (max 60 seconds)
        log_info "Waiting for Docker daemon to start..."
        for i in {1..60}; do
            if docker info &> /dev/null; then
                log_success "Docker daemon is now running"
                break
            fi
            
            if [ $i -eq 60 ]; then
                log_error "Docker daemon failed to start after 60 seconds"
                log_error "Please start Docker Desktop manually and try again"
                exit 1
            fi
            
            sleep 1
        done
    else
        log_error "Docker daemon is not running. Please start Docker and try again."
        exit 1
    fi
else
    log_success "Docker daemon is running"
fi

# Check for Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    log_error "Docker Compose is not installed. Please install Docker Compose."
    exit 1
fi
log_success "Docker Compose found"

# ============================================================================
# Step 2: Start Infrastructure Services
# ============================================================================
log_step "Step 2/7: Starting infrastructure services (NATS, PostgreSQL, Redis)..."

cd "$SCRIPT_DIR/deploy"
docker-compose up -d

# Wait for services to be ready
log_info "Waiting for services to be ready..."
sleep 5

# Verify services are running
if ! docker-compose ps | grep -q "Up"; then
    log_error "Infrastructure services failed to start. Check 'docker-compose logs'"
    exit 1
fi

log_success "Infrastructure services started"
log_info "  - NATS: localhost:4222 (monitoring: localhost:8222)"
log_info "  - PostgreSQL: localhost:5432"
log_info "  - Redis: localhost:6379"

cd "$SCRIPT_DIR"

# ============================================================================
# Step 3: Install Python Dependencies
# ============================================================================
if [ "$SKIP_DEPS" = false ]; then
    log_step "Step 3/8: Installing Python dependencies..."
    
    log_info "Installing n7-core dependencies..."
    cd "$SCRIPT_DIR/n7-core"
    pip install -r requirements.txt > "$LOG_DIR/pip-core.log" 2>&1 || {
        log_error "Failed to install n7-core dependencies. Check logs/pip-core.log"
        exit 1
    }
    
    log_info "Installing n7-sentinels dependencies..."
    cd "$SCRIPT_DIR/n7-sentinels"
    pip install -r requirements.txt > "$LOG_DIR/pip-sentinels.log" 2>&1 || {
        log_error "Failed to install n7-sentinels dependencies. Check logs/pip-sentinels.log"
        exit 1
    }
    
    log_info "Installing n7-strikers dependencies..."
    cd "$SCRIPT_DIR/n7-strikers"
    pip install -r requirements.txt > "$LOG_DIR/pip-strikers.log" 2>&1 || {
        log_error "Failed to install n7-strikers dependencies. Check logs/pip-strikers.log"
        exit 1
    }
    
    log_success "Python dependencies installed"
    cd "$SCRIPT_DIR"
else
    log_warning "Skipping Python dependency installation (--skip-deps)"
fi

# ============================================================================
# Step 4: Install Dashboard Dependencies
# ============================================================================
if [ "$SKIP_DEPS" = false ]; then
    log_step "Step 4/8: Installing dashboard dependencies..."
    
    cd "$SCRIPT_DIR/n7-dashboard"
    npm install > "$LOG_DIR/npm-install.log" 2>&1 || {
        log_error "Failed to install dashboard dependencies. Check logs/npm-install.log"
        exit 1
    }
    
    log_success "Dashboard dependencies installed"
    cd "$SCRIPT_DIR"
else
    log_warning "Skipping dashboard dependency installation (--skip-deps)"
fi

# ============================================================================
# Step 5: Run Database Migrations
# ============================================================================
log_step "Step 5/8: Running database migrations..."

cd "$SCRIPT_DIR/n7-core"

# Check if alembic is installed
if ! command -v alembic &> /dev/null; then
    log_warning "Alembic not found in PATH, trying with python -m alembic..."
    ALEMBIC_CMD="python3 -m alembic"
else
    ALEMBIC_CMD="alembic"
fi

# Run migrations
log_info "Applying database migrations..."
$ALEMBIC_CMD upgrade head > "$LOG_DIR/alembic-migrate.log" 2>&1 || {
    log_error "Database migration failed. Check logs/alembic-migrate.log"
    exit 1
}

log_success "Database migrations completed"
cd "$SCRIPT_DIR"

# ============================================================================
# Step 6: Start N7-Core
# ============================================================================
log_step "Step 6/8: Starting N7-Core services..."

cd "$SCRIPT_DIR/n7-core"
if [ "$VERBOSE" = true ]; then
    python3 main.py 2>&1 | sed "s/^/[CORE] /" | tee "$LOG_DIR/n7-core.log" &
else
    python3 main.py > "$LOG_DIR/n7-core.log" 2>&1 &
fi
CORE_PID=$!
echo "$CORE_PID" >> "$PID_FILE"
log_success "N7-Core started (PID: $CORE_PID)"
if [ "$VERBOSE" = false ]; then
    log_info "  Logs: logs/n7-core.log"
fi

# Give core services time to initialize
sleep 3

# ============================================================================
# Step 7: Start N7-Sentinels and N7-Strikers
# ============================================================================
log_step "Step 7/8: Starting N7-Sentinels and N7-Strikers..."

cd "$SCRIPT_DIR/n7-sentinels"
if [ "$VERBOSE" = true ]; then
    python3 main.py 2>&1 | sed "s/^/[SENTINELS] /" | tee "$LOG_DIR/n7-sentinels.log" &
else
    python3 main.py > "$LOG_DIR/n7-sentinels.log" 2>&1 &
fi
SENTINEL_PID=$!
echo "$SENTINEL_PID" >> "$PID_FILE"
log_success "N7-Sentinels started (PID: $SENTINEL_PID)"
if [ "$VERBOSE" = false ]; then
    log_info "  Logs: logs/n7-sentinels.log"
fi

cd "$SCRIPT_DIR/n7-strikers"
if [ "$VERBOSE" = true ]; then
    python3 main.py 2>&1 | sed "s/^/[STRIKERS] /" | tee "$LOG_DIR/n7-strikers.log" &
else
    python3 main.py > "$LOG_DIR/n7-strikers.log" 2>&1 &
fi
STRIKER_PID=$!
echo "$STRIKER_PID" >> "$PID_FILE"
log_success "N7-Strikers started (PID: $STRIKER_PID)"
if [ "$VERBOSE" = false ]; then
    log_info "  Logs: logs/n7-strikers.log"
fi

# ============================================================================
# Step 8: Start N7-Dashboard
# ============================================================================
log_step "Step 8/8: Starting N7-Dashboard..."

cd "$SCRIPT_DIR/n7-dashboard"
if [ "$VERBOSE" = true ]; then
    npm run dev 2>&1 | sed "s/^/[DASHBOARD] /" | tee "$LOG_DIR/n7-dashboard.log" &
else
    npm run dev > "$LOG_DIR/n7-dashboard.log" 2>&1 &
fi
DASHBOARD_PID=$!
echo "$DASHBOARD_PID" >> "$PID_FILE"
log_success "N7-Dashboard started (PID: $DASHBOARD_PID)"
if [ "$VERBOSE" = false ]; then
    log_info "  Logs: logs/n7-dashboard.log"
fi

cd "$SCRIPT_DIR"

# ============================================================================
# All Services Started
# ============================================================================
sleep 2

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                 ALL SERVICES STARTED                        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Access Points:${NC}"
echo -e "  ${YELLOW}Dashboard:${NC}       http://localhost:5173"
echo -e "  ${YELLOW}API Gateway:${NC}     http://localhost:8000"
echo -e "  ${YELLOW}API Docs:${NC}        http://localhost:8000/docs"
echo -e "  ${YELLOW}NATS Monitor:${NC}    http://localhost:8222"
echo ""
echo -e "${CYAN}Service Status:${NC}"
echo -e "  ${GREEN}✓${NC} Infrastructure (NATS, PostgreSQL, Redis)"
echo -e "  ${GREEN}✓${NC} N7-Core (PID: $CORE_PID)"
echo -e "  ${GREEN}✓${NC} N7-Sentinels (PID: $SENTINEL_PID)"
echo -e "  ${GREEN}✓${NC} N7-Strikers (PID: $STRIKER_PID)"
echo -e "  ${GREEN}✓${NC} N7-Dashboard (PID: $DASHBOARD_PID)"
echo ""
if [ "$VERBOSE" = false ]; then
    echo -e "${CYAN}Logs:${NC}"
    echo -e "  View all logs in: ${YELLOW}logs/${NC}"
    echo -e "  Monitor activity: ${YELLOW}tail -f logs/*.log${NC}"
    echo ""
else
    echo -e "${CYAN}Verbose Mode:${NC} Real-time logs displayed below"
    echo -e "  Logs are also saved to: ${YELLOW}logs/${NC}"
    echo ""
fi
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait indefinitely (services will be stopped by cleanup function on Ctrl+C)
tail -f /dev/null
