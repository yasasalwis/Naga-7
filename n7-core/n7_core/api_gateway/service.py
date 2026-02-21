import asyncio
import logging
from typing import Optional, TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import Config, Server

# Import Routers
from .routers import auth, users, agents, events, deployment, alerts, threat_intel
from .routers import agent_config
from ..config import settings
from ..service_manager.base_service import BaseService

if TYPE_CHECKING:
    from ..llm_analyzer.service import LLMAnalyzerService

logger = logging.getLogger("n7-core.api-gateway")

# Module-level reference set by main.py after LLMAnalyzerService is started.
# Used by the /health endpoint to report live LLM status without circular imports.
_llm_analyzer_ref: Optional["LLMAnalyzerService"] = None


def register_llm_analyzer(svc: "LLMAnalyzerService") -> None:
    """Called from main.py to give the health endpoint access to the LLM service."""
    global _llm_analyzer_ref
    _llm_analyzer_ref = svc


app = FastAPI(title="Naga-7 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agents"])
app.include_router(events.router, prefix="/api/v1/events", tags=["Events"])
app.include_router(deployment.router, prefix="/api/v1/deployment", tags=["Deployment"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])
app.include_router(threat_intel.router, prefix="/api/v1/threat-intel", tags=["Threat Intelligence"])
app.include_router(agent_config.router, prefix="/api/v1/agents", tags=["Agent Config"])


@app.get("/health")
async def health():
    llm_status = "unknown"
    if _llm_analyzer_ref is not None:
        llm_ok = await _llm_analyzer_ref.check_llm_health()
        llm_status = "ok" if llm_ok else "degraded"

    overall = "ok" if llm_status in ("ok", "unknown") else "degraded"
    return {
        "status": overall,
        "components": {
            "llm_analyzer": llm_status,
        },
    }


class APIGatewayService(BaseService):
    """
    API Gateway Service.
    Responsibility: Expose REST API for Dashboard and Integrations.
    """

    def __init__(self):
        super().__init__("APIGatewayService")
        self._server = None

    async def start(self):
        logger.info(f"APIGatewayService ensuring startup on {settings.API_HOST}:{settings.API_PORT}")
        config = Config(app=app, host=settings.API_HOST, port=settings.API_PORT, log_level="info")
        self._server = Server(config)
        # Run uvicorn in a separate task
        asyncio.create_task(self._server.serve())

    async def stop(self):
        if self._server:
            self._server.should_exit = True
        logger.info("APIGatewayService stopped.")
