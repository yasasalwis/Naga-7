import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import logging
from n7_strikers.agent_runtime.service import AgentRuntimeService
from n7_strikers.action_executor.service import ActionExecutorService
from n7_strikers.rollback_manager.service import RollbackManagerService
from n7_strikers.evidence_collector.service import EvidenceCollectorService

from n7_strikers.utils import print_banner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("n7-strikers")

async def main():
    """
    Main entry point for N7-Strikers.
    Initializes and starts the striker agent.
    Ref: TDD Section 6.1 Striker Process Model
    """
    print_banner("N7-Striker")
    logger.info("Starting N7-Striker...")
    
    # Initialize Services
    agent_runtime = AgentRuntimeService()
    action_executor = ActionExecutorService()
    rollback_manager = RollbackManagerService()
    evidence_collector = EvidenceCollectorService()
    
    # Start Services
    await agent_runtime.start()
    await action_executor.start()
    await rollback_manager.start()
    await evidence_collector.start()
    
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("N7-Striker shutting down...")
        await agent_runtime.stop()
        await action_executor.stop()
        await rollback_manager.stop()
        await evidence_collector.stop()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("N7-Striker stopped by user.")
