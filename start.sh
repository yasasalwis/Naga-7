#!/bin/bash

################################################################################
# Naga-7 Development Startup Script
#
# Starts all Naga-7 services with a single command:
# - Infrastructure services (NATS, PostgreSQL, Redis) via Docker Compose
# - N7-Core services
# - N7-Sentinels agent
# - N7-Strikers agent
# - N7-Dashboard
#
# Each application service opens in its own terminal window/tab for easy
# real-time monitoring during development.
#
# Usage: ./start.sh [--skip-deps] [--no-windows] [--verbose]
#   --skip-deps:  Skip dependency installation (faster restarts)
#   --no-windows: Run all services in background (no new terminal windows)
#   --verbose:    Run Sentinels & Strikers with DEBUG log level
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

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

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()    { echo -e "${MAGENTA}[STEP]${NC} $1"; }

get_python_cmd() {
    if   [ -f ".venv/bin/python" ]; then echo ".venv/bin/python"
    elif [ -f "venv/bin/python"  ]; then echo "venv/bin/python"
    else echo "python3"; fi
}

get_pip_cmd() {
    if   [ -f ".venv/bin/pip" ]; then echo ".venv/bin/pip"
    elif [ -f "venv/bin/pip"  ]; then echo "venv/bin/pip"
    else echo "python3 -m pip"; fi
}

# ── Argument parsing ──────────────────────────────────────────────────────────
SKIP_DEPS=false
NO_WINDOWS=false
VERBOSE=false
for arg in "$@"; do
    case $arg in
        --skip-deps)  SKIP_DEPS=true;   shift ;;
        --no-windows) NO_WINDOWS=true;  shift ;;
        --verbose)    VERBOSE=true;     shift ;;
    esac
done

# ── Terminal window launcher ──────────────────────────────────────────────────
# Opens a named terminal window running a command in the given directory.
# Falls back to background process if no supported terminal is found.
open_terminal_window() {
    local title="$1"
    local dir="$2"
    local cmd="$3"       # command to run inside the window
    local log_file="$4"  # fallback log file when running in background

    if [ "$NO_WINDOWS" = true ]; then
        # Background mode — no new windows
        ( cd "$dir" && eval "$cmd" > "$log_file" 2>&1 ) &
        echo $!
        return
    fi

    # ── macOS: Terminal.app ──
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # Write a temp wrapper script so no quoting survives AppleScript boundaries.
        # IMPORTANT: declare and assign on ONE line — splitting onto two lines causes
        # 'local' to swallow mktemp's exit code, leaving wrapper empty on failure.
        local wrapper; wrapper=$(mktemp "/tmp/n7-start-${title// /_}-XXXXXX.sh")
        printf '#!/bin/bash\nprintf "\\033]0;%s\\007" "%s"\ncd "%s"\n%s\necho ""\necho "--- process exited (press Enter to close) ---"\nread\n' \
            "$title" "$title" "$dir" "$cmd" > "$wrapper"
        chmod +x "$wrapper"

        # Open a new Terminal window that executes the wrapper.
        osascript \
            -e 'tell application "Terminal"' \
            -e "    do script \"exec bash $(printf '%q' "$wrapper")\"" \
            -e '    activate' \
            -e 'end tell' \
            &>/dev/null

        # Return a dummy PID; the window manages its own process
        echo 0
        return
    fi

    # ── Linux: try common terminal emulators in preference order ──
    local launched=false
    for term in gnome-terminal konsole xterm xfce4-terminal lxterminal; do
        if command -v "$term" &>/dev/null; then
            case $term in
                gnome-terminal)
                    gnome-terminal --title="$title" -- bash -c "cd '$dir' && $cmd; echo '--- exited ---'; read" &
                    ;;
                konsole)
                    konsole --new-tab --title "$title" -e bash -c "cd '$dir' && $cmd; echo '--- exited ---'; read" &
                    ;;
                xfce4-terminal|lxterminal)
                    $term --title="$title" -e "bash -c \"cd '$dir' && $cmd; echo '--- exited ---'; read\"" &
                    ;;
                xterm)
                    xterm -title "$title" -e "bash -c \"cd '$dir' && $cmd; echo '--- exited ---'; read\"" &
                    ;;
            esac
            launched=true
            break
        fi
    done

    if [ "$launched" = false ]; then
        log_warning "No supported terminal emulator found — running '$title' in background"
        ( cd "$dir" && eval "$cmd" > "$log_file" 2>&1 ) &
    fi

    echo 0   # terminal manages its own process tree
}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/.naga7.pids"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# ── Cleanup ───────────────────────────────────────────────────────────────────
# On macOS a backgrounded subshell ( ... ) & starts in its own process group
# whose PGID == the subshell PID.  We kill the whole group with kill -- -$pgid.
_cleanup_called=0
cleanup() {
    [ "$_cleanup_called" -eq 1 ] && return
    _cleanup_called=1

    echo ""
    log_warning "Shutting down all Naga-7 services..."

    if [ -f "$PID_FILE" ]; then
        # Graceful SIGTERM to every recorded process group
        while IFS= read -r line || [ -n "$line" ]; do
            [ -z "$line" ] && continue
            pgid="${line%%:*}"
            label="${line##*:}"
            if kill -0 -- "-$pgid" 2>/dev/null; then
                log_info "Stopping $label (PGID $pgid)..."
                kill -TERM -- "-$pgid" 2>/dev/null || true
            fi
        done < "$PID_FILE"

        sleep 5   # allow graceful shutdown

        # Force-kill survivors
        while IFS= read -r line || [ -n "$line" ]; do
            [ -z "$line" ] && continue
            pgid="${line%%:*}"
            label="${line##*:}"
            if kill -0 -- "-$pgid" 2>/dev/null; then
                log_warning "Force-killing $label (PGID $pgid)..."
                kill -KILL -- "-$pgid" 2>/dev/null || true
            fi
        done < "$PID_FILE"

        rm -f "$PID_FILE"
    fi

    # Pattern-based sweep for any orphans not in the PID file
    for pattern in \
        "Naga-7/n7-core.*main\.py" \
        "Naga-7/n7-sentinels.*main\.py" \
        "Naga-7/n7-strikers.*main\.py" \
        "Naga-7/n7-dashboard"; do
        pids=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            log_warning "Killing orphan processes ($pattern): $pids"
            kill -TERM $pids 2>/dev/null || true
            sleep 1
            pids=$(pgrep -f "$pattern" 2>/dev/null || true)
            [ -n "$pids" ] && kill -KILL $pids 2>/dev/null || true
        fi
    done

    log_info "Stopping infrastructure services..."
    cd "$SCRIPT_DIR/deploy"
    docker-compose down 2>/dev/null || docker compose down 2>/dev/null || true

    log_success "All services stopped"
    exit 0
}

# Core runs inline (exec) so EXIT always fires when it stops.
# Sentinels/Strikers run in their own windows and manage their own processes.
trap cleanup SIGINT SIGTERM EXIT

# Clear PID file
> "$PID_FILE"

print_banner

# ============================================================================
# Step 1: Prerequisites
# ============================================================================
log_step "Step 1/7: Checking prerequisites..."

command -v python3 &>/dev/null || { log_error "Python 3 not found."; exit 1; }
log_success "Python $(python3 --version | awk '{print $2}') found"

command -v node &>/dev/null || { log_error "Node.js not found."; exit 1; }
log_success "Node.js $(node --version) found"

command -v docker &>/dev/null || { log_error "Docker not found."; exit 1; }
log_success "Docker found"

if ! docker info &>/dev/null; then
    log_warning "Docker daemon not running"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        log_info "Attempting to start Docker Desktop..."
        open -a Docker
        log_info "Waiting for Docker daemon (up to 60 s)..."
        for i in {1..60}; do
            docker info &>/dev/null && { log_success "Docker daemon started"; break; }
            [ $i -eq 60 ] && { log_error "Docker failed to start after 60 s"; exit 1; }
            sleep 1
        done
    else
        log_error "Docker daemon is not running. Please start Docker."; exit 1
    fi
else
    log_success "Docker daemon is running"
fi

command -v docker-compose &>/dev/null || docker compose version &>/dev/null \
    || { log_error "Docker Compose not found."; exit 1; }
log_success "Docker Compose found"

# ============================================================================
# Step 2: Infrastructure
# ============================================================================
log_step "Step 2/7: Starting infrastructure services (NATS, PostgreSQL, Redis)..."

cd "$SCRIPT_DIR/deploy"
docker-compose up -d
log_info "Waiting for services to be ready..."
sleep 5

docker-compose ps | grep -q "Up" \
    || { log_error "Infrastructure failed to start. Run: docker-compose logs"; exit 1; }

log_success "Infrastructure services started"
log_info "  NATS:       localhost:4222  (monitor: localhost:8222)"
log_info "  PostgreSQL: localhost:5432"
log_info "  Redis:      localhost:6379"
cd "$SCRIPT_DIR"

# ============================================================================
# Step 3: Python dependencies
# ============================================================================
if [ "$SKIP_DEPS" = false ]; then
    log_step "Step 3/8: Installing Python dependencies..."

    for component in n7-core n7-sentinels n7-strikers; do
        log_info "Installing $component dependencies..."
        cd "$SCRIPT_DIR/$component"
        PIP_CMD=$(get_pip_cmd)
        $PIP_CMD install -r requirements.txt > "$LOG_DIR/pip-${component}.log" 2>&1 || {
            log_error "Failed to install $component deps. See logs/pip-${component}.log"; exit 1
        }
    done

    log_success "Python dependencies installed"
    cd "$SCRIPT_DIR"
else
    log_warning "Skipping Python dependency installation (--skip-deps)"
fi

# ============================================================================
# Step 4: Dashboard dependencies
# ============================================================================
if [ "$SKIP_DEPS" = false ]; then
    log_step "Step 4/8: Installing dashboard dependencies..."
    cd "$SCRIPT_DIR/n7-dashboard"
    npm install > "$LOG_DIR/npm-install.log" 2>&1 || {
        log_error "Failed to install dashboard dependencies. See logs/npm-install.log"; exit 1
    }
    log_success "Dashboard dependencies installed"
    cd "$SCRIPT_DIR"
else
    log_warning "Skipping dashboard dependency installation (--skip-deps)"
fi

# ============================================================================
# Step 5: Database migrations
# ============================================================================
log_step "Step 5/8: Running database migrations..."

cd "$SCRIPT_DIR/n7-core"
if command -v alembic &>/dev/null; then
    ALEMBIC_CMD="alembic"
elif [ -f ".venv/bin/alembic" ]; then
    ALEMBIC_CMD=".venv/bin/alembic"
else
    PYTHON_CMD=$(get_python_cmd)
    ALEMBIC_CMD="$PYTHON_CMD -m alembic"
fi

$ALEMBIC_CMD upgrade head > "$LOG_DIR/alembic-migrate.log" 2>&1 || {
    log_error "Database migration failed. See logs/alembic-migrate.log"; exit 1
}
log_success "Database migrations completed"
cd "$SCRIPT_DIR"

# ============================================================================
# Step 6: N7-Sentinels & N7-Strikers  (open own windows, verbose/debug logs)
# ============================================================================
log_step "Step 6/8: Starting N7-Sentinels and N7-Strikers in separate windows..."

AGENT_LOG_LEVEL="INFO"
[ "$VERBOSE" = true ] && AGENT_LOG_LEVEL="DEBUG"

PYTHON_CMD=$(cd "$SCRIPT_DIR/n7-sentinels" && get_python_cmd)
SENTINEL_WINDOW_CMD="LOG_LEVEL=$AGENT_LOG_LEVEL $PYTHON_CMD main.py 2>&1 | tee '$LOG_DIR/n7-sentinels.log'"
SENTINEL_PID=$(open_terminal_window "N7-Sentinels" "$SCRIPT_DIR/n7-sentinels" "$SENTINEL_WINDOW_CMD" "$LOG_DIR/n7-sentinels.log")
if [ "$SENTINEL_PID" != "0" ]; then
    echo "${SENTINEL_PID}:N7-Sentinels" >> "$PID_FILE"
fi
log_success "N7-Sentinels started in new window ($AGENT_LOG_LEVEL)"
log_info "  Logs: logs/n7-sentinels.log"

PYTHON_CMD=$(cd "$SCRIPT_DIR/n7-strikers" && get_python_cmd)
STRIKER_WINDOW_CMD="LOG_LEVEL=$AGENT_LOG_LEVEL $PYTHON_CMD main.py 2>&1 | tee '$LOG_DIR/n7-strikers.log'"
STRIKER_PID=$(open_terminal_window "N7-Strikers" "$SCRIPT_DIR/n7-strikers" "$STRIKER_WINDOW_CMD" "$LOG_DIR/n7-strikers.log")
if [ "$STRIKER_PID" != "0" ]; then
    echo "${STRIKER_PID}:N7-Strikers" >> "$PID_FILE"
fi
log_success "N7-Strikers started in new window ($AGENT_LOG_LEVEL)"
log_info "  Logs: logs/n7-strikers.log"

cd "$SCRIPT_DIR"

# ============================================================================
# Step 7: N7-Dashboard  (background, logs to file)
# ============================================================================
log_step "Step 7/8: Starting N7-Dashboard (background)..."

cd "$SCRIPT_DIR/n7-dashboard"
( npm run dev > "$LOG_DIR/n7-dashboard.log" 2>&1 ) &
DASHBOARD_PID=$!
echo "${DASHBOARD_PID}:N7-Dashboard" >> "$PID_FILE"
log_success "N7-Dashboard started (PID: $DASHBOARD_PID)"
log_info "  Logs: logs/n7-dashboard.log"
cd "$SCRIPT_DIR"

# ============================================================================
# Step 8: N7-Core  (runs inline in THIS terminal — live output)
# ============================================================================
log_step "Step 8/8: Starting N7-Core (this terminal)..."
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                  ALL SERVICES STARTED                       ║${NC}"
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
echo -e "  ${GREEN}✓${NC} N7-Sentinels   — own window ($AGENT_LOG_LEVEL)"
echo -e "  ${GREEN}✓${NC} N7-Strikers    — own window ($AGENT_LOG_LEVEL)"
echo -e "  ${GREEN}✓${NC} N7-Dashboard   — background (PID: $DASHBOARD_PID)"
echo -e "  ${GREEN}✓${NC} N7-Core        — this terminal (live output below)"
echo ""
echo -e "${CYAN}Logs:${NC}"
echo -e "  ${YELLOW}logs/${NC}  — tail -f logs/*.log"
echo ""
echo -e "${YELLOW}Ctrl+C stops Core and all background services.${NC}"
echo -e "${YELLOW}Sentinel/Striker windows can be closed independently.${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

PYTHON_CMD=$(cd "$SCRIPT_DIR/n7-core" && get_python_cmd)
cd "$SCRIPT_DIR/n7-core"

# Run Core inline — output goes to terminal AND log file simultaneously.
# Ctrl+C will kill this process, triggering the cleanup trap.
exec $PYTHON_CMD main.py 2>&1 | tee "$LOG_DIR/n7-core.log"

# (Summary and Core startup are handled inline in Step 8 above)
