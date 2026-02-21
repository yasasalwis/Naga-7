import asyncio
import json
import logging
import shlex
from typing import AsyncIterator, Dict, Any, List

logger = logging.getLogger("n7-sentinel.probes.osquery")

class OsqueryProbe:
    """
    Osquery Probe.
    Responsibility: Run periodic osquery SQL commands to find system anomalies.
    """

    def __init__(self):
        self.probe_type = "osquery_monitor"
        self._running = False
        
        # Periodic threat hunting queries
        self._queries = [
            # Find processes executing from deleted binaries
            ("processes_without_binary", "SELECT pid, name, path, cmdline FROM processes WHERE on_disk = 0 AND path != '';"),
            # Processes with unexpected outbound network connections (basic heuristic example)
            ("suspicious_outbound", "SELECT p.pid, p.name, p.cmdline, pos.remote_address, pos.remote_port FROM process_open_sockets pos JOIN processes p ON p.pid = pos.pid WHERE pos.remote_port NOT IN (80, 443) AND pos.remote_address NOT IN ('127.0.0.1', '0.0.0.0', '::1', '::') AND p.name IN ('sh', 'bash', 'nc', 'curl', 'wget');")
        ]

    async def initialize(self, config: dict) -> None:
        logger.info("Initializing OsqueryProbe...")
        # Check if osqueryi is installed and functional
        try:
            process = await asyncio.create_subprocess_exec(
                "osqueryi", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                logger.info(f"osquery found: {stdout.decode().strip()}")
            else:
                logger.warning("osqueryi command failed. Probe will not emit data.")
        except FileNotFoundError:
            logger.warning("osqueryi not found in PATH. Probe will not emit data.")


    async def observe(self) -> AsyncIterator[Dict[str, Any]]:
        self._running = True
        logger.info("OsqueryProbe started observing.")

        while self._running:
            for query_name, sql in self._queries:
                try:
                    # Run osqueryi with JSON output format
                    cmd_args = ["osqueryi", "--json", sql]
                    
                    process = await asyncio.create_subprocess_exec(
                        *cmd_args,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode == 0 and stdout:
                        results = json.loads(stdout.decode())
                        
                        # Yield one event per matched row
                        for row in results:
                            yield {
                                "event_class": "osquery_anomaly",
                                "severity": "high", # By definition, our queries look for anomalies
                                "raw_data": {
                                    "query_name": query_name,
                                    "sql": sql,
                                    "results": row
                                }
                            }
                    
                except FileNotFoundError:
                     # Handled in initialize, but catch here just in case path changes
                     pass
                except Exception as e:
                    logger.error(f"Error running osquery SQL: {e}")

            # Sleep extensively since these are heavy periodic hunts, not instant event streams
            await asyncio.sleep(60.0) 

    async def shutdown(self) -> None:
        self._running = False
        logger.info("OsqueryProbe shutdown.")
