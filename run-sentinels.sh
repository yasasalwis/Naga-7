#!/bin/bash
################################################################################
# N7-Sentinels Launcher
# Called by start.sh to run the Sentinels agent in its own terminal window.
# Environment variables passed in by start.sh:
#   N7_ROOT      — absolute path to the Naga-7 project root
#   LOG_LEVEL    — INFO or DEBUG
#   N7_PID_OUT   — path to a file where this script writes its PID
################################################################################

# Set terminal window title
printf '\033]0;N7-Sentinels\007'

# Write PID so start.sh can track and kill this process
[ -n "$N7_PID_OUT" ] && echo $$ > "$N7_PID_OUT"

SCRIPT_DIR="${N7_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Resolve python
if   [ -f "$SCRIPT_DIR/n7-sentinels/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/n7-sentinels/.venv/bin/python"
elif [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
else
    PYTHON="python3"
fi

cd "$SCRIPT_DIR/n7-sentinels"
LOG_LEVEL="${LOG_LEVEL:-INFO}" exec $PYTHON main.py 2>&1 | tee "$LOG_DIR/n7-sentinels.log"
