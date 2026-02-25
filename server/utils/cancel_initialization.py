"""
Initialization Cancellation Module
===================================

Handles complete cleanup when initialization is cancelled, ensuring
the project can be cleanly re-initialized from session 0.

This fixes the issue where cancelled initializations leave behind:
- Session records in the database
- Log files in the project directory
- Incorrect session numbering for the next initialization
"""

import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from uuid import UUID
import logging

from server.database.connection import DatabaseManager

logger = logging.getLogger(__name__)


class InitializationCanceller:
    """Handles complete cleanup when initialization is cancelled."""

    def __init__(self, project_id: UUID, project_path: Optional[Path] = None):
        """
        Initialize the canceller.

        Args:
            project_id: UUID of the project
            project_path: Optional path to project directory (for log cleanup)
        """
        self.project_id = project_id
        self.project_path = Path(project_path) if project_path else None

    async def cancel_and_cleanup(self, session_id: UUID) -> Dict[str, Any]:
        """
        Perform complete cancellation and cleanup.

        This method:
        1. Marks the session as cancelled
        2. Removes all epics, tasks, and tests
        3. Removes the initialization session from the database
        4. Removes initialization log files
        5. Resets any project metadata

        Args:
            session_id: UUID of the initialization session to cancel

        Returns:
            Dict with cleanup results and any errors
        """
        results = {
            'success': True,
            'session_cleaned': False,
            'epics_deleted': 0,
            'logs_cleaned': False,
            'errors': []
        }

        try:
            async with DatabaseManager() as db:
                async with db.acquire() as conn:
                    # 1. Get session details for logging
                    session = await conn.fetchrow(
                        "SELECT * FROM sessions WHERE id = $1",
                        session_id
                    )

                    if not session:
                        results['errors'].append(f"Session {session_id} not found")
                        results['success'] = False
                        return results

                    session_number = session.get('session_number', 0)

                    # 2. Delete all epics (cascades to tasks and tests)
                    epics = await conn.fetch(
                        "SELECT id FROM epics WHERE project_id = $1",
                        self.project_id
                    )

                    for epic in epics:
                        await conn.execute(
                            "DELETE FROM epics WHERE id = $1",
                            epic['id']
                        )

                    results['epics_deleted'] = len(epics)
                    logger.info(f"Deleted {len(epics)} epics for project {self.project_id}")

                    # 3. Delete deep reviews for this session (if any)
                    await conn.execute(
                        "DELETE FROM session_deep_reviews WHERE session_id = $1",
                        session_id
                    )

                    # 4. Delete the initialization session record
                    # This is important to reset session numbering
                    await conn.execute(
                        "DELETE FROM sessions WHERE id = $1",
                        session_id
                    )
                    results['session_cleaned'] = True
                    logger.info(f"Deleted session record {session_id}")

                    # 6. Reset project initialization status if needed
                    await conn.execute(
                        """
                        UPDATE projects
                        SET initialized_at = NULL
                        WHERE id = $1 AND initialized_at IS NOT NULL
                        """,
                        self.project_id
                    )

                    # 7. Clean up log files if project path provided
                    if self.project_path:
                        logs_cleaned, log_error = self._cleanup_logs(session_number)
                        results['logs_cleaned'] = logs_cleaned
                        if log_error:
                            results['errors'].append(log_error)

        except Exception as e:
            logger.error(f"Error during initialization cancellation: {e}")
            results['success'] = False
            results['errors'].append(str(e))

        return results

    def _cleanup_logs(self, session_number: int) -> Tuple[bool, Optional[str]]:
        """
        Remove initialization session log files.

        Args:
            session_number: The session number to clean up

        Returns:
            Tuple of (success, error_message)
        """
        try:
            from server.utils.project_paths import resolve_logs_dir
            logs_dir = resolve_logs_dir(self.project_path)

            if not logs_dir.exists():
                return True, None

            # Find log files for this session
            # Format: session_NNN_TIMESTAMP.jsonl and session_NNN_TIMESTAMP.txt
            session_prefix = f"session_{session_number:03d}_"

            removed_files = []
            for log_file in logs_dir.glob(f"{session_prefix}*"):
                if log_file.is_file():
                    log_file.unlink()
                    removed_files.append(log_file.name)

            if removed_files:
                logger.info(f"Removed {len(removed_files)} log files: {removed_files}")

            # Also check for any orphaned session 1 logs if this was session 0
            # (in case of the bug where session 1 was also marked as initializer)
            if session_number == 0:
                session1_files = list(logs_dir.glob("session_001_*"))
                for log_file in session1_files:
                    # Check if it's an initializer session by reading first few lines
                    if self._is_initializer_log(log_file):
                        log_file.unlink()
                        removed_files.append(log_file.name)
                        logger.info(f"Removed orphaned initializer log: {log_file.name}")

            return True, None

        except Exception as e:
            error_msg = f"Failed to clean up log files: {e}"
            logger.error(error_msg)
            return False, error_msg

    def _is_initializer_log(self, log_file: Path) -> bool:
        """
        Check if a log file is from an initializer session.

        Args:
            log_file: Path to the log file

        Returns:
            True if this is an initializer session log
        """
        try:
            # For JSONL files, check for session_type in first few lines
            if log_file.suffix == '.jsonl':
                with open(log_file, 'r') as f:
                    for _ in range(10):  # Check first 10 lines
                        line = f.readline()
                        if not line:
                            break
                        if '"session_type": "initializer"' in line:
                            return True
            return False
        except Exception:
            return False


async def cancel_initialization_complete(
    project_id: UUID,
    session_id: UUID,
    project_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Convenience function to perform complete initialization cancellation.

    Args:
        project_id: UUID of the project
        session_id: UUID of the initialization session
        project_path: Optional path to project directory

    Returns:
        Dict with cleanup results
    """
    canceller = InitializationCanceller(project_id, project_path)
    return await canceller.cancel_and_cleanup(session_id)