#!/bin/bash

################################################################################
# Naga-7 Stop Script
#
# Stops all Naga-7 services:
# - N7-Core, N7-Sentinels, N7-Strikers (Python)
# - N7-Dashboard (Vite / Node)
# - Infrastructure services (NATS, PostgreSQL, Redis) via Docker Compose
#
# Usage: ./stop.sh [--keep-infra]
#   --keep-infra: Keep infrastructure services running (only stop app services)
################################################################################

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Parse arguments
KEEP_INFRA=false
for arg in "$@"; do
    case $arg in
        --keep-infra) KEEP_INFRA=true; shift ;;
    esac
done

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/.naga7.pids"

echo ""
log_info "Stopping Naga-7 services..."
echo ""

# ── Kill by process groups recorded in PID file ───────────────────────────────
# Each line is written as "PID:Label" by start.sh.
# A backgrounded subshell ( ... ) & on macOS runs in its own process group
# where PGID == the subshell PID, so kill -- -$pgid kills the whole tree.
if [ -f "$PID_FILE" ]; then
    log_info "Stopping tracked application services..."

    # Graceful SIGTERM first
    while IFS= read -r line || [ -n "$line" ]; do
        [ -z "$line" ] && continue
        pgid="${line%%:*}"
        label="${line##*:}"
        if kill -0 -- "-$pgid" 2>/dev/null; then
            log_info "Stopping $label (PID $pgid)..."
            kill -TERM -- "-$pgid" 2>/dev/null || true
        fi
    done < "$PID_FILE"

    # Wait up to 5 s for graceful exit
    sleep 5

    # Force-kill anything still alive
    while IFS= read -r line || [ -n "$line" ]; do
        [ -z "$line" ] && continue
        pgid="${line%%:*}"
        label="${line##*:}"
        if kill -0 -- "-$pgid" 2>/dev/null; then
            log_warning "Force-killing $label (PID $pgid)..."
            kill -KILL -- "-$pgid" 2>/dev/null || true
        fi
    done < "$PID_FILE"

    rm -f "$PID_FILE"
    log_success "Tracked processes stopped"
else
    log_warning "No PID file found — using pattern-based kill only"
fi

# ── Pattern-based sweep (catches orphans / manual starts) ─────────────────────
# pgrep -f matches against the full command line including working directory,
# so "Naga-7/n7-*/main.py" reliably identifies our processes even when argv[0]
# is just "main.py".
for pattern in \
    "Naga-7/n7-core.*main\.py" \
    "Naga-7/n7-sentinels.*main\.py" \
    "Naga-7/n7-strikers.*main\.py" \
    "Naga-7/n7-dashboard"; do
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        log_warning "Killing orphan processes ($pattern): $pids"
        kill -TERM $pids 2>/dev/null || true
    fi
done

# Brief wait then force-kill survivors
sleep 2
for pattern in \
    "Naga-7/n7-core.*main\.py" \
    "Naga-7/n7-sentinels.*main\.py" \
    "Naga-7/n7-strikers.*main\.py" \
    "Naga-7/n7-dashboard"; do
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    [ -n "$pids" ] && kill -KILL $pids 2>/dev/null || true
done

# ── Port-based cleanup (last resort) ─────────────────────────────────────────
for port in 8000 5173; do
    pids=$(lsof -ti:$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        log_warning "Force-killing process(es) still on port $port: $pids"
        kill -KILL $pids 2>/dev/null || true
        log_success "Port $port cleared"
    fi
done

# ── Infrastructure ─────────────────────────────────────────────────────────────
if [ "$KEEP_INFRA" = false ]; then
    log_info "Stopping infrastructure services..."
    cd "$SCRIPT_DIR/deploy"
    docker-compose down 2>/dev/null || docker compose down 2>/dev/null || true
    log_success "Infrastructure services stopped"
else
    log_warning "Keeping infrastructure services running (--keep-infra)"
fi

echo ""
log_success "All services stopped"
echo ""
