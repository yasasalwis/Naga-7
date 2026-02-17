"""
Playbook Engine Service.
Orchestrates automated response playbooks based on incident data.

Ref: TDD Section 4.4 / SRS 3.4 Automated Incident Response (FR-C030, FR-C031)
"""

import logging
import asyncio
import json
import yaml
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

from ..service_manager.base_service import BaseService
from ..messaging.nats_client import nats_client
from ..database.session import async_session_maker
from ..models.incident import Incident as IncidentModel
from ..models.action import Action as ActionModel
from schemas.actions_pb2 import Action as ProtoAction

logger = logging.getLogger("n7-core.playbook-engine")

class PlaybookEngine(BaseService):
    """
    Playbook Engine Service.
    Executes automated response playbooks based on incidents.
    Supports conditional logic, action sequencing, and rollback.
    """
    def __init__(self, playbook_dir: str = "playbooks"):
        super().__init__("PlaybookEngine")
        self.playbook_dir = Path(playbook_dir)
        self.playbooks: Dict[str, Dict] = {}
        self._running = False
    
    async def start(self):
        """Start the playbook engine service"""
        self._running = True
        logger.info("PlaybookEngine started.")
        
        # Load playbooks from YAML files
        await self._load_playbooks()
        
        # Subscribe to incidents 
        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.subscribe(
                "n7.incidents",
                cb=self.handle_incident,
                queue="playbook_engine"
            )
            logger.info("Subscribed to n7.incidents")
        else:
            logger.warning("NATS not connected, PlaybookEngine waiting...")
    
    async def stop(self):
        """Stop the playbook engine service"""
        self._running = False
        logger.info("PlaybookEngine stopped.")
    
    async def _load_playbooks(self):
        """Load all YAML playbooks from the playbook directory"""
        if not self.playbook_dir.exists():
            logger.warning(f"Playbook directory {self.playbook_dir} does not exist, creating it...")
            self.playbook_dir.mkdir(parents=True, exist_ok=True)
            # Create a sample playbook
            await self._create_sample_playbook()
            return
        
        playbook_files = list(self.playbook_dir.glob("*.yaml")) + list(self.playbook_dir.glob("*.yml"))
        
        for playbook_file in playbook_files:
            try:
                with open(playbook_file, 'r') as f:
                    playbook = yaml.safe_load(f)
                    playbook_id = playbook.get('id', playbook_file.stem)
                    self.playbooks[playbook_id] = playbook
                    logger.info(f"Loaded playbook: {playbook_id} from {playbook_file.name}")
            except Exception as e:
                logger.error(f"Error loading playbook {playbook_file}: {e}", exc_info=True)
        
        logger.info(f"Loaded {len(self.playbooks)} playbooks")
    
    async def _create_sample_playbook(self):
        """Create a sample playbook for demonstration"""
        sample_playbook = {
            'id': 'brute_force_response',
            'name': 'Brute Force Attack Response',
            'description': 'Automated response to brute force attacks',
            'trigger': {
                'incident_type': 'brute_force_detected',
                'severity': ['high', 'critical']
            },
            'steps': [
                {
                    'name': 'Block Source IP',
                    'action_type': 'network_block',
                    'params': {
                        'target': '{{incident.affected_assets[0]}}',
                        'duration': 3600
                    },
                    'conditions': [
                        '{{incident.threat_score}} > 70'
                    ]
                },
                {
                    'name': 'Collect Evidence',
                    'action_type': 'collect_evidence',
                    'params': {
                        'asset': '{{incident.affected_assets[0]}}',
                        'artifacts': ['network_logs', 'auth_logs']
                    }
                },
                {
                    'name': 'Notify SOC',
                    'action_type': 'notify',
                    'params': {
                        'channel': 'slack',
                        'message': 'Brute force attack blocked: {{incident.incident_id}}'
                    }
                }
            ]
        }
        
        playbook_file = self.playbook_dir / 'brute_force_response.yaml'
        with open(playbook_file, 'w') as f:
            yaml.dump(sample_playbook, f, default_flow_style=False)
        
        self.playbooks['brute_force_response'] = sample_playbook
        logger.info("Created sample playbook: brute_force_response")
    
    async def handle_incident(self, msg):
        """Handle incoming incidents and execute matching playbooks"""
        try:
            data = json.loads(msg.data.decode())
            incident_id = data.get('incident_id')
            incident_type = data.get('incident_type', 'unknown')
            severity = data.get('severity', 'medium')
            
            logger.info(f"Received incident: {incident_id} type={incident_type} severity={severity}")
            
            # Find matching playbook
            playbook = self._find_matching_playbook(incident_type, severity)
            
            if playbook:
                logger.info(f"Executing playbook: {playbook['id']} for incident {incident_id}")
                await self.execute_playbook(playbook, data)
            else:
                logger.info(f"No matching playbook found for incident type={incident_type}")
                
        except Exception as e:
            logger.error(f"Error handling incident: {e}", exc_info=True)
    
    def _find_matching_playbook(self, incident_type: str, severity: str) -> Optional[Dict]:
        """Find a playbook that matches the incident type and severity"""
        for playbook in self.playbooks.values():
            trigger = playbook.get('trigger', {})
            trigger_type = trigger.get('incident_type')
            trigger_severity = trigger.get('severity', [])
            
            if trigger_type and incident_type == trigger_type:
                if not trigger_severity or severity in trigger_severity:
                    return playbook
        
        return None
    
    async def execute_playbook(self, playbook: Dict, incident_data: Dict):
        """
        Execute a playbook's steps sequentially.
        Supports conditional logic and action dispatching.
        """
        playbook_id = playbook.get('id')
        steps = playbook.get('steps', [])
        incident_id = incident_data.get('incident_id')
        
        executed_actions = []
        
        try:
            for step in steps:
                step_name = step.get('name')
                action_type = step.get('action_type')
                params = step.get('params', {})
                conditions = step.get('conditions', [])
                
                # Evaluate conditions
                if conditions and not self._evaluate_conditions(conditions, incident_data):
                    logger.info(f"Skipping step '{step_name}' - conditions not met")
                    continue
                
                # Template substitution for params
                resolved_params = self._resolve_templates(params, incident_data)
                
                logger.info(f"Executing step '{step_name}' action_type={action_type}")
                
                # Dispatch action via NATS
                action_id = await self._dispatch_action(
                    action_type=action_type,
                    params=resolved_params,
                    incident_id=incident_id
                )
                
                if action_id:
                    executed_actions.append({
                        'action_id': action_id,
                        'step_name': step_name,
                        'action_type': action_type
                    })
            
            logger.info(f"Playbook {playbook_id} completed successfully. Executed {len(executed_actions)} actions.")
            
            # Update incident in database with playbook_id
            await self._update_incident_playbook(incident_id, playbook_id)
            
        except Exception as e:
            logger.error(f"Error executing playbook {playbook_id}: {e}", exc_info=True)
            # TODO: Implement rollback logic for executed_actions
    
    def _evaluate_conditions(self, conditions: List[str], context: Dict) -> bool:
        """
        Evaluate condition expressions.
        Simple implementation using Python eval (unsafe for production - use a proper DSL)
        """
        try:
            for condition in conditions:
                # Replace template variables
                resolved_condition = self._resolve_template_string(condition, context)
                
                # Simple eval - in production, use a safe expression evaluator
                if not eval(resolved_condition):
                    return False
            return True
        except Exception as e:
            logger.error(f"Error evaluating condition: {e}")
            return False
    
    def _resolve_templates(self, params: Dict, context: Dict) -> Dict:
        """Resolve template variables in parameters"""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved[key] = self._resolve_template_string(value, context)
            else:
                resolved[key] = value
        return resolved
    
    def _resolve_template_string(self, template: str, context: Dict) -> str:
        """
        Resolve template placeholders like {{incident.field}}.
        Simple implementation - in production use Jinja2 or similar.
        """
        import re
        
        def replacer(match):
            path = match.group(1).strip()
            parts = path.split('.')
            value = context
            try:
                for part in parts:
                    if part.endswith(']'):  # Array access like affected_assets[0]
                        field, idx = part.split('[')
                        idx = int(idx.rstrip(']'))
                        value = value[field][idx]
                    else:
                        value = value[part]
                return str(value)
            except (KeyError, IndexError, TypeError):
                logger.warning(f"Template variable not found: {path}")
                return match.group(0)  # Return original if not found
        
        return re.sub(r'\{\{([^}]+)\}\}', replacer, template)
    
    async def _dispatch_action(self, action_type: str, params: Dict, incident_id: str) -> Optional[str]:
        """Dispatch an action to strikers via NATS"""
        try:
            import uuid
            action_id = str(uuid.uuid4())
            
            # Create proto action
            proto_action = ProtoAction(
                action_id=action_id,
                incident_id=incident_id,
                action_type=action_type,
                parameters=json.dumps(params),
                status="queued"
            )
            
            # Persist action to database
            async with async_session_maker() as session:
                db_action = ActionModel(
                    action_id=uuid.UUID(action_id),
                    incident_id=uuid.UUID(incident_id) if incident_id else None,
                    action_type=action_type,
                    parameters=params,
                    status="queued",
                    timestamp=datetime.utcnow()
                )
                session.add(db_action)
                await session.commit()
            
            # Publish to NATS
            if nats_client.nc:
                topic = f"n7.actions.{action_type}"
                await nats_client.nc.publish(topic, proto_action.SerializeToString())
                logger.info(f"Dispatched action {action_id} to {topic}")
            
            return action_id
            
        except Exception as e:
            logger.error(f"Error dispatching action: {e}", exc_info=True)
            return None
    
    async def _update_incident_playbook(self, incident_id: str, playbook_id: str):
        """Update incident with executed playbook ID"""
        try:
            import uuid
            async with async_session_maker() as session:
                incident = await session.get(IncidentModel, uuid.UUID(incident_id))
                if incident:
                    incident.playbook_id = playbook_id
                    await session.commit()
                    logger.debug(f"Updated incident {incident_id} with playbook {playbook_id}")
        except Exception as e:
            logger.error(f"Error updating incident playbook: {e}", exc_info=True)
