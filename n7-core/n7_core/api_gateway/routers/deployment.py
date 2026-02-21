import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, BackgroundTasks
from sqlalchemy import select

from ...database.session import async_session_maker
from ...models.infra_node import InfraNode as InfraNodeModel
from ...schemas.infra_node import (
    InfraNode, InfraNodeCreate, DeployRequest, ScanRequest, ScanResult, DeployResponse
)
from ...deployment.service import DeploymentService

logger = logging.getLogger("n7-core.api.deployment")

router = APIRouter(tags=["Deployment"])

# Module-level singleton — shares process lifecycle with the router
_deployment_service = DeploymentService()


@router.post("/scan", response_model=ScanResult)
async def scan_network(request: ScanRequest):
    """
    Trigger a network scan and return discovered nodes.
    New nodes are persisted; existing nodes get their last_seen updated.
    """
    try:
        if request.method == "nmap":
            hosts = await _deployment_service.scan_network_nmap(
                request.network_cidr, request.timeout_seconds
            )
        else:
            hosts = await _deployment_service.scan_network_ping(
                request.network_cidr, request.timeout_seconds
            )
        nodes = await _deployment_service.persist_discovered_nodes(hosts, method=request.method)
        return ScanResult(discovered=len(nodes), nodes=nodes)
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes", response_model=List[InfraNode])
async def list_nodes(skip: int = 0, limit: int = 200):
    """Return all known infrastructure nodes."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(InfraNodeModel)
            .offset(skip)
            .limit(limit)
            .order_by(InfraNodeModel.created_at.desc())
        )
        return result.scalars().all()


@router.post("/nodes", response_model=InfraNode, status_code=201)
async def add_node(node_in: InfraNodeCreate):
    """Manually register a node without scanning."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(InfraNodeModel).where(InfraNodeModel.ip_address == node_in.ip_address)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Node with this IP already exists")

        enc_password = None
        if node_in.ssh_password:
            enc_password = _deployment_service.encrypt_credential(node_in.ssh_password)

        node = InfraNodeModel(
            ip_address=node_in.ip_address,
            hostname=node_in.hostname,
            mac_address=node_in.mac_address,
            os_type=node_in.os_type,
            ssh_port=node_in.ssh_port,
            winrm_port=node_in.winrm_port,
            ssh_username=node_in.ssh_username,
            ssh_password_enc=enc_password,
            ssh_key_path=node_in.ssh_key_path,
            status="discovered",
            discovery_method="manual",
        )
        session.add(node)
        await session.commit()
        await session.refresh(node)
        return node


@router.post("/nodes/{node_id}/deploy", response_model=DeployResponse)
async def deploy_agent(
    node_id: UUID,
    request: DeployRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger async deployment of an agent to the specified node.
    Returns immediately with status 'pending'.
    Poll GET /api/v1/deployment/nodes to observe deployment_status changes.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(InfraNodeModel).where(InfraNodeModel.id == node_id)
        )
        node = result.scalar_one_or_none()
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        if node.deployment_status in ("pending", "in_progress"):
            raise HTTPException(status_code=409, detail="Deployment already in progress")

        node.deployment_status = "pending"
        await session.commit()

    background_tasks.add_task(
        _deployment_service.deploy_agent,
        node_id=str(node_id),
        agent_type=request.agent_type,
        agent_subtype=request.agent_subtype,
        zone=request.zone,
        core_api_url=request.core_api_url,
        nats_url=request.nats_url,
        ssh_username=request.ssh_username,
        ssh_password=request.ssh_password,
        ssh_key_path=request.ssh_key_path,
    )

    return DeployResponse(
        node_id=node_id,
        deployment_status="pending",
        message="Deployment started. Poll GET /api/v1/deployment/nodes for status updates.",
    )
