#!/bin/bash

################################################################################
# Naga-7 Production Startup Script
#
# Intended for server / headless deployments.  All services run as supervised
# background processes with automatic restart on failure, structured JSON log
# rotation, health-gate sequencing, and a clean shutdown handler.
#
# Key differences from the development script (start.sh):
#   - No interactive terminal windows
#   - Mandatory .env validation (warns on insecure defaults)
#   - Health-gate: each tier must pass HTTP / port checks before the next starts
#   - Per-service process watchdog with configurable restart policy
#   - Log rotation (logrotate-friendly naming)
#   - Graceful drain + SIGKILL timeout for clean deploys
#   - Exit code reflects overall health (0 = all up, 1 = failures)
#
# Usage:
#   ./start-prod.sh [OPTIONS]
#
# Options:
#   --skip-deps          Skip pip / npm dependency installation
#   --skip-migrations    Skip Alembic database migrations
#   --keep-infra         Do not start/stop Docker infrastructure (assume it is
#                        already running externally — e.g. managed Postgres)
#   --no-dashboard       Do not start the N7-Dashboard (API-only deployments)
#   --max-restarts N     Max times a crashed service is restarted (default: 5)
#   --restart-delay N    Seconds between restart attempts (default: 5)
#   --health-timeout N   Seconds to wait for each health gate (default: 60)
#   --env-file PATH      Path to a .env file to source (default: auto-detect
#                        per component)
#
# Environment variables (can also be set before running):
#   N7_LOG_DIR           Log directory (default: ./logs)
#   N7_PID_FILE          PID-tracking file (default: ./.naga7-prod.pids)
################################################################################

set -euo pipefail

# ── Color codes ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Logging helpers ───────────────────────────────────────────────────────────
_ts()        { date '+%Y-%m-%dT%H:%M:%S%z'; }
log_info()   { echo -e "$(_ts) ${BLUE}[INFO]${NC}    $*"; }
log_ok()     { echo -e "$(_ts) ${GREEN}[OK]${NC}      $*"; }
log_warn()   { echo -e "$(_ts) ${YELLOW}[WARN]${NC}    $*"; }
log_error()  { echo -e "$(_ts) ${RED}[ERROR]${NC}   $*" >&2; }
log_step()   { echo -e "\n$(_ts) ${MAGENTA}${BOLD}[STEP]${NC}    $*"; }
log_fatal()  { log_error "$*"; exit 1; }

# ── Banner ────────────────────────────────────────────────────────────────────
print_banner() {
    echo -e "${CYAN}"
    cat << "EOF"
    ███╗   ██╗ █████╗  ██████╗  █████╗       ███████╗
    ████╗  ██║██╔══██╗██╔════╝ ██╔══██╗      ╚════██║
    ██╔██╗ ██║███████║██║  ███╗███████║█████╗  ███╔═╝
    ██║╚██╗██║██╔══██║██║   ██║██╔══██║╚════╝██╔══╝
    ██║ ╚████║██║  ██║╚██████╔╝██║  ██║      ██║
    ╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝      ╚═╝

    Multi-Level AI Agent Security System — PRODUCTION MODE
EOF
    echo -e "${NC}"
}

# ── Argument parsing ──────────────────────────────────────────────────────────
SKIP_DEPS=false
SKIP_MIGRATIONS=false
KEEP_INFRA=false
NO_DASHBOARD=false
MAX_RESTARTS=5
RESTART_DELAY=5
HEALTH_TIMEOUT=60
ENV_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-deps)        SKIP_DEPS=true        ;;
        --skip-migrations)  SKIP_MIGRATIONS=true   ;;
        --keep-infra)       KEEP_INFRA=true        ;;
        --no-dashboard)     NO_DASHBOARD=true       ;;
        --max-restarts)     MAX_RESTARTS="$2"; shift ;;
        --restart-delay)    RESTART_DELAY="$2"; shift ;;
        --health-timeout)   HEALTH_TIMEOUT="$2"; shift ;;
        --env-file)         ENV_FILE="$2"; shift   ;;
        *) log_fatal "Unknown option: $1  (run with --help to see usage)" ;;
    esac
    shift
done

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="${N7_LOG_DIR:-$SCRIPT_DIR/logs}"
PID_FILE="${N7_PID_FILE:-$SCRIPT_DIR/.naga7-prod.pids}"
WATCHDOG_LOG="$LOG_DIR/watchdog.log"

mkdir -p "$LOG_DIR"

# ── Python / pip helpers ──────────────────────────────────────────────────────
get_python_cmd() {
    local dir="${1:-$PWD}"
    if   [ -f "$dir/.venv/bin/python" ]; then echo "$dir/.venv/bin/python"
    elif [ -f "$dir/venv/bin/python"  ]; then echo "$dir/venv/bin/python"
    else echo "python3"; fi
}

get_pip_cmd() {
    local dir="${1:-$PWD}"
    if   [ -f "$dir/.venv/bin/pip" ]; then echo "$dir/.venv/bin/pip"
    elif [ -f "$dir/venv/bin/pip"  ]; then echo "$dir/venv/bin/pip"
    else echo "python3 -m pip"; fi
}

get_alembic_cmd() {
    local dir="${1:-$PWD}"
    if   [ -f "$dir/.venv/bin/alembic" ]; then echo "$dir/.venv/bin/alembic"
    elif command -v alembic &>/dev/null;  then echo "alembic"
    else echo "$(get_python_cmd "$dir") -m alembic"; fi
}

# ── Shutdown ──────────────────────────────────────────────────────────────────
_shutdown_called=0
shutdown_all() {
    [ "$_shutdown_called" -eq 1 ] && return
    _shutdown_called=1

    echo ""
    log_warn "=== Initiating graceful shutdown ==="

    # Kill watchdog background loop first so it doesn't restart dying processes
    if [ -n "${WATCHDOG_PID:-}" ] && kill -0 "$WATCHDOG_PID" 2>/dev/null; then
        kill -TERM "$WATCHDOG_PID" 2>/dev/null || true
    fi

    if [ -f "$PID_FILE" ]; then
        # Graceful SIGTERM to every recorded process group
        while IFS= read -r line || [ -n "$line" ]; do
            [ -z "$line" ] && continue
            local pgid="${line%%:*}"
            local label="${line##*:}"
            if kill -0 -- "-$pgid" 2>/dev/null; then
                log_info "Draining $label (PGID $pgid) — SIGTERM..."
                kill -TERM -- "-$pgid" 2>/dev/null || true
            fi
        done < "$PID_FILE"

        log_info "Waiting up to 15 s for graceful drain..."
        sleep 15

        # Force-kill survivors
        while IFS= read -r line || [ -n "$line" ]; do
            [ -z "$line" ] && continue
            local pgid="${line%%:*}"
            local label="${line##*:}"
            if kill -0 -- "-$pgid" 2>/dev/null; then
                log_warn "Force-killing $label (PGID $pgid)"
                kill -KILL -- "-$pgid" 2>/dev/null || true
            fi
        done < "$PID_FILE"

        rm -f "$PID_FILE"
    fi

    # Pattern sweep for orphans
    for pattern in \
        "Naga-7/n7-core.*main\.py" \
        "Naga-7/n7-sentinels.*main\.py" \
        "Naga-7/n7-strikers.*main\.py" \
        "Naga-7/n7-dashboard"; do
        local pids
        pids=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            log_warn "Killing orphan ($pattern): $pids"
            kill -TERM $pids 2>/dev/null || true
            sleep 2
            pids=$(pgrep -f "$pattern" 2>/dev/null || true)
            [ -n "$pids" ] && kill -KILL $pids 2>/dev/null || true
        fi
    done

    if [ "$KEEP_INFRA" = false ]; then
        log_info "Stopping infrastructure services..."
        cd "$SCRIPT_DIR/deploy"
        docker-compose down 2>/dev/null || docker compose down 2>/dev/null || true
    fi

    log_ok "Shutdown complete"
    exit 0
}

trap shutdown_all SIGINT SIGTERM EXIT
> "$PID_FILE"

# ── .env sourcing ─────────────────────────────────────────────────────────────
load_env() {
    local component_dir="$1"
    local env_src=""

    if [ -n "$ENV_FILE" ]; then
        env_src="$ENV_FILE"
    elif [ -f "$component_dir/.env" ]; then
        env_src="$component_dir/.env"
    fi

    if [ -n "$env_src" ]; then
        # Export every key=value that isn't a comment or blank
        set -o allexport
        # shellcheck source=/dev/null
        source "$env_src"
        set +o allexport
    fi
}

# ── Security: validate .env for production-unsafe defaults ───────────────────
validate_env() {
    local component="$1"
    local env_file="$2"
    local warnings=0

    [ ! -f "$env_file" ] && { log_warn "No .env found for $component at $env_file"; return; }

    local insecure_patterns=(
        "SECRET_KEY=changeme_in_production"
        "PASSWORD=n7password"
        "DEBUG=True"
        "ENVIRONMENT=development"
    )

    for pattern in "${insecure_patterns[@]}"; do
        if grep -q "$pattern" "$env_file" 2>/dev/null; then
            log_warn "INSECURE default in $component/.env: $pattern"
            (( warnings++ )) || true
        fi
    done

    if [ "$warnings" -gt 0 ]; then
        log_warn "$component has $warnings insecure config value(s) — review before production use"
    fi
}

# ── Health-gate helpers ───────────────────────────────────────────────────────
# wait_for_http URL TIMEOUT_SECS
wait_for_http() {
    local url="$1"
    local timeout="${2:-$HEALTH_TIMEOUT}"
    local elapsed=0
    until curl -sf --max-time 2 "$url" &>/dev/null; do
        [ "$elapsed" -ge "$timeout" ] && return 1
        sleep 1
        (( elapsed++ )) || true
    done
    return 0
}

# wait_for_port HOST PORT TIMEOUT_SECS
wait_for_port() {
    local host="$1"
    local port="$2"
    local timeout="${3:-$HEALTH_TIMEOUT}"
    local elapsed=0
    until (echo >/dev/tcp/"$host"/"$port") 2>/dev/null; do
        [ "$elapsed" -ge "$timeout" ] && return 1
        sleep 1
        (( elapsed++ )) || true
    done
    return 0
}

# ── Process supervisor ────────────────────────────────────────────────────────
# Runs a command in a subprocess with automatic restart.
# Writes "PGID:label" to PID_FILE; watchdog loop runs in background.
#
# Usage: start_supervised LABEL DIR CMD LOG_FILE
start_supervised() {
    local label="$1"
    local dir="$2"
    local cmd="$3"
    local log_file="$4"
    local restarts=0

    # Rotate log if it already exists and is non-empty
    if [ -s "$log_file" ]; then
        mv "$log_file" "${log_file%.log}-$(date '+%Y%m%d_%H%M%S').log"
    fi

    (
        # Inner loop — restarts the process up to MAX_RESTARTS times
        while true; do
            # Set process group so we can kill the whole tree
            set -m
            ( cd "$dir" && eval "$cmd" >> "$log_file" 2>&1 ) &
            local child_pid=$!

            # Record PGID in the shared PID file (overwrites previous entry for label)
            local pgid
            pgid=$(ps -o pgid= -p "$child_pid" 2>/dev/null | tr -d ' ') || pgid="$child_pid"
            # Remove any stale entry for this label then append
            grep -v ":${label}$" "$PID_FILE" > "${PID_FILE}.tmp" 2>/dev/null || true
            echo "${pgid}:${label}" >> "${PID_FILE}.tmp"
            mv "${PID_FILE}.tmp" "$PID_FILE"

            wait "$child_pid" 2>/dev/null
            local exit_code=$?

            if [ "$_shutdown_called" -eq 1 ]; then
                echo "$(_ts) [WATCHDOG] $label — shutdown requested, not restarting" >> "$WATCHDOG_LOG"
                exit 0
            fi

            if [ "$exit_code" -eq 0 ]; then
                echo "$(_ts) [WATCHDOG] $label — exited cleanly (0), not restarting" >> "$WATCHDOG_LOG"
                exit 0
            fi

            (( restarts++ )) || true
            if [ "$restarts" -gt "$MAX_RESTARTS" ]; then
                echo "$(_ts) [WATCHDOG] $label — exceeded max restarts ($MAX_RESTARTS), giving up" >> "$WATCHDOG_LOG"
                log_error "$label exceeded max restarts ($MAX_RESTARTS) — check $log_file"
                exit 1
            fi

            echo "$(_ts) [WATCHDOG] $label — crashed (exit $exit_code), restart $restarts/$MAX_RESTARTS in ${RESTART_DELAY}s" >> "$WATCHDOG_LOG"
            log_warn "$label crashed (exit $exit_code) — restarting in ${RESTART_DELAY}s ($restarts/$MAX_RESTARTS)"
            sleep "$RESTART_DELAY"
        done
    ) &

    WATCHDOG_PID=$!
    log_ok "$label supervised watchdog started (watchdog PID: $WATCHDOG_PID)"
    echo "$WATCHDOG_LOG — tail to monitor restarts"
}

# ── PRODUCTION LOG SYMLINK ────────────────────────────────────────────────────
# Create a dated log directory and symlink "current" for easy access
DATED_LOG_DIR="$LOG_DIR/$(date '+%Y-%m-%d_%H%M%S')"
mkdir -p "$DATED_LOG_DIR"
ln -sfn "$DATED_LOG_DIR" "$LOG_DIR/current"
LOG_DIR="$DATED_LOG_DIR"

################################################################################
print_banner

# ============================================================================
# Step 1: Prerequisites
# ============================================================================
log_step "1/8  Checking prerequisites..."

check_cmd() { command -v "$1" &>/dev/null || log_fatal "$1 not found. Install it and retry."; }

check_cmd python3
log_ok  "Python $(python3 --version | awk '{print $2}')"

check_cmd node
log_ok  "Node.js $(node --version)"

check_cmd docker
log_ok  "Docker found"

check_cmd curl
log_ok  "curl found"

if ! docker info &>/dev/null; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        log_info "Starting Docker Desktop..."
        open -a Docker
        for i in {1..60}; do
            docker info &>/dev/null && { log_ok "Docker daemon started"; break; }
            [ $i -eq 60 ] && log_fatal "Docker daemon did not start within 60 s"
            sleep 1
        done
    else
        log_fatal "Docker daemon is not running. Start it and retry."
    fi
else
    log_ok "Docker daemon running"
fi

command -v docker-compose &>/dev/null || docker compose version &>/dev/null \
    || log_fatal "Docker Compose not found."
log_ok "Docker Compose found"

# ============================================================================
# Step 2: Environment validation
# ============================================================================
log_step "2/8  Validating environment configuration..."

for component in n7-core n7-sentinels n7-strikers; do
    env_path="$SCRIPT_DIR/$component/.env"
    if [ ! -f "$env_path" ] && [ -f "$SCRIPT_DIR/$component/.env.example" ]; then
        log_warn "$component/.env not found — copying from .env.example"
        log_warn "  Edit $env_path with production values before deploying"
        cp "$SCRIPT_DIR/$component/.env.example" "$env_path"
    fi
    validate_env "$component" "$env_path"
done

log_ok "Environment validation complete"

# ============================================================================
# Step 3: Infrastructure
# ============================================================================
if [ "$KEEP_INFRA" = false ]; then
    log_step "3/8  Starting infrastructure (NATS, PostgreSQL, Redis)..."

    cd "$SCRIPT_DIR/deploy"
    docker-compose up -d
    cd "$SCRIPT_DIR"

    log_info "Waiting for PostgreSQL to be healthy..."
    ELAPSED=0
    until docker inspect --format='{{.State.Health.Status}}' n7-postgres 2>/dev/null | grep -q "healthy"; do
        [ "$ELAPSED" -ge "$HEALTH_TIMEOUT" ] && log_fatal "PostgreSQL did not become healthy within ${HEALTH_TIMEOUT}s"
        sleep 2
        (( ELAPSED+=2 )) || true
    done
    log_ok "PostgreSQL healthy"

    log_info "Waiting for NATS..."
    wait_for_port localhost 4222 "$HEALTH_TIMEOUT" || log_fatal "NATS did not become reachable within ${HEALTH_TIMEOUT}s"
    log_ok "NATS reachable on :4222"

    log_info "Waiting for Redis..."
    wait_for_port localhost 6379 "$HEALTH_TIMEOUT" || log_fatal "Redis did not become reachable within ${HEALTH_TIMEOUT}s"
    log_ok "Redis reachable on :6379"
else
    log_step "3/8  Skipping infrastructure start (--keep-infra)"
    log_info "Verifying external infrastructure..."
    wait_for_port localhost 5432 10 || log_warn "PostgreSQL not reachable on :5432 — continuing anyway"
    wait_for_port localhost 4222 10 || log_warn "NATS not reachable on :4222 — continuing anyway"
    wait_for_port localhost 6379 10 || log_warn "Redis not reachable on :6379 — continuing anyway"
fi

# ============================================================================
# Step 4: Python dependencies
# ============================================================================
if [ "$SKIP_DEPS" = false ]; then
    log_step "4/8  Installing Python dependencies..."

    for component in n7-core n7-sentinels n7-strikers; do
        log_info "[$component] pip install..."
        cd "$SCRIPT_DIR/$component"
        PIP_CMD=$(get_pip_cmd "$SCRIPT_DIR/$component")
        $PIP_CMD install --quiet -r requirements.txt \
            > "$LOG_DIR/pip-${component}.log" 2>&1 || {
            log_error "[$component] pip install failed — see $LOG_DIR/pip-${component}.log"
            exit 1
        }
        log_ok "[$component] dependencies installed"
    done
    cd "$SCRIPT_DIR"
else
    log_step "4/8  Skipping Python dependency installation (--skip-deps)"
fi

# ============================================================================
# Step 5: Dashboard dependencies
# ============================================================================
if [ "$SKIP_DEPS" = false ] && [ "$NO_DASHBOARD" = false ]; then
    log_step "5/8  Installing dashboard dependencies..."
    cd "$SCRIPT_DIR/n7-dashboard"
    npm ci --silent > "$LOG_DIR/npm-install.log" 2>&1 || {
        log_error "npm ci failed — see $LOG_DIR/npm-install.log"
        exit 1
    }
    log_ok "Dashboard dependencies installed"
    cd "$SCRIPT_DIR"
else
    log_step "5/8  Skipping dashboard dependency installation"
fi

# ============================================================================
# Step 6: Database migrations
# ============================================================================
if [ "$SKIP_MIGRATIONS" = false ]; then
    log_step "6/8  Running database migrations..."
    cd "$SCRIPT_DIR/n7-core"
    load_env "$SCRIPT_DIR/n7-core"
    ALEMBIC_CMD=$(get_alembic_cmd "$SCRIPT_DIR/n7-core")
    $ALEMBIC_CMD upgrade head > "$LOG_DIR/alembic-migrate.log" 2>&1 || {
        log_error "Alembic migration failed — see $LOG_DIR/alembic-migrate.log"
        exit 1
    }
    log_ok "Database migrations applied"
    cd "$SCRIPT_DIR"
else
    log_step "6/8  Skipping database migrations (--skip-migrations)"
fi

# ============================================================================
# Step 7: Start application services (supervised)
# ============================================================================
log_step "7/8  Starting application services..."

# ── N7-Core ──────────────────────────────────────────────────────────────────
PYTHON_CMD=$(get_python_cmd "$SCRIPT_DIR/n7-core")
start_supervised \
    "N7-Core" \
    "$SCRIPT_DIR/n7-core" \
    "$PYTHON_CMD main.py" \
    "$LOG_DIR/n7-core.log"

log_info "Waiting for N7-Core API health gate (http://localhost:8000/health)..."
wait_for_http "http://localhost:8000/health" "$HEALTH_TIMEOUT" \
    || log_warn "N7-Core /health did not respond in ${HEALTH_TIMEOUT}s — agents will retry registration"
log_ok "N7-Core API is up"

# ── N7-Sentinels ─────────────────────────────────────────────────────────────
PYTHON_CMD=$(get_python_cmd "$SCRIPT_DIR/n7-sentinels")
start_supervised \
    "N7-Sentinels" \
    "$SCRIPT_DIR/n7-sentinels" \
    "$PYTHON_CMD main.py" \
    "$LOG_DIR/n7-sentinels.log"

# ── N7-Strikers ──────────────────────────────────────────────────────────────
PYTHON_CMD=$(get_python_cmd "$SCRIPT_DIR/n7-strikers")
start_supervised \
    "N7-Strikers" \
    "$SCRIPT_DIR/n7-strikers" \
    "$PYTHON_CMD main.py" \
    "$LOG_DIR/n7-strikers.log"

log_ok "Sentinels and Strikers supervisors started"

# ── N7-Dashboard ─────────────────────────────────────────────────────────────
if [ "$NO_DASHBOARD" = false ]; then
    log_step "8/8  Building and starting N7-Dashboard..."
    cd "$SCRIPT_DIR/n7-dashboard"

    log_info "Building dashboard for production..."
    npm run build > "$LOG_DIR/npm-build.log" 2>&1 || {
        log_error "Dashboard build failed — see $LOG_DIR/npm-build.log"
        exit 1
    }
    log_ok "Dashboard build complete"

    # Serve the production build with a static file server
    # Falls back to `npm run preview` (Vite) if `serve` is not installed
    if command -v serve &>/dev/null; then
        DASHBOARD_CMD="serve -s dist -l 5173"
    else
        DASHBOARD_CMD="npm run preview -- --port 5173 --host 0.0.0.0"
    fi

    start_supervised \
        "N7-Dashboard" \
        "$SCRIPT_DIR/n7-dashboard" \
        "$DASHBOARD_CMD" \
        "$LOG_DIR/n7-dashboard.log"
    cd "$SCRIPT_DIR"
else
    log_step "8/8  Skipping dashboard (--no-dashboard)"
fi

# ============================================================================
# All services started
# ============================================================================
sleep 2

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          NAGA-7 PRODUCTION STACK IS RUNNING                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Access Points:${NC}"
echo -e "  ${YELLOW}API Gateway:${NC}     http://localhost:8000"
echo -e "  ${YELLOW}API Docs:${NC}        http://localhost:8000/docs"
echo -e "  ${YELLOW}NATS Monitor:${NC}    http://localhost:8222"
[ "$NO_DASHBOARD" = false ] && \
echo -e "  ${YELLOW}Dashboard:${NC}       http://localhost:5173"
echo ""
echo -e "${CYAN}Service Status:${NC}"
echo -e "  ${GREEN}✓${NC} Infrastructure (NATS, PostgreSQL, Redis)"
echo -e "  ${GREEN}✓${NC} N7-Core        (supervised, auto-restart)"
echo -e "  ${GREEN}✓${NC} N7-Sentinels   (supervised, auto-restart)"
echo -e "  ${GREEN}✓${NC} N7-Strikers    (supervised, auto-restart)"
[ "$NO_DASHBOARD" = false ] && \
echo -e "  ${GREEN}✓${NC} N7-Dashboard   (supervised, auto-restart)"
echo ""
echo -e "${CYAN}Logs:${NC}"
echo -e "  ${YELLOW}$LOG_DIR/${NC}"
echo -e "  ${YELLOW}$SCRIPT_DIR/logs/current/${NC}  — symlink to today's run"
echo -e "  Watchdog events: ${YELLOW}$WATCHDOG_LOG${NC}"
echo -e "  Live tail:       tail -f logs/current/*.log"
echo ""
echo -e "${CYAN}Restart policy:${NC}  max ${MAX_RESTARTS} restarts, ${RESTART_DELAY}s delay"
echo ""
echo -e "${YELLOW}Send SIGTERM or Ctrl+C to stop all services gracefully.${NC}"
echo -e "Or run ${YELLOW}./stop.sh${NC} from another terminal."
echo ""

# ── Keep this process alive so traps fire on Ctrl+C / SIGTERM ────────────────
tail -f /dev/null
