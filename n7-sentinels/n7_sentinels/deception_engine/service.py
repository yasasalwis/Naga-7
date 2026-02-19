import asyncio
import json
import logging
import os
import stat
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..event_emitter.service import EventEmitterService
from ..config import settings

logger = logging.getLogger("n7-sentinel.deception-engine")

# Deception Subject — picked up by EventPipelineService via n7.events.> wildcard
DECEPTION_SUBJECT = "n7.events.sentinel.deception"

# Decoy file definitions: (filename, content_lines, description)
# IMPORTANT: All content is fake / clearly marked as HONEYTOKEN. No real credentials.
DECOY_FILES = [
    (
        "AWS_root_credentials.csv",
        (
            "User Name,Password,Access key ID,Secret access key,Console login link\n"
            "root,HONEYTOKEN_NOT_REAL,"
            "AKIAIOSFODNN7EXAMPLE_HONEYTOKEN,"
            "wJalrXUtnFEMI_HONEYTOKEN_bPxRfiCYEXAMPLEKEY,"
            "https://example-honeytoken.signin.aws.amazon.com/console\n"
        ),
        "AWS root credential honeytoken",
    ),
    (
        "Passwords.kdbx.txt",
        "KeePass Database — HONEYTOKEN — DO NOT USE\n[This file is a security trap]\n",
        "KeePass database honeytoken",
    ),
    (
        "id_rsa_backup",
        (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "HONEYTOKEN_NOT_A_REAL_PRIVATE_KEY_DO_NOT_USE\n"
            "-----END OPENSSH PRIVATE KEY-----\n"
        ),
        "SSH private key honeytoken",
    ),
    (
        ".env.production",
        (
            "# HONEYTOKEN — This file is a security trap\n"
            "DATABASE_URL=postgresql://honeytoken:honeytoken@honeytoken:5432/honeytoken\n"
            "SECRET_KEY=HONEYTOKEN_SECRET_KEY_NOT_REAL\n"
            "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE_HONEYTOKEN\n"
        ),
        "Production .env honeytoken",
    ),
    (
        "internal_api_keys.json",
        (
            '{"note": "HONEYTOKEN — security trap", '
            '"stripe_live_key": "sk_live_HONEYTOKEN_NOT_REAL", '
            '"sendgrid_api_key": "SG.HONEYTOKEN_NOT_REAL", '
            '"github_token": "ghp_HONEYTOKEN_NOT_REAL"}\n'
        ),
        "Internal API keys honeytoken",
    ),
]

# Set of decoy filenames for fast lookup
DECOY_FILENAMES = {filename for filename, _, _ in DECOY_FILES}
DECOY_DESCRIPTIONS = {filename: desc for filename, _, desc in DECOY_FILES}


class DeceptionEngineService:
    """
    Deception Engine Service.
    Responsibility: Place honeytoken decoy files on the host and monitor them for any access.
    Any filesystem event on a decoy file is a 100%-confidence, zero-false-positive alert.

    Ref: TDD Section 5.X Deception Engine, SRS FR-S010
    """

    def __init__(self, event_emitter: EventEmitterService):
        self._running = False
        self._event_emitter = event_emitter
        self._decoy_dir: str = getattr(settings, "DECEPTION_DECOY_DIR", "/tmp/n7_decoys")
        self._enabled: bool = getattr(settings, "DECEPTION_ENABLED", True)
        self._decoy_paths: List[Path] = []
        self._monitor_task: Optional[asyncio.Task] = None
        self._observer = None
        self._queue: asyncio.Queue = asyncio.Queue()

    async def start(self):
        if not self._enabled:
            logger.info("DeceptionEngineService disabled via config.")
            return

        self._running = True
        logger.info("DeceptionEngineService starting...")

        decoy_dir = Path(self._decoy_dir)
        decoy_dir.mkdir(parents=True, exist_ok=True)

        self._decoy_paths = []
        for filename, content, description in DECOY_FILES:
            path = decoy_dir / filename
            await self._create_decoy_file(path, content, description)
            self._decoy_paths.append(path)

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(
            f"DeceptionEngineService started. Monitoring {len(self._decoy_paths)} "
            f"honeytoken file(s) in '{self._decoy_dir}'"
        )

    async def stop(self):
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        if self._observer:
            self._observer.stop()
            self._observer.join()
        logger.info("DeceptionEngineService stopped.")

    async def _create_decoy_file(self, path: Path, content: str, description: str):
        """Write a decoy file with read-only world permissions (644)."""
        try:
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                # Owner rw, group r, world r — legitimate users won't browse /tmp/n7_decoys/
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                logger.info(f"Created decoy file: {path} ({description})")
            else:
                logger.debug(f"Decoy file already exists (skipping create): {path}")
        except Exception as e:
            logger.error(f"Failed to create decoy file {path}: {e}")

    async def _monitor_loop(self):
        """
        Start a watchdog Observer on the decoy directory and process filesystem events
        asynchronously. Only events on known decoy filenames trigger alerts.
        """
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            logger.error("watchdog not installed — DeceptionEngineService cannot monitor files.")
            return

        loop = asyncio.get_running_loop()
        decoy_filenames = DECOY_FILENAMES  # captured for closure

        class _DeceptionHandler(FileSystemEventHandler):
            def __init__(self, queue: asyncio.Queue, _loop):
                self._q = queue
                self._loop = _loop

            def on_any_event(self, event):
                if event.is_directory:
                    return
                fname = Path(event.src_path).name
                if fname in decoy_filenames:
                    asyncio.run_coroutine_threadsafe(
                        self._q.put({
                            "event_type": event.event_type,
                            "src_path": event.src_path,
                        }),
                        self._loop,
                    )

        handler = _DeceptionHandler(self._queue, loop)
        self._observer = Observer()
        self._observer.schedule(handler, self._decoy_dir, recursive=False)
        self._observer.start()

        try:
            while self._running:
                try:
                    fs_event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                    await self._emit_honeytoken_alert(fs_event)
                except asyncio.TimeoutError:
                    continue
        finally:
            self._observer.stop()
            self._observer.join()

    async def _emit_honeytoken_alert(self, fs_event: dict):
        """
        Emit a maximum-confidence alert for a honeytoken access event.
        Published directly to n7.events.sentinel.deception (caught by Core's wildcard sub).
        """
        src_path = fs_event.get("src_path", "unknown")
        event_type = fs_event.get("event_type", "unknown")
        fname = Path(src_path).name
        description = DECOY_DESCRIPTIONS.get(fname, "Honeytoken file accessed")

        event_data = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "sentinel_id": getattr(settings, "AGENT_ID", "sentinel-1"),
            "event_class": "honeytoken_access",
            "severity": "critical",
            "raw_data": {
                "event_type": event_type,
                "src_path": src_path,
                "filename": fname,
                "description": description,
                "threat_score": 100,
                "deception_triggered": True,
                "ioc_matched": False,
            },
        }

        payload = json.dumps(event_data).encode()

        # Publish directly to deception-specific subject if NATS is up;
        # fall back to EventEmitterService buffering otherwise.
        try:
            if self._event_emitter.nc.is_connected:
                await self._event_emitter.nc.publish(DECEPTION_SUBJECT, payload)
                logger.warning(
                    f"HONEYTOKEN ALERT: {description} — "
                    f"file='{fname}', event='{event_type}'"
                )
            else:
                # Buffer via EventEmitterService (will flush when reconnected)
                await self._event_emitter.emit(event_data)
                logger.warning(
                    f"HONEYTOKEN ALERT (buffered, NATS down): {description} — "
                    f"file='{fname}', event='{event_type}'"
                )
        except Exception as e:
            logger.error(f"Failed to emit honeytoken alert: {e}", exc_info=True)
