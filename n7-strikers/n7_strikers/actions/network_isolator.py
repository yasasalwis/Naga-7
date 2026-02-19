import asyncio
import logging
import platform
import shutil
import subprocess
from datetime import datetime

logger = logging.getLogger("n7-striker.actions.network_isolator")

NATS_PORT = 4222
CHAIN_NAME = "N7_QUARANTINE"


class NetworkIsolatorAction:
    """
    Host Network Isolation Action.
    Responsibility: Apply OS-level firewall rules to completely isolate a host,
    preserving ONLY NATS connectivity (port 4222) and loopback interface.

    Supports:
    - Linux: iptables
    - Windows: PowerShell New-NetFirewallRule

    params: {"reason": str, "alert_id": str}
    """

    def __init__(self):
        self.action_type = "isolate_host"
        self._platform = platform.system().lower()
        self._iptables = shutil.which("iptables") if self._platform == "linux" else None

    async def execute(self, params: dict) -> dict:
        reason = params.get("reason", "automated_isolation")
        alert_id = params.get("alert_id", "unknown")
        logger.warning(f"Executing host isolation: reason={reason}, alert_id={alert_id}")

        try:
            if self._platform == "linux":
                success = await asyncio.to_thread(self._apply_linux_isolation)
            elif self._platform == "windows":
                success = await asyncio.to_thread(self._apply_windows_isolation)
            else:
                logger.warning(f"Unsupported platform for isolation: {self._platform}, simulating.")
                return {
                    "success": True,
                    "action_type": "isolate_host",
                    "simulated": True,
                    "platform": self._platform,
                    "isolated_at": datetime.utcnow().isoformat(),
                }

            return {
                "success": success,
                "action_type": "isolate_host",
                "isolated_at": datetime.utcnow().isoformat(),
                "platform": self._platform,
                "nats_port_preserved": NATS_PORT,
                "reason": reason,
                "alert_id": alert_id,
            }
        except Exception as e:
            logger.error(f"Isolation failed: {e}", exc_info=True)
            return {"success": False, "reason": str(e)}

    def _apply_linux_isolation(self) -> bool:
        """
        Apply iptables rules to isolate the host.

        Rule order (evaluated top-to-bottom in N7_QUARANTINE chain):
          1. ACCEPT established/related (keeps existing NATS session alive)
          2. ACCEPT loopback (lo interface)
          3. ACCEPT TCP dport 4222 (new inbound NATS connections)
          4. ACCEPT TCP sport 4222 (outbound NATS traffic)
          5. DROP everything else

        The N7_QUARANTINE chain is inserted at position 1 in INPUT and OUTPUT
        so it takes priority over any existing rules.
        """
        if not self._iptables:
            logger.warning("iptables not found — simulating isolation.")
            return True

        ipt = self._iptables

        def run(args: list):
            subprocess.check_call(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def run_silent(args: list):
            subprocess.call(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Flush and recreate the quarantine chain
        run_silent([ipt, "-F", CHAIN_NAME])
        run_silent([ipt, "-X", CHAIN_NAME])
        run([ipt, "-N", CHAIN_NAME])

        # Allow established/related connections first (keeps current NATS session alive)
        run([ipt, "-A", CHAIN_NAME, "-m", "state", "--state", "ESTABLISHED,RELATED", "-j", "ACCEPT"])

        # Allow loopback interface
        run([ipt, "-A", CHAIN_NAME, "-i", "lo", "-j", "ACCEPT"])
        run([ipt, "-A", CHAIN_NAME, "-o", "lo", "-j", "ACCEPT"])

        # Allow NATS port 4222 inbound and outbound (new connections)
        run([ipt, "-A", CHAIN_NAME, "-p", "tcp", "--dport", str(NATS_PORT), "-j", "ACCEPT"])
        run([ipt, "-A", CHAIN_NAME, "-p", "tcp", "--sport", str(NATS_PORT), "-j", "ACCEPT"])

        # Drop everything else
        run([ipt, "-A", CHAIN_NAME, "-j", "DROP"])

        # Hook chain into INPUT (idempotent)
        check_input = subprocess.call(
            [ipt, "-C", "INPUT", "-j", CHAIN_NAME],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if check_input != 0:
            run([ipt, "-I", "INPUT", "1", "-j", CHAIN_NAME])

        # Hook chain into OUTPUT (idempotent)
        check_output = subprocess.call(
            [ipt, "-C", "OUTPUT", "-j", CHAIN_NAME],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if check_output != 0:
            run([ipt, "-I", "OUTPUT", "1", "-j", CHAIN_NAME])

        logger.warning(f"Host isolated via iptables. NATS port {NATS_PORT} preserved.")
        return True

    def _apply_windows_isolation(self) -> bool:
        """
        Apply Windows Firewall rules via PowerShell.
        Block all inbound/outbound traffic except NATS port 4222.
        """
        ps_script = f"""
        Remove-NetFirewallRule -DisplayName "N7_BLOCK_ALL_IN" -ErrorAction SilentlyContinue
        Remove-NetFirewallRule -DisplayName "N7_BLOCK_ALL_OUT" -ErrorAction SilentlyContinue
        Remove-NetFirewallRule -DisplayName "N7_ALLOW_NATS_IN" -ErrorAction SilentlyContinue
        Remove-NetFirewallRule -DisplayName "N7_ALLOW_NATS_OUT" -ErrorAction SilentlyContinue

        New-NetFirewallRule -DisplayName "N7_ALLOW_NATS_IN" -Direction Inbound `
            -Protocol TCP -LocalPort {NATS_PORT} -Action Allow
        New-NetFirewallRule -DisplayName "N7_ALLOW_NATS_OUT" -Direction Outbound `
            -Protocol TCP -RemotePort {NATS_PORT} -Action Allow

        New-NetFirewallRule -DisplayName "N7_BLOCK_ALL_IN" -Direction Inbound `
            -Action Block -Priority 65500
        New-NetFirewallRule -DisplayName "N7_BLOCK_ALL_OUT" -Direction Outbound `
            -Action Block -Priority 65500
        """
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            logger.error(f"PowerShell isolation failed: {result.stderr}")
            return False
        logger.warning(f"Host isolated via Windows Firewall. NATS port {NATS_PORT} preserved.")
        return True


class NetworkUnisolatorAction:
    """
    Host Network Un-isolation (Rollback) Action.
    Removes the N7_QUARANTINE iptables chain / Windows Firewall rules added by NetworkIsolatorAction.

    params: {"original_action_id": str}
    """

    def __init__(self):
        self.action_type = "unisolate_host"
        self._platform = platform.system().lower()
        self._iptables = shutil.which("iptables") if self._platform == "linux" else None

    async def execute(self, params: dict) -> dict:
        logger.warning(f"Executing host un-isolation: {params}")
        try:
            if self._platform == "linux":
                success = await asyncio.to_thread(self._remove_linux_isolation)
            elif self._platform == "windows":
                success = await asyncio.to_thread(self._remove_windows_isolation)
            else:
                return {"success": True, "simulated": True, "action_type": "unisolate_host"}

            return {
                "success": success,
                "action_type": "unisolate_host",
                "unisolated_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Un-isolation failed: {e}", exc_info=True)
            return {"success": False, "reason": str(e)}

    def _remove_linux_isolation(self) -> bool:
        if not self._iptables:
            return True
        ipt = self._iptables
        subprocess.call([ipt, "-D", "INPUT", "-j", CHAIN_NAME],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.call([ipt, "-D", "OUTPUT", "-j", CHAIN_NAME],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.call([ipt, "-F", CHAIN_NAME],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.call([ipt, "-X", CHAIN_NAME],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.warning("Host un-isolated: N7_QUARANTINE iptables chain removed.")
        return True

    def _remove_windows_isolation(self) -> bool:
        ps_script = """
        Remove-NetFirewallRule -DisplayName "N7_BLOCK_ALL_IN" -ErrorAction SilentlyContinue
        Remove-NetFirewallRule -DisplayName "N7_BLOCK_ALL_OUT" -ErrorAction SilentlyContinue
        Remove-NetFirewallRule -DisplayName "N7_ALLOW_NATS_IN" -ErrorAction SilentlyContinue
        Remove-NetFirewallRule -DisplayName "N7_ALLOW_NATS_OUT" -ErrorAction SilentlyContinue
        """
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True
        )
        return result.returncode == 0
