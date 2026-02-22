"""
Alerts Router.
Exposes paginated alert records including LLM-generated narratives.
Also provides operator-driven striker dispatch from the dashboard.
Ref: TDD Section 4.X LLM Analyzer Dashboard Integration, SRS FR-D004, FR-K001
"""
import json
import logging
import uuid as _uuid
from typing import List, Optional
import os
import time
import base64
import nkeys

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from ..auth import get_current_active_user

from ...database.session import async_session_maker
from ...messaging.nats_client import nats_client
from ...models.alert import Alert as AlertModel
from ...models.action import Action as ActionModel
from datetime import datetime
from sqlalchemy import select, desc

router = APIRouter(tags=["Alerts"])
logger = logging.getLogger("n7-core.alerts-router")


# ---------------------------------------------------------------------------
# Schemas for dispatch
# ---------------------------------------------------------------------------

class StrikerAction(BaseModel):
    """A single action to dispatch to a striker."""
    action_type: str          # e.g. network_block, kill_process, isolate_host
    parameters: dict = {}     # Action-specific params

class DispatchRequest(BaseModel):
    """Operator-confirmed dispatch of one or more striker actions from the dashboard."""
    actions: List[StrikerAction]
    operator_note: Optional[str] = None  # Optional reason / free-text note

class DispatchResult(BaseModel):
    action_type: str
    action_id: str
    status: str               # queued | error
    error: Optional[str] = None


@router.get("/ws-token")
async def get_ws_token(current_user=Depends(get_current_active_user)):
    """
    Generate a short-lived, read-only NATS User JWT for the dashboard.
    Ref: SRS FR-D004 Real-time alerts
    """
    try:
        # Load Account Seed
        seed_path = os.path.join(os.path.dirname(__file__), "..", "..", "certs", "account.seed")
        with open(seed_path, "rb") as f:
            account_seed = f.read().strip()
            
        # Generate ephemeral User NKey
        user_key = nkeys.gen_key(nkeys.PREFIX_BYTE_USER)
        user_pub = user_key.public_key.decode()
        
        # Issuer is the Account
        account_pub = nkeys.from_seed(account_seed).public_key.decode()
        
        iat = int(time.time())
        exp = iat + 86400  # 24 hour expiration for demo
        
        claims = {
            "jti": base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip('='),
            "iat": iat,
            "exp": exp,
            "iss": account_pub,
            "name": f"dashboard-{current_user.username}",
            "sub": user_pub,
            "nats": {
                "type": "user",
                "version": 2,
                "pub": {},  # No publish permissions
                "sub": {"allow": ["n7.alerts.critical.new", "n7.actions.>"]},
            }
        }
        
        # Sign the JWT
        header = {"typ": "jwt", "alg": "ed25519-nkey"}
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        claims_b64 = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
        payload = f"{header_b64}.{claims_b64}"
        
        sig = nkeys.from_seed(account_seed).sign(payload.encode())
        sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip('=')
        
        jwt_token = f"{payload}.{sig_b64}"
        user_seed = user_key.seed().decode()
        
        return {
            "jwt": jwt_token,
            "seed": user_seed
        }
    except Exception as e:
        logger.error(f"Failed to generate ws-token: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate WebSocket token")


@router.get("/")
async def list_alerts(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """
    Return a paginated list of alerts, newest first.
    Includes all LLM-generated enrichment fields (llm_narrative, mitre tactic/technique).
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(AlertModel)
            .order_by(desc(AlertModel.created_at))
            .offset(skip)
            .limit(limit)
        )
        alerts = result.scalars().all()

    return [
        {
            "id": str(a.id),
            "alert_id": str(a.alert_id) if hasattr(a, "alert_id") else str(a.id),
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "severity": a.severity,
            "threat_score": a.threat_score,
            "status": a.status,
            "verdict": a.verdict,
            "affected_assets": a.affected_assets or [],
            "reasoning": a.reasoning or {},
            "event_ids": a.event_ids or [],
            # LLM enrichment fields
            "llm_narrative": a.llm_narrative,
            "llm_mitre_tactic": a.llm_mitre_tactic,
            "llm_mitre_technique": a.llm_mitre_technique,
            "llm_remediation": a.llm_remediation,
        }
        for a in alerts
    ]


@router.get("/{alert_id}")
async def get_alert(alert_id: str):
    """Return a single alert by its UUID."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(AlertModel).where(AlertModel.alert_id == _uuid.UUID(alert_id))
        )
        a = result.scalar_one_or_none()
        if a is None:
            raise HTTPException(status_code=404, detail="Alert not found")

    return {
        "id": str(a.id),
        "alert_id": str(a.alert_id) if hasattr(a, "alert_id") else str(a.id),
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "severity": a.severity,
        "threat_score": a.threat_score,
        "status": a.status,
        "verdict": a.verdict,
        "affected_assets": a.affected_assets or [],
        "reasoning": a.reasoning or {},
        "event_ids": a.event_ids or [],
        "llm_narrative": a.llm_narrative,
        "llm_mitre_tactic": a.llm_mitre_tactic,
        "llm_mitre_technique": a.llm_mitre_technique,
        "llm_remediation": a.llm_remediation,
    }


@router.post("/{alert_id}/dispatch")
async def dispatch_striker_actions(alert_id: str, req: DispatchRequest):
    """
    Operator-driven dispatch of striker actions for a specific alert.
    The dashboard calls this after the operator reviews LLM recommendations
    and clicks 'Dispatch'. Each action is persisted to the DB and published
    to the appropriate n7.actions.{action_type} NATS subject.
    Ref: SRS FR-K001, FR-D005
    """
    # Validate alert exists
    async with async_session_maker() as session:
        result = await session.execute(
            select(AlertModel).where(AlertModel.alert_id == _uuid.UUID(alert_id))
        )
        alert = result.scalar_one_or_none()
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")

    results: list[dict] = []

    for action in req.actions:
        action_id = str(_uuid.uuid4())
        try:
            # Persist action to DB
            async with async_session_maker() as session:
                db_action = ActionModel(
                    action_id=_uuid.UUID(action_id),
                    incident_id=None,
                    action_type=action.action_type,
                    parameters={
                        **action.parameters,
                        "_source": "operator_dispatch",
                        "_alert_id": alert_id,
                        "_operator_note": req.operator_note or "",
                    },
                    status="queued",
                    timestamp=datetime.utcnow(),
                )
                session.add(db_action)
                await session.commit()

            # Publish to NATS
            if nats_client.nc and nats_client.nc.is_connected:
                try:
                    from schemas.actions_pb2 import Action as ProtoAction
                    proto = ProtoAction(
                        action_id=action_id,
                        incident_id="",
                        action_type=action.action_type,
                        parameters=json.dumps(action.parameters),
                        status="queued",
                    )
                    await nats_client.nc.publish(
                        f"n7.actions.{action.action_type}",
                        proto.SerializeToString(),
                    )
                    logger.info(
                        f"Operator dispatched action {action_id} "
                        f"type={action.action_type} for alert={alert_id}"
                    )
                except Exception as proto_err:
                    # Fallback: publish JSON if protobuf import fails
                    payload = json.dumps({
                        "action_id": action_id,
                        "action_type": action.action_type,
                        "parameters": action.parameters,
                        "status": "queued",
                    }).encode()
                    await nats_client.nc.publish(f"n7.actions.{action.action_type}", payload)
                    logger.warning(f"Proto fallback used for action {action_id}: {proto_err}")
            else:
                logger.warning(
                    f"NATS unavailable — action {action_id} persisted to DB only (queued)"
                )

            results.append({"action_type": action.action_type, "action_id": action_id, "status": "queued"})

        except Exception as e:
            logger.error(f"Failed to dispatch action {action.action_type}: {e}", exc_info=True)
            results.append({
                "action_type": action.action_type,
                "action_id": action_id,
                "status": "error",
                "error": str(e),
            })

    return {"alert_id": alert_id, "dispatched": results}
