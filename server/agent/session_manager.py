"""
Enhanced Session Manager with Pause/Resume Capability
======================================================

Manages session lifecycle including pausing, resuming, and state preservation.
"""

import json
import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime
from pathlib import Path
from uuid import UUID

from server.database.connection import DatabaseManager
from server.agent.intervention import InterventionManager


class PausedSessionManager:
    """Manages paused sessions and their state."""

    def __init__(self):
        """Initialize the paused session manager."""
        self.paused_sessions: Dict[str, Dict] = {}

    async def pause_session(
        self,
        session_id: str,
        project_id: str,
        reason: str,
        pause_type: str,
        intervention_manager: Optional[InterventionManager] = None,
        current_task: Optional[Dict] = None,
        message_count: int = 0
    ) -> str:
        """
        Pause a session and save its state to database.

        Args:
            session_id: UUID of the session
            project_id: UUID of the project
            reason: Reason for pausing
            pause_type: Type of pause (retry_limit, critical_error, manual, timeout)
            intervention_manager: Optional intervention manager with stats
            current_task: Current task being worked on
            message_count: Number of messages in current session

        Returns:
            UUID of the paused session record
        """
        # Gather intervention stats if available
        blocker_info = {}
        retry_stats = {}
        error_messages = []

        if intervention_manager:
            summary = intervention_manager.get_summary()
            retry_stats = summary.get("retry_stats", {})
            blockers = summary.get("blockers", [])
            if blockers:
                blocker_info = blockers[-1] if isinstance(blockers, list) else blockers
                # Extract error messages from blockers
                error_messages = [b.get("message", "") for b in blockers if b.get("message")]

        # Extract task info
        current_task_id = current_task.get("id") if current_task else None
        current_task_description = current_task.get("name") if current_task else None

        # Save to database
        async with DatabaseManager() as db:
            paused_session_id = await db.pause_session(
                session_id=UUID(session_id),
                project_id=UUID(project_id),
                reason=reason,
                pause_type=pause_type,
                blocker_info=blocker_info,
                retry_stats=retry_stats,
                current_task_id=current_task_id,
                current_task_description=current_task_description,
                message_count=message_count,
                error_messages=error_messages if error_messages else None
            )

        print(f"[INTERVENTION] Session paused - ID: {paused_session_id}")
        print(f"  Reason: {reason}")
        print(f"  Type: {pause_type}")
        if current_task:
            print(f"  Task: {current_task.get('name', 'Unknown')}")

        return str(paused_session_id)

    async def resume_session(
        self,
        paused_session_id: str,
        resolved_by: str = "system",
        resolution_notes: Optional[str] = None
    ) -> Dict:
        """
        Resume a paused session from database.

        Args:
            paused_session_id: UUID of the paused session
            resolved_by: Who resolved the issue
            resolution_notes: Notes about the resolution

        Returns:
            Session information for resuming
        """
        print(f"[INTERVENTION] Attempting to resume session - ID: {paused_session_id}")
        print(f"  Resolved by: {resolved_by}")
        if resolution_notes:
            print(f"  Notes: {resolution_notes}")

        async with DatabaseManager() as db:
            # Get the paused session details before resuming
            paused_session = await db.get_paused_session(UUID(paused_session_id))

            if not paused_session:
                raise ValueError(f"Paused session not found: {paused_session_id}")

            if paused_session.get("resolved"):
                raise ValueError(f"Session already resolved: {paused_session_id}")

            # Get project details
            project = await db.get_project(paused_session["project_id"])
            if not project:
                raise ValueError(f"Project not found: {paused_session['project_id']}")

            # Generate resume prompt
            resume_prompt = self._generate_resume_prompt(paused_session, resolution_notes)

            # Set resume information
            await db.set_pause_resume_prompt(
                paused_session_id=UUID(paused_session_id),
                resume_prompt=resume_prompt,
                can_auto_resume=False,  # Require manual resume for safety
                resume_context={"resolved_by": resolved_by, "resolution_notes": resolution_notes}
            )

            # Mark as resumed in database
            success = await db.resume_session(
                paused_session_id=UUID(paused_session_id),
                resolved_by=resolved_by,
                resolution_notes=resolution_notes
            )

            if not success:
                raise RuntimeError(f"Failed to resume session: {paused_session_id}")

        # Return context for resuming
        return {
            "session_id": str(paused_session["session_id"]),
            "project_id": str(paused_session["project_id"]),
            "project_name": project.get("name", "Unknown"),
            "project_path": project.get("local_path", ""),
            "current_task_id": paused_session.get("current_task_id"),
            "current_task_description": paused_session.get("current_task_description"),
            "pause_reason": paused_session.get("pause_reason"),
            "pause_type": paused_session.get("pause_type"),
            "resolution_notes": resolution_notes,
            "resume_prompt": resume_prompt
        }

    def _generate_resume_prompt(
        self,
        paused_session: Dict,
        resolution_notes: Optional[str]
    ) -> str:
        """Generate a prompt for resuming the session."""
        prompt_parts = [
            "## Session Resume",
            f"This session was paused due to: {paused_session['pause_reason']}",
        ]

        if resolution_notes:
            prompt_parts.append(f"\n**Resolution:** {resolution_notes}")

        if paused_session["current_task_description"]:
            prompt_parts.append(
                f"\n**Current Task:** {paused_session['current_task_description']}"
            )

        # Add blocker information if available
        blocker_info = paused_session.get("blocker_info", {})
        if blocker_info:
            prompt_parts.append(f"\n**Previous Blocker:** {blocker_info.get('type', 'Unknown')}")

        prompt_parts.extend([
            "\n## Instructions",
            "1. Verify the issue has been resolved",
            "2. Continue with the current task if not completed",
            "3. If still blocked, document the issue and move to next task",
        ])

        return "\n".join(prompt_parts)

    async def get_active_pauses(self, project_id: Optional[str] = None) -> List[Dict]:
        """
        Get all active (unresolved) paused sessions from database.

        Args:
            project_id: Optional project ID to filter by

        Returns:
            List of active paused sessions with project info
        """
        async with DatabaseManager() as db:
            project_uuid = UUID(project_id) if project_id else None
            return await db.get_active_pauses(project_id=project_uuid)

    async def get_intervention_history(
        self,
        project_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get history of resolved interventions from database.

        Args:
            project_id: Optional project ID to filter by
            limit: Maximum number of records to return

        Returns:
            List of resolved interventions with resolution details
        """
        async with DatabaseManager() as db:
            project_uuid = UUID(project_id) if project_id else None
            return await db.get_intervention_history(project_id=project_uuid, limit=limit)

    async def _log_action(
        self,
        paused_session_id: str,
        action_type: str,
        action_status: str,
        action_details: Dict,
        result_message: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """
        Log an intervention action to database.

        Args:
            paused_session_id: UUID of the paused session
            action_type: Type of action
            action_status: Status of action
            action_details: Details about the action
            result_message: Optional result message
            error_message: Optional error message
        """
        print(f"[INTERVENTION ACTION] {action_type}: {action_status}")
        if action_details:
            print(f"  Details: {action_details}")

        async with DatabaseManager() as db:
            await db.log_intervention_action(
                paused_session_id=UUID(paused_session_id),
                action_type=action_type,
                action_status=action_status,
                action_details=action_details,
                result_message=result_message,
                error_message=error_message
            )

    async def can_auto_resume(self, paused_session_id: str) -> bool:
        """
        Check if a paused session can be automatically resumed.

        Args:
            paused_session_id: UUID of the paused session

        Returns:
            True if can auto-resume
        """
        async with DatabaseManager() as db:
            paused_session = await db.get_paused_session(UUID(paused_session_id))
            if not paused_session or paused_session.get("resolved"):
                return False
            return paused_session.get("can_auto_resume", False)


class AutoRecoveryManager:
    """Manages automatic recovery actions for common issues."""

    def __init__(self):
        """Initialize auto-recovery manager."""
        self.recovery_actions = {
            "port_conflict": self._recover_port_conflict,
            "redis_not_running": self._recover_redis,
            "database_connection_failed": self._recover_database,
            "module_not_found": self._recover_missing_module,
        }

    async def attempt_recovery(
        self,
        blocker_type: str,
        project_path: Path,
        details: Dict
    ) -> tuple[bool, str]:
        """
        Attempt automatic recovery for a blocker.

        Args:
            blocker_type: Type of blocker
            project_path: Path to project
            details: Additional details about the blocker

        Returns:
            Tuple of (success, message)
        """
        if blocker_type in self.recovery_actions:
            recovery_func = self.recovery_actions[blocker_type]
            return await recovery_func(project_path, details)

        return False, f"No auto-recovery available for {blocker_type}"

    async def _recover_port_conflict(
        self,
        project_path: Path,
        details: Dict
    ) -> tuple[bool, str]:
        """Recover from port conflict by killing process on port."""
        import subprocess

        port = details.get("port", 3001)

        try:
            # Find and kill process on port
            cmd = f"lsof -ti:{port} | xargs kill -9"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return True, f"Killed process on port {port}"
            else:
                return False, f"No process found on port {port}"

        except Exception as e:
            return False, f"Failed to clear port {port}: {e}"

    async def _recover_redis(
        self,
        project_path: Path,
        details: Dict
    ) -> tuple[bool, str]:
        """Recover from Redis not running by starting it."""
        import subprocess

        try:
            # Try to start Redis
            cmd = "redis-server --daemonize yes"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Verify Redis is running
                verify_cmd = "redis-cli ping"
                verify_result = subprocess.run(
                    verify_cmd,
                    shell=True,
                    capture_output=True,
                    text=True
                )

                if "PONG" in verify_result.stdout:
                    return True, "Redis started successfully"

            return False, "Failed to start Redis"

        except Exception as e:
            return False, f"Failed to start Redis: {e}"

    async def _recover_database(
        self,
        project_path: Path,
        details: Dict
    ) -> tuple[bool, str]:
        """Recover from database connection failure."""
        # This is more complex and usually requires manual intervention
        # We can try to restart PostgreSQL service if running locally

        import subprocess

        try:
            # Try to start PostgreSQL (macOS)
            cmds = [
                "brew services start postgresql",  # macOS with Homebrew
                "sudo service postgresql start",   # Linux
                "pg_ctl start",                    # Direct pg_ctl
            ]

            for cmd in cmds:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    return True, f"Database service started with: {cmd}"

            return False, "Could not start database service automatically"

        except Exception as e:
            return False, f"Failed to start database: {e}"

    async def _recover_missing_module(
        self,
        project_path: Path,
        details: Dict
    ) -> tuple[bool, str]:
        """Recover from missing module by installing it."""
        import subprocess

        module_name = details.get("module", "")

        if not module_name:
            return False, "Module name not identified"

        try:
            # Determine package manager
            if (project_path / "package.json").exists():
                # Node.js project
                if (project_path / "pnpm-lock.yaml").exists():
                    cmd = f"cd {project_path} && pnpm add {module_name}"
                elif (project_path / "yarn.lock").exists():
                    cmd = f"cd {project_path} && yarn add {module_name}"
                else:
                    cmd = f"cd {project_path} && npm install {module_name}"

            elif (project_path / "requirements.txt").exists():
                # Python project
                cmd = f"cd {project_path} && pip install {module_name}"

            else:
                return False, "Could not determine package manager"

            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return True, f"Installed module: {module_name}"
            else:
                return False, f"Failed to install {module_name}: {result.stderr}"

        except Exception as e:
            return False, f"Failed to install module: {e}"