import logging
import json
from datetime import datetime
from sqlalchemy import select
from ..service_manager.base_service import BaseService
from ..messaging.nats_client import nats_client
from ..database.session import async_session_maker
from ..models.audit_log import AuditLog

logger = logging.getLogger("n7-core.audit-logger")

class AuditLoggerService(BaseService):
    """
    Audit Logger Service.
    Responsibility: Immutable logging of all events, decisions, and actions with hash-chain tamper detection.
    Ref: TDD Section 4.1 / SRS 3.5 Audit and Compliance (FR-C040, FR-C041, FR-C042)
    """
    def __init__(self):
        super().__init__("AuditLoggerService")
        self._running = False

    async def start(self):
        self._running = True
        logger.info("AuditLoggerService started.")
        
        # Subscribe to audit events
        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.subscribe(
                "n7.audit", 
                cb=self.handle_audit_event,
                queue="audit_logger"
            )
            logger.info("Subscribed to n7.audit")
        else:
            logger.warning("NATS not connected, AuditLoggerService waiting for connection...")

    async def stop(self):
        self._running = False
        logger.info("AuditLoggerService stopped.")

    async def log_entry(self, actor: str, action: str, resource: str = None, details: dict = None):
        """
        Create an audit log entry with hash chain.
        Can be called directly by other services or via NATS.
        """
        try:
            async with async_session_maker() as session:
                # Get the most recent audit log entry to chain from
                stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(1)
                result = await session.execute(stmt)
                previous_entry = result.scalar_one_or_none()
                
                previous_hash = previous_entry.current_hash if previous_entry else None
                
                # Create new entry
                timestamp = datetime.utcnow()
                log_id = str(AuditLog.__table__.columns['log_id'].default.arg())  # Generate UUID
                
                # Calculate hash
                current_hash = AuditLog.calculate_hash(
                    log_id=log_id,
                    timestamp=timestamp.isoformat(),
                    actor=actor,
                    action=action,
                    resource=resource or "",
                    details=json.dumps(details or {}, sort_keys=True),
                    previous_hash=previous_hash or ""
                )
                
                audit_entry = AuditLog(
                    timestamp=timestamp,
                    actor=actor,
                    action=action,
                    resource=resource,
                    details=details or {},
                    previous_hash=previous_hash,
                    current_hash=current_hash
                )
                
                session.add(audit_entry)
                await session.commit()
                
                logger.debug(f"Audit log created: {action} by {actor}")
                
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}", exc_info=True)

    async def handle_audit_event(self, msg):
        """
        Callback for NATS audit events.
        Expected message format (JSON):
        {
            "actor": "username or agent_id",
            "action": "event_type",
            "resource": "resource_id",
            "details": {...}
        }
        """
        try:
            data = json.loads(msg.data.decode())
            await self.log_entry(
                actor=data.get("actor", "system"),
                action=data.get("action", "unknown"),
                resource=data.get("resource"),
                details=data.get("details", {})
            )
        except Exception as e:
            logger.error(f"Error processing audit event: {e}", exc_info=True)

    async def verify_hash_chain(self) -> bool:
        """
        Verify the integrity of the entire audit log hash chain.
        Returns True if chain is intact, False if tampering detected.
        """
        try:
            async with async_session_maker() as session:
                stmt = select(AuditLog).order_by(AuditLog.timestamp.asc())
                result = await session.execute(stmt)
                entries = result.scalars().all()
                
                previous_hash = None
                for entry in entries:
                    # Recalculate hash
                    expected_hash = AuditLog.calculate_hash(
                        log_id=str(entry.log_id),
                        timestamp=entry.timestamp.isoformat(),
                        actor=entry.actor,
                        action=entry.action,
                        resource=entry.resource or "",
                        details=json.dumps(entry.details, sort_keys=True),
                        previous_hash=entry.previous_hash or ""
                    )
                    
                    # Verify hash matches
                    if expected_hash != entry.current_hash:
                        logger.error(f"Hash mismatch detected at log_id={entry.log_id}")
                        return False
                    
                    # Verify previous hash chain
                    if entry.previous_hash != previous_hash:
                        logger.error(f"Chain broken at log_id={entry.log_id}")
                        return False
                    
                    previous_hash = entry.current_hash
                
                logger.info("Audit log hash chain verified successfully")
                return True
                
        except Exception as e:
            logger.error(f"Error verifying hash chain: {e}", exc_info=True)
            return False
