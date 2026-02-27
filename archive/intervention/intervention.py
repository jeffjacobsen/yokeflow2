"""
Intervention System for YokeFlow
=================================

Detects retry loops, critical errors, and triggers notifications
when sessions get stuck or encounter blockers.
"""

import json
import asyncio
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict
import aiohttp
from pathlib import Path

from server.database.connection import DatabaseManager
from server.agent.quality_detector import QualityPatternDetector


class RetryTracker:
    """Track retry attempts to detect infinite loops."""

    def __init__(self, max_retries: int = 3):
        """
        Initialize retry tracker.

        Args:
            max_retries: Maximum retries allowed before considering it a blocker
        """
        self.max_retries = max_retries
        self.command_counts: Dict[str, int] = defaultdict(int)
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.last_commands: List[str] = []
        self.max_history = 20  # Keep last N commands for pattern detection

    def _get_command_signature(self, tool_name: str, tool_input: Dict) -> str:
        """
        Create a signature for a command to track retries.

        Args:
            tool_name: Name of the tool being used
            tool_input: Input parameters for the tool

        Returns:
            A hash signature of the command
        """
        # For bash commands, extract the actual command
        if tool_name in ["bash", "bash_docker", "mcp__task-manager__bash_docker"]:
            command = tool_input.get("command", "")
            # Normalize command by removing variable parts like timestamps
            command = command.split("2>&1")[0].strip()  # Remove redirect operators
            command = command.split(">")[0].strip()  # Remove output redirects
            signature_str = f"{tool_name}:{command}"
        else:
            # For other tools, use tool name and key parameters
            key_params = {k: v for k, v in tool_input.items()
                         if k not in ["timestamp", "id", "session_id"]}
            signature_str = f"{tool_name}:{json.dumps(key_params, sort_keys=True)}"

        return hashlib.md5(signature_str.encode()).hexdigest()

    def track_command(self, tool_name: str, tool_input: Dict) -> Tuple[bool, Optional[str]]:
        """
        Track a command execution and detect retry loops.

        Args:
            tool_name: Name of the tool being used
            tool_input: Input parameters for the tool

        Returns:
            Tuple of (is_blocked, reason)
        """
        signature = self._get_command_signature(tool_name, tool_input)
        self.command_counts[signature] += 1

        # Keep history
        self.last_commands.append(signature)
        if len(self.last_commands) > self.max_history:
            self.last_commands.pop(0)

        # Check if we've exceeded retry limit
        if self.command_counts[signature] > self.max_retries:
            command_preview = tool_input.get("command", str(tool_input))[:100]
            return True, f"Command attempted {self.command_counts[signature]} times: {command_preview}"

        # Check for rapid repetition pattern (same command 3 times in last 5 commands)
        if len(self.last_commands) >= 5:
            last_5 = self.last_commands[-5:]
            if last_5.count(signature) >= 3:
                command_preview = tool_input.get("command", str(tool_input))[:100]
                return True, f"Rapid repetition detected for: {command_preview}"

        return False, None

    def track_error(self, error_message: str) -> Tuple[bool, Optional[str]]:
        """
        Track errors to detect repeated failures.

        Args:
            error_message: The error message

        Returns:
            Tuple of (is_blocked, reason)
        """
        # Normalize error message
        error_key = error_message[:200] if error_message else "unknown_error"
        self.error_counts[error_key] += 1

        if self.error_counts[error_key] > self.max_retries:
            return True, f"Error occurred {self.error_counts[error_key]} times: {error_key[:100]}"

        return False, None

    def get_stats(self) -> Dict:
        """Get retry statistics."""
        return {
            "total_unique_commands": len(self.command_counts),
            "total_retries": sum(self.command_counts.values()) - len(self.command_counts),
            "max_retries_on_single_command": max(self.command_counts.values()) if self.command_counts else 0,
            "unique_errors": len(self.error_counts),
            "total_errors": sum(self.error_counts.values())
        }


class BlockerDetector:
    """Detect critical errors and infrastructure blockers."""

    # Critical error patterns that indicate infrastructure issues
    CRITICAL_PATTERNS = [
        # Prisma errors
        ("Prisma schema validation", "prisma_schema_error"),
        ("Command \"prisma\" not found", "prisma_not_installed"),
        ("ERR_PNPM_RECURSIVE_EXEC_FIRST_FAIL.*prisma", "prisma_exec_fail"),

        # Redis errors
        ("Redis not running", "redis_not_running"),
        ("Could not connect to Redis", "redis_connection_failed"),
        ("ECONNREFUSED.*6379", "redis_connection_refused"),

        # Database errors
        ("Database connection failed", "database_connection_failed"),
        ("ECONNREFUSED.*5432", "postgres_connection_refused"),
        ("authentication failed for user", "database_auth_failed"),

        # Port conflicts
        ("Port.*already in use", "port_conflict"),
        ("EADDRINUSE", "address_in_use"),

        # Missing dependencies
        ("Cannot find module", "module_not_found"),
        ("Module not found", "module_not_found"),
        ("Command not found", "command_not_found"),

        # Build/compilation errors
        ("TypeScript error", "typescript_error"),
        ("SyntaxError", "syntax_error"),
        ("Compilation failed", "compilation_failed"),
    ]

    def __init__(self):
        """Initialize blocker detector."""
        self.detected_blockers: List[Dict] = []

    def check_for_blocker(self, error_message: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if an error indicates a critical blocker.

        Args:
            error_message: The error message to check

        Returns:
            Tuple of (is_blocker, blocker_info)
        """
        import re

        for pattern, error_type in self.CRITICAL_PATTERNS:
            if re.search(pattern, error_message, re.IGNORECASE):
                blocker_info = {
                    "type": error_type,
                    "pattern": pattern,
                    "message": error_message[:500],
                    "timestamp": datetime.now().isoformat(),
                    "requires_human_intervention": True
                }
                self.detected_blockers.append(blocker_info)
                return True, blocker_info

        return False, None

    def get_blockers(self) -> List[Dict]:
        """Get list of detected blockers."""
        return self.detected_blockers


class NotificationService:
    """Send notifications when intervention is needed."""

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize notification service.

        Args:
            config: Configuration for notifications (webhook URL, etc.)
        """
        self.config = config or {}
        self.webhook_url = self.config.get("webhook_url")
        self.enabled = self.config.get("enabled", False)

    async def send_blocker_notification(
        self,
        session_id: str,
        project_name: str,
        blocker_info: Dict,
        retry_stats: Dict
    ) -> bool:
        """
        Send notification about a blocker requiring intervention.

        Args:
            session_id: Current session ID
            project_name: Name of the project
            blocker_info: Information about the blocker
            retry_stats: Retry statistics

        Returns:
            True if notification was sent successfully
        """
        if not self.enabled or not self.webhook_url:
            return False

        message = self._format_blocker_message(
            session_id, project_name, blocker_info, retry_stats
        )

        try:
            async with aiohttp.ClientSession() as session:
                # Support different webhook formats
                if "slack.com" in self.webhook_url:
                    # Slack webhook format
                    payload = {"text": message}
                elif "discord.com" in self.webhook_url:
                    # Discord webhook format
                    payload = {"content": message}
                else:
                    # Generic webhook format
                    payload = {
                        "message": message,
                        "session_id": session_id,
                        "project": project_name,
                        "blocker": blocker_info,
                        "stats": retry_stats,
                        "timestamp": datetime.now().isoformat()
                    }

                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status in [200, 201, 204]

        except Exception as e:
            print(f"Failed to send webhook notification: {e}")
            return False

    def _format_blocker_message(
        self,
        session_id: str,
        project_name: str,
        blocker_info: Dict,
        retry_stats: Dict
    ) -> str:
        """Format a human-readable blocker message."""

        message = f"""🚨 **YokeFlow Session Blocked**

**Project:** {project_name}
**Session:** {session_id}
**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Blocker Type:** {blocker_info.get('type', 'unknown')}
**Error:** {blocker_info.get('message', 'No error message')[:200]}

**Retry Statistics:**
• Total retries: {retry_stats.get('total_retries', 0)}
• Max retries on single command: {retry_stats.get('max_retries_on_single_command', 0)}
• Unique errors: {retry_stats.get('unique_errors', 0)}

**Action Required:** Manual intervention needed to resolve infrastructure issue.

View logs: `projects/{project_name}/yokeflow/logs/`
"""
        return message


class InterventionManager:
    """
    Main intervention system that coordinates retry tracking,
    blocker detection, quality pattern detection, and notifications.
    """

    def __init__(self, config: Optional[Dict] = None, environment: str = "docker"):
        """
        Initialize intervention manager.

        Args:
            config: Configuration dictionary
            environment: Running environment (docker/local)
        """
        self.config = config or {}
        self.environment = environment

        # Initialize components
        max_retries = self.config.get("max_retries", 3)
        self.retry_tracker = RetryTracker(max_retries=max_retries)
        self.blocker_detector = BlockerDetector()
        self.notification_service = NotificationService(
            config=self.config.get("notifications", {})
        )

        # Initialize quality detector if quality checking is enabled
        self.quality_detector = None
        if self.config.get("detect_quality_issues", True):
            self.quality_detector = QualityPatternDetector(
                environment=environment,
                config=self.config.get("quality_detection", {})
            )

        # State
        self.session_id: Optional[str] = None
        self.project_name: Optional[str] = None
        self.blocker_documented = False
        self.notification_sent = False
        self.current_task: Optional[Dict] = None

    def set_session_info(self, session_id: str, project_name: str):
        """Set current session information."""
        self.session_id = session_id
        self.project_name = project_name

    def set_current_task(self, task_id: str, task_name: str):
        """
        Set the current task being worked on.

        Args:
            task_id: Task identifier
            task_name: Task name
        """
        self.current_task = {
            "id": task_id,
            "name": task_name
        }

        # Notify quality detector about new task
        if self.quality_detector:
            self.quality_detector.start_task(task_id, task_name)

    async def check_tool_use(
        self,
        tool_name: str,
        tool_input: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        Check a tool use for retry loops and quality issues.

        Args:
            tool_name: Name of the tool
            tool_input: Tool input parameters

        Returns:
            Tuple of (should_block, reason)
        """
        # Track the command for retry loops
        is_blocked, reason = self.retry_tracker.track_command(tool_name, tool_input)

        # Check for quality issues in tool usage
        if self.quality_detector and not is_blocked:
            quality_blocked, quality_reason = self.quality_detector.track_tool_use(
                tool_name, tool_input, self.environment
            )
            if quality_blocked:
                is_blocked = True
                reason = quality_reason

        # Track verification attempts if this is a verification tool
        if self.quality_detector and self.current_task:
            if "browser" in tool_name.lower() or "agent-browser" in tool_name.lower():
                # This is a browser verification
                self.quality_detector.track_verification_attempt(
                    self.current_task["id"],
                    "browser",
                    True,  # Will be updated if it fails
                    None
                )
            elif tool_name in ["bash", "Bash", "mcp__task-manager__bash_docker"]:
                command = tool_input.get("command", "")
                # Check if this is a test command
                if any(kw in command for kw in ["npm test", "pytest", "jest", "mocha", "curl"]):
                    verification_method = "api_test" if "curl" in command else "unit_test"
                    self.quality_detector.track_verification_attempt(
                        self.current_task["id"],
                        verification_method,
                        True,  # Will be updated if it fails
                        None
                    )

        if is_blocked and not self.notification_sent:
            # Send notification
            await self._send_intervention_notification(reason)
            self.notification_sent = True

        return is_blocked, reason

    async def check_tool_error(
        self,
        error_message: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check a tool error for blockers.

        Args:
            error_message: The error message

        Returns:
            Tuple of (should_block, reason)
        """
        # Check for retry loops on errors
        is_retry_blocked, retry_reason = self.retry_tracker.track_error(error_message)

        # Check for critical blockers
        is_critical_blocker, blocker_info = self.blocker_detector.check_for_blocker(
            error_message
        )

        if is_critical_blocker and not self.notification_sent:
            # Send notification for critical blocker
            await self._send_intervention_notification(
                f"Critical blocker: {blocker_info['type']}"
            )
            self.notification_sent = True
            return True, f"Critical infrastructure error: {blocker_info['type']}"

        if is_retry_blocked:
            return True, retry_reason

        return False, None

    async def _send_intervention_notification(self, reason: str):
        """Send intervention notification."""
        if not self.session_id or not self.project_name:
            return

        blocker_info = {
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }

        retry_stats = self.retry_tracker.get_stats()

        await self.notification_service.send_blocker_notification(
            self.session_id,
            self.project_name,
            blocker_info,
            retry_stats
        )

    def document_blocker(self, project_dir: Path, task_info: Dict, reason: str):
        """
        Document a blocker in yokeflow/agent-progress.md.

        Args:
            project_dir: Project directory path
            task_info: Information about the current task
            reason: Reason for the blocker
        """
        if self.blocker_documented:
            return

        yokeflow_dir = project_dir / "yokeflow"
        yokeflow_dir.mkdir(exist_ok=True)
        progress_file = yokeflow_dir / "agent-progress.md"

        blocker_content = f"""

## BLOCKER - Session {self.session_id} - {datetime.now().isoformat()}

**Task:** {task_info.get('id', 'Unknown')} - {task_info.get('name', 'Unknown task')}
**Issue:** {reason}
**Root Cause:** Automated retry limit exceeded or critical infrastructure error detected

**Retry Statistics:**
{json.dumps(self.retry_tracker.get_stats(), indent=2)}

**Detected Blockers:**
{json.dumps(self.blocker_detector.get_blockers(), indent=2)}

**Requires:**
- [ ] Human intervention to resolve infrastructure issue
- [ ] Review logs in `logs/` directory
- [ ] Fix root cause before resuming

**Impact:** Session halted to prevent infinite loops and resource waste
"""

        try:
            with open(progress_file, "a") as f:
                f.write(blocker_content)
            self.blocker_documented = True
        except Exception as e:
            print(f"Failed to document blocker: {e}")

    async def check_task_completion(
        self,
        task_id: str,
        marking_complete: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a task can be marked as complete based on quality standards.

        Args:
            task_id: Task identifier
            marking_complete: Whether the task is being marked complete

        Returns:
            Tuple of (should_block, reason)
        """
        if not self.quality_detector:
            return False, None

        # Check task completion quality
        is_blocked, reason = self.quality_detector.check_task_completion_quality(
            task_id, marking_complete
        )

        if is_blocked:
            # Check if we should intervene
            should_intervene, intervention_reason = self.quality_detector.should_intervene()
            if should_intervene and not self.notification_sent:
                await self._send_intervention_notification(intervention_reason)
                self.notification_sent = True

        return is_blocked, reason

    def get_summary(self) -> Dict:
        """Get intervention summary including quality metrics."""
        summary = {
            "retry_stats": self.retry_tracker.get_stats(),
            "blockers": self.blocker_detector.get_blockers(),
            "notification_sent": self.notification_sent,
            "blocker_documented": self.blocker_documented
        }

        # Add quality summary if available
        if self.quality_detector:
            summary["quality"] = self.quality_detector.get_quality_summary()

        return summary