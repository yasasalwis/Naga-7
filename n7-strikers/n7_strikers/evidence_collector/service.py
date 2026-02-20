import logging
import os
import time
from datetime import datetime

import psutil

logger = logging.getLogger("n7-striker.evidence-collector")

# Directories to scan for recent file activity
_WATCH_DIRS = ["/tmp", "/var/tmp", "/home", "/opt/n7"]
# Files modified within this window (seconds) are considered "recent"
_RECENT_FILE_WINDOW = 300


class EvidenceCollectorService:
    """
    Evidence Collector Service.
    Responsibility: Forensically capture host state immediately before and after
    each Striker action, providing pre/post snapshots for incident investigation.

    Captures:
    - Running process list (pid, name, cmdline, user, cpu%, mem%)
    - Active network connections (laddr, raddr, status, pid)
    - Recently modified files in key directories (last 5 minutes)
    - Point-in-time system metrics (cpu, memory, disk)

    Ref: TDD Section 6.1 Striker Process Model
    """

    def __init__(self):
        self._running = False

    async def start(self):
        self._running = True
        logger.info("EvidenceCollectorService started.")

    async def stop(self):
        self._running = False
        logger.info("EvidenceCollectorService stopped.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def collect_pre_action(self, action_id: str, action_type: str, params: dict) -> dict:
        """
        Capture forensic snapshot immediately BEFORE an action is executed.
        Returns a dict suitable for storing in Action.evidence['pre'].
        """
        snapshot = self._capture_snapshot(action_id=action_id, phase="pre")
        snapshot["action_type"] = action_type
        snapshot["action_params"] = params
        logger.info(
            f"Pre-action evidence captured for {action_id} ({action_type}): "
            f"{len(snapshot['processes'])} procs, {len(snapshot['network_connections'])} conns, "
            f"{len(snapshot['recent_files'])} recent files"
        )
        return snapshot

    async def collect_post_action(self, action_id: str, action_type: str, result: dict) -> dict:
        """
        Capture forensic snapshot immediately AFTER an action completes.
        Returns a dict suitable for storing in Action.evidence['post'].
        """
        snapshot = self._capture_snapshot(action_id=action_id, phase="post")
        snapshot["action_type"] = action_type
        snapshot["action_result"] = result
        logger.info(
            f"Post-action evidence captured for {action_id} ({action_type}): "
            f"{len(snapshot['processes'])} procs, {len(snapshot['network_connections'])} conns"
        )
        return snapshot

    # ------------------------------------------------------------------
    # Internal capture
    # ------------------------------------------------------------------

    def _capture_snapshot(self, action_id: str, phase: str) -> dict:
        return {
            "captured_at": datetime.utcnow().isoformat(),
            "action_id": action_id,
            "phase": phase,
            "processes": self._capture_processes(),
            "network_connections": self._capture_network_connections(),
            "recent_files": self._capture_recent_files(),
            "system_metrics": self._capture_system_metrics(),
        }

    def _capture_processes(self) -> list:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cmdline", "username", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                procs.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cmdline": " ".join(info["cmdline"] or [])[:512],
                    "username": info["username"],
                    "cpu_percent": round(info["cpu_percent"] or 0.0, 2),
                    "memory_percent": round(info["memory_percent"] or 0.0, 4),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return procs

    def _capture_network_connections(self) -> list:
        conns = []
        try:
            for c in psutil.net_connections(kind="inet"):
                try:
                    laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else None
                    raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else None
                    conns.append({
                        "fd": c.fd,
                        "family": c.family.name if hasattr(c.family, "name") else str(c.family),
                        "type": c.type.name if hasattr(c.type, "name") else str(c.type),
                        "laddr": laddr,
                        "raddr": raddr,
                        "status": c.status,
                        "pid": c.pid,
                    })
                except Exception:
                    continue
        except psutil.AccessDenied:
            logger.debug("Access denied listing network connections (non-root)")
        return conns

    def _capture_recent_files(self) -> list:
        cutoff = time.time() - _RECENT_FILE_WINDOW
        recent = []
        for watch_dir in _WATCH_DIRS:
            if not os.path.isdir(watch_dir):
                continue
            try:
                for root, _, files in os.walk(watch_dir, followlinks=False):
                    # Cap traversal depth to avoid very deep trees
                    depth = root[len(watch_dir):].count(os.sep)
                    if depth > 5:
                        continue
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        try:
                            stat = os.stat(fpath)
                            if stat.st_mtime >= cutoff:
                                recent.append({
                                    "path": fpath,
                                    "size_bytes": stat.st_size,
                                    "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                                })
                        except OSError:
                            continue
            except PermissionError:
                continue
        return recent[:200]  # cap to 200 entries to keep payload manageable

    def _capture_system_metrics(self) -> dict:
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return {
                "cpu_percent": round(cpu, 2),
                "memory_percent": round(mem.percent, 2),
                "memory_available_mb": round(mem.available / 1024 / 1024, 1),
                "disk_percent": round(disk.percent, 2),
                "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 2),
            }
        except Exception as e:
            logger.debug(f"Failed to capture system metrics: {e}")
            return {}
