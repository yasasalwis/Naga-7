import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import Config, Server

# Import Routers
from .routers import auth, users, agents, events, deployment, alerts, threat_intel
from ..config import settings
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.api-gateway")

app = FastAPI(title="Naga-7 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(deployment.router, prefix="/api/deployment", tags=["Deployment"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(threat_intel.router, prefix="/api/threat-intel", tags=["Threat Intelligence"])


@app.get("/health")
async def health():
    return {"status": "ok"}


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
