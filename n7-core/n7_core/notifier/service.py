
import logging
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List
import httpx

from ..service_manager.base_service import BaseService
from ..messaging.nats_client import nats_client
from ..config import settings

logger = logging.getLogger("n7-core.notifier")

class NotifierService(BaseService):
    """
    Notifier Service.
    Responsibility: Send notifications via multiple channels (Slack, Email, Webhook, PagerDuty).
    Ref: SRS FR-C023, FR-D007
    """
    def __init__(self):
        super().__init__("NotifierService")
        self._running = False
        self.http_client = None

    async def start(self):
        self._running = True
        self.http_client = httpx.AsyncClient(timeout=10.0)
        logger.info("NotifierService started.")
        
        # Subscribe to notification requests
        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.subscribe(
                "n7.notifications", 
                cb=self.handle_notification,
                queue="notifier"
            )
            logger.info("Subscribed to n7.notifications")
        else:
            logger.warning("NATS not connected, NotifierService waiting for connection...")

    async def stop(self):
        self._running = False
        if self.http_client:
            await self.http_client.aclose()
        logger.info("NotifierService stopped.")

    async def handle_notification(self, msg):
        """
        Handle incoming notification requests from NATS.
        Expected format:
        {
            "channels": ["slack", "email", "webhook", "pagerduty"],
            "severity": "high",
            "title": "Alert Title",
            "message": "Alert message body",
            "details": {...}
        }
        """
        try:
            data = json.loads(msg.data.decode())
            channels = data.get("channels", [])
            
            for channel in channels:
                if channel == "slack":
                    await self.send_slack(data)
                elif channel == "email":
                    await self.send_email(data)
                elif channel == "webhook":
                    await self.send_webhook(data)
                elif channel == "pagerduty":
                    await self.send_pagerduty(data)
                    
        except Exception as e:
            logger.error(f"Error processing notification: {e}", exc_info=True)

    async def send_slack(self, notification: Dict):
        """Send notification to Slack via webhook."""
        try:
            slack_url = getattr(settings, 'SLACK_WEBHOOK_URL', None)
            if not slack_url:
                logger.warning("SLACK_WEBHOOK_URL not configured, skipping Slack notification")
                return
            
            # Build Slack message
            color_map = {
                "critical": "danger",
                "high": "warning",
                "medium": "#ffcc00",
                "low": "good"
            }
            
            payload = {
                "attachments": [
                    {
                        "color": color_map.get(notification.get("severity", "medium"), "good"),
                        "title": notification.get("title", "N7 Alert"),
                        "text": notification.get("message", ""),
                        "fields": [
                            {"title": "Severity", "value": notification.get("severity", "unknown"), "short": True}
                        ],
                        "footer": "Naga-7",
                        "ts": int(notification.get("timestamp", 0))
                    }
                ]
            }
            
            response = await self.http_client.post(slack_url, json=payload)
            if response.status_code == 200:
                logger.info("Slack notification sent successfully")
            else:
                logger.error(f"Slack notification failed: {response.status_code} {response.text}")
                
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}", exc_info=True)

    async def send_email(self, notification: Dict):
        """Send notification via email (SMTP)."""
        try:
            smtp_host = getattr(settings, 'SMTP_HOST', None)
            smtp_port = getattr(settings, 'SMTP_PORT', 587)
            smtp_user = getattr(settings, 'SMTP_USER', None)
            smtp_password = getattr(settings, 'SMTP_PASSWORD', None)
            email_to = getattr(settings, 'EMAIL_RECIPIENTS', [])
            email_from = getattr(settings, 'EMAIL_FROM', 'naga7@example.com')
            
            if not all([smtp_host, smtp_user, smtp_password]) or not email_to:
                logger.warning("Email settings not fully configured, skipping email notification")
                return
            
            msg = MIMEMultipart()
            msg['From'] = email_from
            msg['To'] = ', '.join(email_to)
            msg['Subject'] = f"[N7 {notification.get('severity', '').upper()}] {notification.get('title', 'Alert')}"
            
            body = f"""
Naga-7 Alert Notification

Severity: {notification.get('severity', 'unknown')}
Title: {notification.get('title', 'N/A')}

Message:
{notification.get('message', '')}

Details:
{json.dumps(notification.get('details', {}), indent=2)}
"""
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            
            logger.info("Email notification sent successfully")
                
        except Exception as e:
            logger.error(f"Error sending email notification: {e}", exc_info=True)

    async def send_webhook(self, notification: Dict):
        """Send notification to generic webhook."""
        try:
            webhook_url = notification.get("webhook_url") or getattr(settings, 'WEBHOOK_URL', None)
            if not webhook_url:
                logger.warning("Webhook URL not provided, skipping webhook notification")
                return
            
            payload = {
                "severity": notification.get("severity"),
                "title": notification.get("title"),
                "message": notification.get("message"),
                "details": notification.get("details", {}),
                "timestamp": notification.get("timestamp")
            }
            
            response = await self.http_client.post(webhook_url, json=payload)
            if response.status_code in [200, 201, 202]:
                logger.info("Webhook notification sent successfully")
            else:
                logger.error(f"Webhook notification failed: {response.status_code} {response.text}")
                
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}", exc_info=True)

    async def send_pagerduty(self, notification: Dict):
        """Send notification to PagerDuty Events API v2."""
        try:
            pd_integration_key = getattr(settings, 'PAGERDUTY_INTEGRATION_KEY', None)
            if not pd_integration_key:
                logger.warning("PAGERDUTY_INTEGRATION_KEY not configured, skipping PagerDuty notification")
                return
            
            severity_map = {
                "critical": "critical",
                "high": "error",
                "medium": "warning",
                "low": "info"
            }
            
            payload = {
                "routing_key": pd_integration_key,
                "event_action": "trigger",
                "payload": {
                    "summary": notification.get("title", "N7 Alert"),
                    "severity": severity_map.get(notification.get("severity", "medium"), "warning"),
                    "source": "naga7-core",
                    "custom_details": notification.get("details", {})
                }
            }
            
            response = await self.http_client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload
            )
            
            if response.status_code == 202:
                logger.info("PagerDuty notification sent successfully")
            else:
                logger.error(f"PagerDuty notification failed: {response.status_code} {response.text}")
                
        except Exception as e:
            logger.error(f"Error sending PagerDuty notification: {e}", exc_info=True)
