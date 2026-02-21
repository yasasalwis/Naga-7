import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Must be imported first — installs the colored formatter before any other module logs
import n7_sentinels.logger  # noqa: F401

import asyncio
import logging
from typing import Dict, Any
from n7_sentinels.agent_runtime.service import AgentRuntimeService
from n7_sentinels.event_emitter.service import EventEmitterService
from n7_sentinels.detection_engine.service import DetectionEngineService
from n7_sentinels.deception_engine.service import DeceptionEngineService
from n7_sentinels.probes.system import SystemProbe
from n7_sentinels.config import settings

from n7_sentinels.utils import print_banner

logger = logging.getLogger("n7-sentinels")

async def main():
    """
    Main entry point for N7-Sentinels.
    Initializes and starts the sentinel agent.
    Ref: TDD Section 5.1 Sentinel Process Model
    """
    print_banner("N7-Sentinel")
    logger.info("Starting N7-Sentinel...")

    # Initialize Core Services
    agent_runtime = AgentRuntimeService()
    event_emitter = EventEmitterService()
    agent_runtime.set_event_emitter(event_emitter)  # Wire emitter for graph anomaly dispatch
    detection_engine = DetectionEngineService(event_emitter)
    deception_engine = DeceptionEngineService(event_emitter)

    # Initialize Probes
    system_probe = SystemProbe(interval=5)

    # Start Services
    await agent_runtime.start()
    await event_emitter.start()
    await detection_engine.start()
    await deception_engine.start()

    # Start Probe Loop
    asyncio.create_task(probe_loop(system_probe, detection_engine))

    try:
        while True:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("N7-Sentinel shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise
    finally:
        await deception_engine.stop()
        await detection_engine.stop()
        await event_emitter.stop()
        await agent_runtime.stop()

async def probe_loop(probe, detection_engine):
    """
    Periodically runs a probe and sends data to detection engine.
    """
    logger.info(f"Starting loop for {probe.name}")
    try:
        while True:
            data = await probe.collect()
            await detection_engine.analyze(probe.name, data)
            await asyncio.sleep(probe.interval)
    except Exception as e:
        logger.error(f"Probe loop error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("N7-Sentinel stopped by user.")
