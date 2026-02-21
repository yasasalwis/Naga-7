import logging
import sys
from datetime import datetime, timezone

from .config import settings

# ANSI escape codes
_RESET    = "\033[0m"
_BOLD     = "\033[1m"
_DIM      = "\033[2m"

# Level → color
_LEVEL_COLORS = {
    "DEBUG":    "\033[36m",    # Cyan
    "INFO":     "\033[32m",    # Green
    "WARNING":  "\033[33m",    # Yellow
    "ERROR":    "\033[31m",    # Red
    "CRITICAL": "\033[35;1m",  # Bright Magenta
}

# Component badge: bright red for Strikers (response/action agents)
_COMPONENT_COLOR = "\033[91m"
_COMPONENT_TAG   = "STRIKER"


class N7StrikerFormatter(logging.Formatter):
    """
    Human-readable colored formatter for N7-Strikers.

    Example output:
      [2026-02-21 14:05:33.421]  [STRIKER]  [INFO    ]  n7-striker.actions.kill_process  » Killed process pid=4821
      [2026-02-21 14:05:33.512]  [STRIKER]  [WARNING ]  n7-striker.agent-runtime         » Heartbeat 404: re-registering
      [2026-02-21 14:05:33.600]  [STRIKER]  [ERROR   ]  n7-striker.actions.network_block  » Failed to block IP
    """

    def format(self, record: logging.LogRecord) -> str:
        # --- Timestamp [YYYY-MM-DD HH:MM:SS.mmm] ---
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]  # trim microseconds → milliseconds
        ts_part = f"{_DIM}[{ts}]{_RESET}"

        # --- Component badge [STRIKER] ---
        badge = f"{_COMPONENT_COLOR}{_BOLD}[{_COMPONENT_TAG}]{_RESET}"

        # --- Level tag [INFO    ] padded to 8 chars inside brackets ---
        level      = record.levelname
        lcolor     = _LEVEL_COLORS.get(level, "")
        level_part = f"{lcolor}{_BOLD}[{level:<8}]{_RESET}"

        # --- Logger name (dimmed) ---
        name_part = f"{_DIM}{record.name}{_RESET}"

        # --- Message ---
        msg = record.getMessage()
        if record.exc_info:
            msg = msg + "\n" + self.formatException(record.exc_info)

        return f"{ts_part}  {badge}  {level_part}  {name_part}  » {msg}"


def setup_logging() -> logging.Logger:
    """
    Configure logging for N7-Strikers.

    Development  → colored, human-readable lines to stdout
    Production   → plain structured lines to stdout (no color codes)

    Log level is controlled by settings.LOG_LEVEL (default: INFO).
    """
    root = logging.getLogger()

    # Remove handlers added by imported libraries before us
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)

    if settings.ENVIRONMENT == "production":
        # Plain structured format for log aggregators (no ANSI codes)
        plain_fmt = logging.Formatter(
            fmt="[%(asctime)s]  [STRIKER]  [%(levelname)-8s]  %(name)s  » %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(plain_fmt)
    else:
        handler.setFormatter(N7StrikerFormatter())

    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)

    # Suppress chatty third-party loggers
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("nats").setLevel(logging.WARNING)

    return root


logger = setup_logging()
