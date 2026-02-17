import logging
import subprocess
import shutil

logger = logging.getLogger("n7-striker.actions.network_block")

class NetworkBlockAction:
    def __init__(self):
        self.action_type = "network_block"
        self._iptables = shutil.which("iptables")

    async def execute(self, params: dict) -> dict:
        """
        Blocks an IP using iptables.
        params: {"target": str, "duration": int}
        """
        target = params.get("target")
        if not target:
            return {"status": "failed", "reason": "No target specified"}
        
        logger.info(f"Executing network_block on {target}")
        
        if not self._iptables:
             logger.warning("iptables not found, simulating action")
             return {"status": "succeeded", "simulated": True}

        try:
            # Check if already blocked
            check_cmd = [self._iptables, "-C", "INPUT", "-s", target, "-j", "DROP"]
            ret = subprocess.call(check_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ret == 0:
                 return {"status": "succeeded", "reason": "Already blocked"}

            # Block
            cmd = [self._iptables, "-A", "INPUT", "-s", target, "-j", "DROP"]
            subprocess.check_call(cmd)
            logger.info(f"Blocked {target} via iptables")
            
            # Note: Unblocking is handled by a scheduler or rollback manager (not implemented in this atomic action)
            
            return {"status": "succeeded"}
        except Exception as e:
            logger.error(f"Failed to block {target}: {e}")
            return {"status": "failed", "reason": str(e)}
