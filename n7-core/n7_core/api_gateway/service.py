
import asyncio
import logging
import uvicorn
from fastapi import FastAPI
from ..service_manager.base_service import BaseService
from .routers import auth, users, events, agents

logger = logging.getLogger("n7-core.api-gateway")

class APIGatewayService(BaseService):
    """
    API Gateway Service.
    Responsibility: Expose REST API (FastAPI).
    Ref: TDD Section 4.1 Core Service Decomposition
    """
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        super().__init__("APIGatewayService")
        self.host = host
        self.port = port
        self.app = FastAPI(title="Naga-7 API", version="1.0.0")
        
        # Include Routers
        self.app.include_router(auth.router)
        self.app.include_router(users.router)
        self.app.include_router(events.router)
        self.app.include_router(agents.router)
        
        self.server = None

    async def start(self):
        logger.info(f"APIGatewayService starting on {self.host}:{self.port}...")
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        self.server = uvicorn.Server(config)
        # Run server in a background task
        asyncio.create_task(self.server.serve())

    async def stop(self):
        if self.server:
            self.server.should_exit = True
            # Allow some time for graceful shutdown if needed, though server.serve() handles it
            logger.info("APIGatewayService stopped.")
