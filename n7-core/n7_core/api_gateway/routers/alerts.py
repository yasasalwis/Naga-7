"""
Alerts Router.
Exposes paginated alert records including LLM-generated narratives.
Ref: TDD Section 4.X LLM Analyzer Dashboard Integration, SRS FR-D004
"""
from fastapi import APIRouter, Query

from ...database.session import async_session_maker
from ...models.alert import Alert as AlertModel
from sqlalchemy import select, desc

router = APIRouter(tags=["Alerts"])


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
        }
        for a in alerts
    ]


@router.get("/{alert_id}")
async def get_alert(alert_id: str):
    """Return a single alert by its UUID."""
    import uuid as _uuid
    async with async_session_maker() as session:
        result = await session.execute(
            select(AlertModel).where(AlertModel.alert_id == _uuid.UUID(alert_id))
        )
        a = result.scalar_one_or_none()
        if a is None:
            from fastapi import HTTPException
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
    }
