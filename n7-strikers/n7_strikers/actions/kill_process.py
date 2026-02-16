import logging
import psutil
import json

logger = logging.getLogger("n7-striker.actions.kill_process")

class KillProcessAction:
    def __init__(self):
        self.action_type = "kill_process"

    async def execute(self, params: dict) -> dict:
        """
        Kills a process by PID or Name.
        params: {"pid": int} or {"process_name": str}
        """
        pid = params.get("pid")
        process_name = params.get("process_name")
        
        logger.info(f"Executing kill_process: pid={pid}, name={process_name}")
        
        killed_count = 0
        
        if pid:
            try:
                p = psutil.Process(pid)
                p.kill()
                killed_count = 1
                logger.info(f"Killed process {pid}")
            except psutil.NoSuchProcess:
                logger.warning(f"Process {pid} not found")
                return {"status": "failed", "reason": "Process not found"}
            except Exception as e:
                logger.error(f"Failed to kill process {pid}: {e}")
                return {"status": "failed", "reason": str(e)}

        elif process_name:
            for p in psutil.process_iter(['pid', 'name']):
                if p.info['name'] == process_name:
                    try:
                        p.kill()
                        killed_count += 1
                        logger.info(f"Killed process {p.info['pid']} ({process_name})")
                    except Exception as e:
                        logger.error(f"Failed to kill {p.info['pid']}: {e}")
            
            if killed_count == 0:
                 return {"status": "failed", "reason": "No matching process found"}

        return {"status": "succeeded", "killed_count": killed_count}
