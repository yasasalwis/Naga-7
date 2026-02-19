#!/bin/bash

################################################################################
# Naga-7 Stop Script
# 
# This script stops all Naga-7 services:
# - All Python services (N7-Core, N7-Sentinels, N7-Strikers)
# - Dashboard service
# - Infrastructure services (NATS, PostgreSQL, Redis) via Docker Compose
#
# Usage: ./stop.sh [--keep-infra]
#   --keep-infra: Keep infrastructure services running (only stop app services)
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Parse command line arguments
KEEP_INFRA=false
for arg in "$@"; do
    case $arg in
        --keep-infra)
            KEEP_INFRA=true
            shift
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/.naga7.pids"

echo ""
log_info "Stopping Naga-7 services..."
echo ""

# Stop processes tracked in PID file
if [ -f "$PID_FILE" ]; then
    log_info "Stopping application services..."
    while read -r pid; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            log_success "Stopped process $pid"
        fi
    done < "$PID_FILE"
    rm "$PID_FILE"
else
    log_warning "No PID file found. Attempting to stop services by name..."
    
    # Try to stop by process name
    pkill -f "n7-core/main.py" 2>/dev/null && log_success "Stopped N7-Core" || true
    pkill -f "n7-sentinels/main.py" 2>/dev/null && log_success "Stopped N7-Sentinels" || true
    pkill -f "n7-strikers/main.py" 2>/dev/null && log_success "Stopped N7-Strikers" || true
    pkill -f "vite" 2>/dev/null && log_success "Stopped N7-Dashboard" || true

    # Force kill processes on ports if still running
    if lsof -ti:8000 >/dev/null; then
        log_warning "Force killing process on port 8000..."
        kill -9 $(lsof -ti:8000) 2>/dev/null || true
        log_success "Killed process on port 8000"
    fi
    if lsof -ti:5173 >/dev/null; then
        log_warning "Force killing process on port 5173..."
        kill -9 $(lsof -ti:5173) 2>/dev/null || true
        log_success "Killed process on port 5173"
    fi
fi

# Stop infrastructure services
if [ "$KEEP_INFRA" = false ]; then
    log_info "Stopping infrastructure services..."
    cd "$SCRIPT_DIR/deploy"
    docker-compose down 2>/dev/null || true
    log_success "Infrastructure services stopped"
else
    log_warning "Keeping infrastructure services running (--keep-infra)"
fi

echo ""
log_success "All services stopped successfully"
echo ""
