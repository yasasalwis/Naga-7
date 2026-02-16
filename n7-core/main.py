
import asyncio
import logging
from typing import Dict, Any
from n7_core.messaging.nats_client import nats_client
from n7_core.service_manager.service_manager import ServiceManager
from n7_core.event_pipeline.service import EventPipelineService
from n7_core.agent_manager.service import AgentManagerService
from n7_core.api_gateway.service import APIGatewayService
from n7_core.threat_correlator.service import ThreatCorrelatorService
from n7_core.decision_engine.service import DecisionEngineService
from n7_core.audit_logger.service import AuditLoggerService
from n7_core.enrichment.service import EnrichmentService
from n7_core.threat_intel.service import ThreatIntelService
from n7_core.playbooks.service import PlaybookEngineService
from n7_core.notifier.service import NotifierService

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("n7-core")

async def main():
    """
    Main entry point for N7-Core.
    Initializes and starts all core services.
    """
    logger.info("Starting N7-Core...")
    
    # Initialize Service Manager
    service_manager = ServiceManager()

    # Connect to NATS
    try:
        await nats_client.connect()
    except Exception as e:
        logger.error(f"Failed to connect to NATS during startup: {e}")
        # Proceeding, but services depending on NATS will need to handle this
    
    # Register Core Services
    # strict adherence to TDD Section 4.1
    service_manager.register(EventPipelineService())
    service_manager.register(AgentManagerService())
    service_manager.register(APIGatewayService())
    service_manager.register(ThreatCorrelatorService())
    service_manager.register(DecisionEngineService())
    service_manager.register(AuditLoggerService())
    service_manager.register(EnrichmentService())
    service_manager.register(ThreatIntelService())
    service_manager.register(PlaybookEngineService())
    service_manager.register(NotifierService())
    
    # Start all services
    await service_manager.start_all()
    
    try:
        # Keep the main loop running
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("N7-Core shutting down...")
        await service_manager.stop_all()
        await nats_client.close()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("N7-Core stopped by user.")
