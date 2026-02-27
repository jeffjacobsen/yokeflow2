"""
Multi-Channel Notification System
==================================

Supports webhook, email, and SMS notifications for interventions.
"""

import asyncio
import aiohttp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import os


class MultiChannelNotificationService:
    """Enhanced notification service with multiple channel support."""

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize multi-channel notification service.

        Args:
            config: Configuration for various notification channels
        """
        self.config = config or {}

        # Channel configurations
        self.webhook_config = self.config.get("webhook", {})
        self.email_config = self.config.get("email", {})
        self.sms_config = self.config.get("sms", {})

        # Rate limiting
        self.last_notification_times: Dict[str, datetime] = {}
        self.min_interval = self.config.get("min_notification_interval", 300)  # 5 minutes

    async def send_notification(
        self,
        title: str,
        message: str,
        details: Dict,
        channels: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """
        Send notification through multiple channels.

        Args:
            title: Notification title
            message: Main message body
            details: Additional details
            channels: List of channels to use (default: all enabled)

        Returns:
            Dictionary of channel: success status
        """
        # Check rate limiting
        if not self._check_rate_limit(details.get("project_id", "global")):
            return {"rate_limited": False}

        # Determine which channels to use
        if channels is None:
            channels = self._get_enabled_channels()

        results = {}

        # Send through each channel
        tasks = []
        if "webhook" in channels:
            tasks.append(self._send_webhook(title, message, details))
        if "email" in channels:
            tasks.append(self._send_email(title, message, details))
        if "sms" in channels:
            tasks.append(self._send_sms(title, message, details))

        # Execute all notifications in parallel
        if tasks:
            channel_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, channel in enumerate(channels):
                if isinstance(channel_results[i], Exception):
                    results[channel] = False
                    print(f"Notification error ({channel}): {channel_results[i]}")
                else:
                    results[channel] = channel_results[i]

        return results

    def _check_rate_limit(self, key: str) -> bool:
        """Check if enough time has passed since last notification."""
        now = datetime.now()
        last_time = self.last_notification_times.get(key)

        if last_time:
            elapsed = (now - last_time).total_seconds()
            if elapsed < self.min_interval:
                return False

        self.last_notification_times[key] = now
        return True

    def _get_enabled_channels(self) -> List[str]:
        """Get list of enabled notification channels."""
        channels = []

        if self.webhook_config.get("enabled") and self.webhook_config.get("url"):
            channels.append("webhook")

        if self.email_config.get("enabled") and self.email_config.get("addresses"):
            channels.append("email")

        if self.sms_config.get("enabled") and self.sms_config.get("numbers"):
            channels.append("sms")

        return channels

    async def _send_webhook(
        self,
        title: str,
        message: str,
        details: Dict
    ) -> bool:
        """Send webhook notification."""
        url = self.webhook_config.get("url")

        if not url:
            return False

        # Format message for different webhook types
        if "slack.com" in url:
            payload = {
                "text": title,
                "attachments": [{
                    "color": "danger",
                    "text": message,
                    "fields": [
                        {"title": k, "value": str(v), "short": True}
                        for k, v in details.items()
                        if k not in ["message", "title"]
                    ],
                    "footer": "YokeFlow Intervention System",
                    "ts": int(datetime.now().timestamp())
                }]
            }
        elif "discord.com" in url:
            payload = {
                "content": f"**{title}**",
                "embeds": [{
                    "description": message,
                    "color": 15158332,  # Red
                    "fields": [
                        {"name": k, "value": str(v)[:1024], "inline": True}
                        for k, v in details.items()
                        if k not in ["message", "title"]
                    ],
                    "footer": {"text": "YokeFlow Intervention System"},
                    "timestamp": datetime.now().isoformat()
                }]
            }
        else:
            # Generic webhook format
            payload = {
                "title": title,
                "message": message,
                "details": details,
                "timestamp": datetime.now().isoformat(),
                "source": "yokeflow_intervention"
            }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status in [200, 201, 204]
        except Exception as e:
            print(f"Webhook notification failed: {e}")
            return False

    async def _send_email(
        self,
        title: str,
        message: str,
        details: Dict
    ) -> bool:
        """Send email notification."""
        smtp_config = self.email_config.get("smtp", {})
        addresses = self.email_config.get("addresses", [])

        if not smtp_config or not addresses:
            return False

        try:
            # Create email message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[YokeFlow] {title}"
            msg["From"] = smtp_config.get("from_address", "yokeflow@localhost")
            msg["To"] = ", ".join(addresses)

            # Create HTML body
            html_body = self._create_email_html(title, message, details)
            msg.attach(MIMEText(html_body, "html"))

            # Create plain text alternative
            text_body = f"{title}\n\n{message}\n\nDetails:\n"
            for k, v in details.items():
                text_body += f"  {k}: {v}\n"
            msg.attach(MIMEText(text_body, "plain"))

            # Send email
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._send_email_sync,
                smtp_config,
                addresses,
                msg
            )

            return True

        except Exception as e:
            print(f"Email notification failed: {e}")
            return False

    def _send_email_sync(
        self,
        smtp_config: Dict,
        addresses: List[str],
        msg: MIMEMultipart
    ):
        """Synchronous email sending (run in executor)."""
        with smtplib.SMTP(
            smtp_config.get("host", "localhost"),
            smtp_config.get("port", 587)
        ) as server:
            if smtp_config.get("use_tls", True):
                server.starttls()

            if smtp_config.get("username") and smtp_config.get("password"):
                server.login(
                    smtp_config["username"],
                    smtp_config["password"]
                )

            server.send_message(msg)

    def _create_email_html(self, title: str, message: str, details: Dict) -> str:
        """Create HTML email body."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #dc3545; color: white; padding: 15px; border-radius: 5px; }}
                .content {{ background: #f8f9fa; padding: 15px; margin-top: 10px; border-radius: 5px; }}
                .details {{ margin-top: 15px; }}
                .detail-item {{ margin: 5px 0; padding: 5px; background: white; border-radius: 3px; }}
                .footer {{ margin-top: 20px; color: #6c757d; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{title}</h2>
            </div>
            <div class="content">
                <p>{message}</p>
                <div class="details">
                    <h3>Details:</h3>
        """

        for key, value in details.items():
            if key not in ["title", "message"]:
                html += f'<div class="detail-item"><strong>{key}:</strong> {value}</div>'

        html += """
                </div>
            </div>
            <div class="footer">
                <p>YokeFlow Intervention System - Automated Notification</p>
                <p>Time: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
            </div>
        </body>
        </html>
        """

        return html

    async def _send_sms(
        self,
        title: str,
        message: str,
        details: Dict
    ) -> bool:
        """Send SMS notification (using Twilio)."""
        try:
            # Import Twilio client (optional dependency)
            from twilio.rest import Client

            account_sid = self.sms_config.get("twilio_account_sid") or os.getenv("TWILIO_ACCOUNT_SID")
            auth_token = self.sms_config.get("twilio_auth_token") or os.getenv("TWILIO_AUTH_TOKEN")
            from_number = self.sms_config.get("from_number")
            to_numbers = self.sms_config.get("numbers", [])

            if not all([account_sid, auth_token, from_number, to_numbers]):
                return False

            client = Client(account_sid, auth_token)

            # Create concise SMS message
            sms_text = f"[YokeFlow] {title}\n{message[:100]}"
            if details.get("project_name"):
                sms_text += f"\nProject: {details['project_name']}"

            # Send to all configured numbers
            success = True
            for to_number in to_numbers:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        client.messages.create,
                        sms_text,
                        from_number,
                        to_number
                    )
                except Exception as e:
                    print(f"SMS to {to_number} failed: {e}")
                    success = False

            return success

        except ImportError:
            print("Twilio not installed. Run: pip install twilio")
            return False
        except Exception as e:
            print(f"SMS notification failed: {e}")
            return False


class NotificationPreferencesManager:
    """Manages per-project notification preferences."""

    @staticmethod
    async def get_preferences(project_id: str) -> Dict:
        """Get notification preferences for a project."""
        from server.database.connection import DatabaseManager

        async with DatabaseManager() as db:
            query = """
                SELECT * FROM notification_preferences
                WHERE project_id = %s::UUID
            """

            result = await db.fetch_one(query, project_id)

            if result:
                return dict(result)
            else:
                # Return defaults if no preferences set
                return {
                    "webhook_enabled": False,
                    "email_enabled": False,
                    "sms_enabled": False,
                    "notify_on_retry_limit": True,
                    "notify_on_critical_error": True,
                    "notify_on_timeout": True,
                    "notify_on_manual_pause": False,
                    "min_notification_interval": 300
                }

    @staticmethod
    async def update_preferences(
        project_id: str,
        preferences: Dict
    ) -> bool:
        """Update notification preferences for a project."""
        from server.database.connection import DatabaseManager

        async with DatabaseManager() as db:
            query = """
                INSERT INTO notification_preferences (
                    project_id,
                    webhook_enabled, webhook_url,
                    email_enabled, email_addresses,
                    sms_enabled, sms_numbers,
                    notify_on_retry_limit,
                    notify_on_critical_error,
                    notify_on_timeout,
                    notify_on_manual_pause,
                    min_notification_interval
                ) VALUES (
                    %s::UUID,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (project_id)
                DO UPDATE SET
                    webhook_enabled = EXCLUDED.webhook_enabled,
                    webhook_url = EXCLUDED.webhook_url,
                    email_enabled = EXCLUDED.email_enabled,
                    email_addresses = EXCLUDED.email_addresses,
                    sms_enabled = EXCLUDED.sms_enabled,
                    sms_numbers = EXCLUDED.sms_numbers,
                    notify_on_retry_limit = EXCLUDED.notify_on_retry_limit,
                    notify_on_critical_error = EXCLUDED.notify_on_critical_error,
                    notify_on_timeout = EXCLUDED.notify_on_timeout,
                    notify_on_manual_pause = EXCLUDED.notify_on_manual_pause,
                    min_notification_interval = EXCLUDED.min_notification_interval,
                    updated_at = NOW()
            """

            await db.execute(
                query,
                project_id,
                preferences.get("webhook_enabled", False),
                preferences.get("webhook_url"),
                preferences.get("email_enabled", False),
                preferences.get("email_addresses", []),
                preferences.get("sms_enabled", False),
                preferences.get("sms_numbers", []),
                preferences.get("notify_on_retry_limit", True),
                preferences.get("notify_on_critical_error", True),
                preferences.get("notify_on_timeout", True),
                preferences.get("notify_on_manual_pause", False),
                preferences.get("min_notification_interval", 300)
            )

            return True