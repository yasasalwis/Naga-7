import asyncio
import logging
from uvicorn import Config, Server
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..service_manager.base_service import BaseService
from ..config import settings
from ..database.session import async_session_maker
from ..models.agent import Agent
from ..models.alert import Alert
from sqlalchemy import select

logger = logging.getLogger("n7-core.api-gateway")

app = FastAPI(title="Naga-7 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/agents")
async def get_agents():
    async with async_session_maker() as session:
        result = await session.execute(select(Agent))
        agents = result.scalars().all()
        return agents

@app.get("/api/events")
async def get_events(limit: int = 50):
    # Mock response because we didn't implement Event model fully yet in step 128
    # But let's check if we can return empty list or mock data
    return [
        {"event_id": "evt-1", "timestamp": "2026-02-17T10:00:00Z", "event_class": "process", "severity": "info", "raw_data": "sample"},
        {"event_id": "evt-2", "timestamp": "2026-02-17T10:00:05Z", "event_class": "network", "severity": "medium", "raw_data": "suspicious port"}
    ]

@app.get("/api/alerts")
async def get_alerts():
    async with async_session_maker() as session:
        result = await session.execute(select(Alert))
        alerts = result.scalars().all()
        return alerts

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
