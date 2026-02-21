"""
Collects rich node metadata for N7 Sentinel registration and NATS publish.
Sends on every restart to Core via:
  - Registration payload (metadata field)
  - NATS topic: n7.node.metadata.{agent_id}

Uses only stdlib (platform, socket, sys, importlib.metadata) and psutil
(already a required dependency via probes/system.py).

Ref: SRS FR-S001, TDD Section 4.3 Agent Registry
"""
import logging
import platform
import socket
import sys

import psutil

logger = logging.getLogger("n7-sentinel.metadata-collector")


def collect_node_metadata() -> dict:
    """
    Collect hardware, OS, and network identity of this node.
    Returns a dict suitable for JSON serialisation.
    Gracefully returns partial data if any individual collection fails.
    """
    meta: dict = {}

    # CPU
    try:
        meta["cpu_model"] = platform.processor() or "unknown"
        meta["cpu_cores"] = psutil.cpu_count(logical=False) or psutil.cpu_count() or 0
    except Exception as e:
        logger.warning(f"CPU metadata collection failed: {e}")
        meta.setdefault("cpu_model", "unknown")
        meta.setdefault("cpu_cores", 0)

    # RAM
    try:
        meta["ram_total_mb"] = round(psutil.virtual_memory().total / (1024 * 1024))
    except Exception as e:
        logger.warning(f"RAM metadata collection failed: {e}")
        meta["ram_total_mb"] = 0

    # OS
    try:
        meta["os_name"] = platform.system()        # e.g. "Linux", "Darwin", "Windows"
        meta["os_version"] = platform.version()
        meta["kernel_version"] = platform.release()
    except Exception as e:
        logger.warning(f"OS metadata collection failed: {e}")
        meta.setdefault("os_name", "unknown")
        meta.setdefault("os_version", "unknown")
        meta.setdefault("kernel_version", "unknown")

    # Hostname (FQDN preferred)
    try:
        meta["hostname"] = socket.getfqdn()
    except Exception:
        meta["hostname"] = "localhost"

    # MAC address — first non-loopback NIC with a valid address
    try:
        mac = _get_primary_mac()
        meta["mac_address"] = mac
    except Exception as e:
        logger.warning(f"MAC metadata collection failed: {e}")
        meta["mac_address"] = "unknown"

    # Python version
    try:
        meta["python_version"] = sys.version.split()[0]
    except Exception:
        meta["python_version"] = "unknown"

    # Agent package version
    try:
        import importlib.metadata as _imeta
        meta["agent_version"] = _imeta.version("n7-sentinels")
    except Exception:
        meta["agent_version"] = "dev"

    return meta


def _get_primary_mac() -> str:
    """Return MAC address of the first non-loopback network interface."""
    # psutil.AF_LINK is available on most platforms; fall back to socket.AF_PACKET (Linux)
    af_link = getattr(psutil, "AF_LINK", None)
    if af_link is None:
        import socket as _socket
        af_link = getattr(_socket, "AF_PACKET", -1)

    for nic, addrs in psutil.net_if_addrs().items():
        # Skip loopback interfaces
        if nic in ("lo", "lo0") or nic.startswith("lo"):
            continue
        for addr in addrs:
            if addr.family == af_link:
                mac = addr.address.upper().replace("-", ":")
                if mac and mac != "00:00:00:00:00:00":
                    return mac

    # Fallback: derive from uuid.getnode() (uses hardware address)
    import uuid as _uuid
    raw = _uuid.getnode()
    return ":".join(f"{(raw >> (5 - i) * 8) & 0xFF:02X}" for i in range(6))
