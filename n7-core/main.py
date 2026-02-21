import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import logging
from typing import Dict, Any
from n7_core.messaging.nats_client import nats_client
from n7_core.service_manager.service_manager import ServiceManager
from n7_core.event_pipeline.service import EventPipelineService
from n7_core.agent_manager.service import AgentManagerService
from n7_core.api_gateway.service import APIGatewayService
from n7_core.threat_correlator.service import ThreatCorrelatorService
from n7_core.llm_analyzer.service import LLMAnalyzerService
from n7_core.decision_engine.service import DecisionEngineService
from n7_core.audit_logger.service import AuditLoggerService
from n7_core.enrichment.service import EnrichmentService
from n7_core.threat_intel.service import ThreatIntelService
from n7_core.ti_fetcher.service import TIFetcherService
from n7_core.playbooks.service import PlaybookEngineService
from n7_core.notifier.service import NotifierService
from n7_core.deployment.service import DeploymentService
from n7_core.utils import print_banner
from n7_core.config import settings
from n7_core.api_gateway.service import register_llm_analyzer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("n7-core")

async def main():
    """
    Main entry point for N7-Core.
    Initializes and starts all core services.
    Ref: TDD Section 4.1 Core Service Decomposition
    """
    print_banner("N7-Core")
    logger.info("Starting N7-Core...")

    # Initialize Service Manager
    service_manager = ServiceManager()

    # Connect to NATS
    try:
        await nats_client.connect()
    except Exception as e:
        logger.error(f"Failed to connect to NATS during startup: {e}")
        # Proceeding — services handle NATS absence gracefully

    # ----------------------------------------------------------------
    # Build services with dependency injection
    # (order matters: dependencies constructed before dependents)
    # ----------------------------------------------------------------

    # Threat Intelligence: ThreatIntelService holds Redis IOC cache;
    # EnrichmentService wraps it for per-event lookups;
    # EventPipelineService calls EnrichmentService after deduplication;
    # TIFetcherService populates the cache from external feeds.
    threat_intel_svc = ThreatIntelService()
    enrichment_svc = EnrichmentService()
    enrichment_svc.set_threat_intel_service(threat_intel_svc)
    event_pipeline_svc = EventPipelineService()
    event_pipeline_svc.set_enrichment_service(enrichment_svc)
    ti_fetcher_svc = TIFetcherService(threat_intel_svc)

    # LLM Analyzer sits between ThreatCorrelator (publishes n7.llm.analyze)
    # and DecisionEngine (consumes n7.alerts). Must be registered before
    # DecisionEngineService so its subscription is active.
    llm_analyzer_svc = LLMAnalyzerService()

    # ----------------------------------------------------------------
    # Register Core Services (strict adherence to TDD Section 4.1)
    # ----------------------------------------------------------------
    service_manager.register(event_pipeline_svc)
    service_manager.register(AgentManagerService())
    service_manager.register(APIGatewayService())
    service_manager.register(threat_intel_svc)
    service_manager.register(enrichment_svc)
    service_manager.register(ti_fetcher_svc)
    service_manager.register(ThreatCorrelatorService())
    service_manager.register(llm_analyzer_svc)
    service_manager.register(DecisionEngineService())
    service_manager.register(AuditLoggerService())
    service_manager.register(PlaybookEngineService())
    service_manager.register(DeploymentService())
    service_manager.register(NotifierService())

    # Expose LLMAnalyzerService to the /health endpoint
    register_llm_analyzer(llm_analyzer_svc)

    # Start all services
    await service_manager.start_all()

    # ------------------------------------------------------------------
    # Post-startup: verify LLM is active and reachable before processing
    # ------------------------------------------------------------------
    llm_ok = await llm_analyzer_svc.check_llm_health()
    if llm_ok:
        logger.info(
            "Startup check: LLM (Ollama) is ACTIVE — enriched narratives enabled."
        )
    else:
        logger.warning(
            "Startup check: LLM (Ollama) is UNREACHABLE — "
            "alert narratives will use rule-based fallback until Ollama recovers. "
            "Ensure Ollama is running at %s and model '%s' is pulled.",
            settings.OLLAMA_URL,
            settings.OLLAMA_MODEL,
        )

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
