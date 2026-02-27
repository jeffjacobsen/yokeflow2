"""
Agent Orchestrator
========================================

Centralized orchestration layer for managing autonomous agent sessions.

This module provides a clean interface for:
- Creating projects
- Starting/stopping agent sessions
- Querying session status
- Managing the agent lifecycle

Design Philosophy:
- Independent (can be called from API or tests)
- Uses PostgreSQL database for all data access
- Async-first for scalability
- Foundation for future job queue integration (Celery/Redis)
"""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Awaitable, TYPE_CHECKING
from datetime import datetime
from uuid import UUID
import os

import asyncpg

from server.client.claude import create_client
from server.database.connection import get_db, DatabaseManager, is_postgresql_configured
from server.agent.models import SessionStatus, SessionType, SessionInfo
from server.quality.integration import QualityIntegration
from server.utils.logging import get_logger, setup_structured_logging

if TYPE_CHECKING:
    from server.database.operations import TaskDatabase
from server.client.prompts import (
    get_initializer_prompt,
    get_coding_prompt,
    get_brownfield_coding_preamble,
    copy_spec_to_project,
)
from server.agent.codebase_import import CodebaseImporter
from server.utils.observability import SessionLogger, QuietOutputFilter, create_session_logger
from server.agent.agent import run_agent_session, SessionManager
from server.utils.config import Config
# Verification system removed - replaced by test execution in Phase 2

# Initialize structured logging if not already done (for CLI usage)
if not any(isinstance(h.formatter, type(None)) for h in get_logger(__name__).handlers):
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_format = os.getenv('LOG_FORMAT', 'dev')
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    setup_structured_logging(
        level=log_level,
        format_type=log_format,
        log_file=logs_dir / "yokeflow.log"
    )

logger = get_logger(__name__)

# Re-export models for backward compatibility
__all__ = ['AgentOrchestrator', 'SessionInfo', 'SessionStatus', 'SessionType']


class AgentOrchestrator:
    """
    Orchestrates autonomous agent sessions using PostgreSQL.

    Provides a high-level interface for managing agent lifecycle via the API.
    All sessions raise exceptions on interrupt rather than calling sys.exit().
    """

    def __init__(self, verbose: bool = False, event_callback=None):
        """
        Initialize the orchestrator.

        Args:
            verbose: If True, show detailed output during sessions
            event_callback: Optional async callback function for session events.
                          Called with (project_id, event_type, data) parameters.
        """
        self.verbose = verbose
        self.event_callback = event_callback
        self.config = Config.load_default()

        # Quality system integration
        self.quality = QualityIntegration(self.config, event_callback)

        # Session managers for graceful shutdown
        self.session_managers: Dict[str, SessionManager] = {}

        # Session control flags (per-project)
        self.stop_after_current: Dict[str, bool] = {}  # project_id -> flag

    # =========================================================================
    # Project Operations
    # =========================================================================

    async def create_project(
        self,
        project_name: str,
        spec_source: Optional[Path] = None,
        spec_content: Optional[str] = None,
        user_id: Optional[UUID] = None,
        force: bool = False,
        initializer_model: Optional[str] = None,
        coding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new project from a specification.

        Args:
            project_name: Name for the project (must be unique)
            spec_source: Path to spec file or folder (optional)
            spec_content: Spec content as string (optional)
            user_id: User ID (optional, for future multi-user support)
            force: If True, overwrite existing project
            initializer_model: Model for initialization session (optional)
            coding_model: Model for coding sessions (optional)

        Returns:
            Dict with project info: {"project_id": UUID, "name": str, ...}

        Raises:
            ValueError: If project already exists and force=False
        """
        async with DatabaseManager() as db:
            # Check if project exists
            existing = await db.get_project_by_name(project_name)
            if existing and not force:
                raise ValueError(
                    f"A project named '{project_name}' already exists. Please choose a different name or delete the existing project first."
                )

            if existing and force:
                # Delete existing project before creating new one
                await db.delete_project(existing['id'])

            # Determine spec path/content
            spec_path = str(spec_source) if spec_source else None

            # If spec_source is provided, read its content if not already provided
            if spec_source and not spec_content:
                spec_source = Path(spec_source)
                if spec_source.is_file():
                    spec_content = spec_source.read_text()
                elif spec_source.is_dir():
                    # For directories, concatenate all relevant files
                    spec_files = []
                    for pattern in ["*.md", "*.txt", "README*"]:
                        spec_files.extend(spec_source.glob(pattern))
                    spec_content = "\n\n".join(
                        f"# {f.name}\n\n{f.read_text()}"
                        for f in sorted(spec_files)
                    )

            # Create project directory
            projects_dir = Path(self.config.project.default_projects_dir)
            project_path = projects_dir / project_name
            project_path.mkdir(parents=True, exist_ok=True)

            # Copy spec files to project's yokeflow/specs/ directory
            from server.utils.project_paths import get_specs_dir
            if spec_source:
                spec_rel_path = copy_spec_to_project(project_path, spec_source)
            elif spec_content:
                # Write spec_content to yokeflow/specs/spec.md if no source file provided
                specs_dir = get_specs_dir(project_path)
                specs_dir.mkdir(parents=True, exist_ok=True)
                (specs_dir / "spec.md").write_text(spec_content)
                spec_rel_path = "yokeflow/specs/spec.md"
            else:
                spec_rel_path = ""

            # Create project in database
            project = await db.create_project(
                name=project_name,
                spec_file_path=spec_rel_path,
                spec_content=spec_content,
                user_id=user_id,
            )

            # Copy agent skills (commands/, skills/) so Claude Code discovers them
            from server.client.claude import copy_agent_skills
            copy_agent_skills(project_path)

            # Update project with local_path and initial settings
            await db.update_project(project['id'], local_path=str(project_path))
            project['local_path'] = str(project_path)

            # Set initial project settings
            settings = {
                'max_iterations': None,  # None = unlimited (auto-continue)
            }
            if initializer_model:
                settings['initializer_model'] = initializer_model
            if coding_model:
                settings['coding_model'] = coding_model

            await db.update_project_settings(project['id'], settings)

            # Optional: Run spec pre-analysis if configured
            if self.config.spec_analysis.enabled and spec_content:
                try:
                    from server.generation.spec_analyzer import analyze_spec
                    logger.info(f"Running spec pre-analysis for project '{project_name}'...")
                    analysis = await analyze_spec(
                        spec_content=spec_content,
                        model=self.config.spec_analysis.model,
                    )
                    # Store in codebase_analysis column (unused by greenfield projects)
                    await db.update_codebase_analysis(project['id'], analysis)
                    logger.info(f"Spec pre-analysis stored for project '{project_name}'")
                except Exception as e:
                    logger.warning(f"Spec pre-analysis failed (non-fatal): {e}")

            return project

    async def create_brownfield_project(
        self,
        project_name: str,
        source_url: Optional[str] = None,
        source_path: Optional[str] = None,
        branch: str = "main",
        change_spec_content: Optional[str] = None,
        user_id: Optional[UUID] = None,
        initializer_model: Optional[str] = None,
        coding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a brownfield project from an existing codebase.

        The codebase is imported into projects/<project_name>/, analyzed,
        and prepared for the brownfield initializer session which creates
        epics/tasks scoped to the requested changes.

        Args:
            project_name: Name for the project (must be unique)
            source_url: Git repository URL to clone from
            source_path: Local filesystem path to copy from
            branch: Git branch to import (default: main)
            change_spec_content: Description of changes to make
            user_id: User ID (optional)
            initializer_model: Model for initialization (optional)
            coding_model: Model for coding sessions (optional)

        Returns:
            Dict with project info

        Raises:
            ValueError: If project exists, no source provided, or import fails
        """
        import shutil

        async with DatabaseManager() as db:
            # Check if project exists
            existing = await db.get_project_by_name(project_name)
            if existing:
                raise ValueError(
                    f"A project named '{project_name}' already exists. "
                    "Please choose a different name or delete the existing project first."
                )

            # Create project directory
            projects_dir = Path(self.config.project.default_projects_dir)
            project_path = projects_dir / project_name
            project_path.mkdir(parents=True, exist_ok=True)

            # Import codebase
            importer = CodebaseImporter()
            if source_url:
                import_result = await importer.import_from_github(
                    source_url, branch, project_path
                )
            elif source_path:
                import_result = await importer.import_from_local(
                    Path(source_path), project_path
                )
            else:
                raise ValueError("Either source_url or source_path must be provided")

            if not import_result.success:
                # Clean up on failure
                shutil.rmtree(project_path, ignore_errors=True)
                raise ValueError(f"Import failed: {import_result.error}")

            # Analyze codebase
            analysis = await importer.analyze_codebase(project_path)

            # Write change spec to yokeflow/specs/
            from server.utils.project_paths import get_specs_dir
            if change_spec_content:
                specs_dir = get_specs_dir(project_path)
                specs_dir.mkdir(parents=True, exist_ok=True)
                (specs_dir / "change_spec.md").write_text(change_spec_content)

            # Set up git feature branch
            feature_branch = await importer.setup_brownfield_git(
                project_path,
                branch_name=f"{self.config.brownfield.default_feature_branch_prefix}modifications"
            )

            # Create project in database
            project = await db.create_project(
                name=project_name,
                spec_file_path="yokeflow/specs/change_spec.md",
                spec_content=change_spec_content,
                user_id=user_id,
                project_type='brownfield',
                source_commit_sha=import_result.commit_sha,
                codebase_analysis=analysis.to_dict(),
            )

            # Copy agent skills (commands/, skills/) so Claude Code discovers them
            from server.client.claude import copy_agent_skills
            copy_agent_skills(project_path)

            # Update with local_path
            await db.update_project(project['id'], local_path=str(project_path))
            project['local_path'] = str(project_path)

            # Store github_repo_url and github_branch for brownfield tracking
            if source_url:
                await db.update_project(
                    project['id'],
                    github_repo_url=source_url,
                    github_branch=branch,
                )

            # Set project settings
            settings = {
                'project_type': 'brownfield',
                'feature_branch': feature_branch,
                'max_iterations': None,
            }
            if initializer_model:
                settings['initializer_model'] = initializer_model
            if coding_model:
                settings['coding_model'] = coding_model

            await db.update_project_settings(project['id'], settings)

            logger.info(
                f"Created brownfield project '{project_name}' from "
                f"{'GitHub' if source_url else 'local'} source "
                f"({import_result.file_count} files, "
                f"{', '.join(analysis.languages[:3])} detected)"
            )

            return project

    async def rollback_brownfield_changes(self, project_id: UUID) -> bool:
        """
        Reset a brownfield project to its original imported state.

        Checks out the source branch, deletes the feature branch,
        and removes all epics/tasks/tests from the database.

        Args:
            project_id: UUID of the brownfield project

        Returns:
            True if rollback succeeded

        Raises:
            ValueError: If project not found or not a brownfield project
        """
        import subprocess

        async with DatabaseManager() as db:
            project = await db.get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            project_type = project.get('project_type', 'greenfield')
            if project_type != 'brownfield':
                raise ValueError("Rollback is only available for brownfield projects")

            project_path = None
            # Get local_path from metadata
            metadata = project.get('metadata', {})
            if isinstance(metadata, str):
                import json
                metadata = json.loads(metadata)
            local_path = metadata.get('local_path')
            if local_path:
                project_path = Path(local_path)

            if not project_path or not project_path.exists():
                raise ValueError(f"Project directory not found")

            # Get source branch
            source_branch = project.get('github_branch', 'main')

            # Reset git to source branch
            result = subprocess.run(
                ['git', 'checkout', source_branch],
                cwd=str(project_path), capture_output=True, text=True
            )
            if result.returncode != 0:
                raise ValueError(f"Git checkout failed: {result.stderr}")

            # Delete feature branch
            feature_prefix = self.config.brownfield.default_feature_branch_prefix
            subprocess.run(
                ['git', 'branch', '-D', f'{feature_prefix}modifications'],
                cwd=str(project_path), capture_output=True, text=True
            )

            # Reset task/epic statuses in DB
            async with db.acquire() as conn:
                await conn.execute(
                    """DELETE FROM tests WHERE task_id IN
                       (SELECT id FROM tasks WHERE epic_id IN
                        (SELECT id FROM epics WHERE project_id = $1))""",
                    project_id
                )
                await conn.execute(
                    """DELETE FROM tasks WHERE epic_id IN
                       (SELECT id FROM epics WHERE project_id = $1)""",
                    project_id
                )
                await conn.execute(
                    "DELETE FROM epics WHERE project_id = $1",
                    project_id
                )

            logger.info(f"Rolled back brownfield project {project_id}")
            return True

    async def get_project_info(self, project_id: UUID) -> Dict[str, Any]:
        """
        Get information about a project.

        Args:
            project_id: UUID of the project

        Returns:
            Dict with project info and progress statistics

        Raises:
            ValueError: If project doesn't exist
        """
        async with DatabaseManager() as db:
            project = await db.get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            # Compute local_path from project name
            projects_dir = Path(self.config.project.default_projects_dir)
            project_path = projects_dir / project['name']
            project['local_path'] = str(project_path)

            # Get progress statistics
            progress = await db.get_progress(project_id)
            next_task = await db.get_next_task(project_id)

            # Check for active sessions
            active_session = await db.get_active_session(project_id)
            active_sessions = [active_session] if active_session else []

            # Check environment configuration
            env_file = project_path / ".env" if project_path else None
            env_example = project_path / ".env.example" if project_path else None
            has_env_file = env_file and env_file.exists()
            has_env_example = env_example and env_example.exists()

            # Check if .env.example actually has variables (not just empty file)
            has_env_variables = False
            if has_env_example and env_example:
                try:
                    content = env_example.read_text()
                    # Count non-empty, non-comment lines
                    lines = [line.strip() for line in content.splitlines()]
                    var_lines = [line for line in lines if line and not line.startswith('#')]
                    has_env_variables = len(var_lines) > 0
                except Exception:
                    # If we can't read the file, assume it has variables
                    has_env_variables = True

            # Determine if initialization is complete (Session 1 has created epics/tasks)
            # Handle both old and new field names for compatibility
            total_epics = progress.get("total_epics", 0) or progress.get("epics_total", 0)
            is_initialized = total_epics > 0

            # Determine if env configuration is needed
            # Only flag if .env.example exists AND has actual variables
            needs_env_config = (
                is_initialized and
                has_env_variables and
                not project.get('env_configured', False)
            )

            return {
                **project,
                "is_initialized": is_initialized,
                "progress": progress,
                "next_task": next_task,
                "active_sessions": active_sessions,
                "has_env_file": has_env_file,
                "has_env_example": has_env_example,
                "needs_env_config": needs_env_config,
            }

    async def get_project_by_name(self, project_name: str) -> Optional[Dict[str, Any]]:
        """
        Get project by name.

        Args:
            project_name: Name of the project

        Returns:
            Project dict if found, None otherwise
        """
        async with DatabaseManager() as db:
            project = await db.get_project_by_name(project_name)
            if project:
                return await self.get_project_info(project['id'])
            return None

    async def list_projects(self, user_id: Optional[UUID] = None) -> List[Dict[str, Any]]:
        """
        List all projects.

        Args:
            user_id: Optional user ID to filter projects

        Returns:
            List of project info dicts
        """
        async with DatabaseManager() as db:
            projects = await db.list_projects(user_id=user_id)

            # Enrich with progress info
            enriched = []
            for project in projects:
                try:
                    info = await self.get_project_info(project['id'])
                    enriched.append(info)
                except Exception as e:
                    logger.warning(f"Could not get info for project {project['name']}: {e}")
                    enriched.append(project)

            return enriched

    # =========================================================================
    # Session Operations
    # =========================================================================

    async def start_initialization(
        self,
        project_id: UUID,
        initializer_model: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> SessionInfo:
        """
        Run initialization session (Session 0) for a project.

        This method:
        - Creates the project structure (epics, tasks, tests)
        - Runs init.sh to setup the environment
        - ALWAYS stops after Session 0 completes
        - Does NOT auto-continue to coding sessions

        Args:
            project_id: UUID of the project
            initializer_model: Model to use (defaults to config.models.initializer)
            progress_callback: Optional async callback for real-time progress updates

        Returns:
            SessionInfo for the completed initialization session

        Raises:
            ValueError: If project doesn't exist or already initialized
        """
        async with DatabaseManager() as db:
            # Verify project exists
            project = await db.get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            # Check if already initialized
            epics = await db.list_epics(project_id)
            if len(epics) > 0:
                raise ValueError(
                    f"Project already initialized with {len(epics)} epics. "
                    f"Use start_coding_sessions() instead."
                )

        # Use default model if not provided
        if not initializer_model:
            initializer_model = self.config.models.initializer

        # Run Session 0
        session_info = await self.start_session(
            project_id=project_id,
            initializer_model=initializer_model,
            coding_model=None,  # Not needed for initialization
            max_iterations=None,  # Not applicable
            progress_callback=progress_callback,
        )

        # Notify that Session 0 is complete
        if self.event_callback:
            await self.event_callback(project_id, "session_complete", {
                "session": session_info.to_dict()
            })

        return session_info

    async def start_coding_sessions(
        self,
        project_id: UUID,
        coding_model: Optional[str] = None,
        max_iterations: Optional[int] = 0,  # 0 = unlimited by default
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> SessionInfo:
        """
        Run coding sessions (Session 2+) for a project.

        This method:
        - Verifies initialization is complete
        - Runs multiple sessions with auto-continue
        - Respects max_iterations setting (0/None = unlimited)
        - Respects stop_after_current flag

        Args:
            project_id: UUID of the project
            coding_model: Model to use (defaults to config.models.coding)
            max_iterations: Maximum sessions to run (0 or None = unlimited)
            progress_callback: Optional async callback for real-time progress updates

        Returns:
            SessionInfo for the LAST completed session

        Raises:
            ValueError: If project doesn't exist or not initialized
        """
        async with DatabaseManager() as db:
            # Verify project exists
            project = await db.get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            # Check if project is already complete
            if project.get('completed_at'):
                logger.info(f"✅ Project '{project['name']}' is already complete (completed_at: {project['completed_at']})")
                logger.info("Not starting new coding sessions for completed project.")
                # Return early with a message indicating project is complete
                raise ValueError(
                    f"Project '{project['name']}' is already marked as complete. "
                    f"Completed at: {project['completed_at']}. "
                    "No new sessions will be started."
                )

            # Check if initialization is complete
            epics = await db.list_epics(project_id)
            if len(epics) == 0:
                raise ValueError(
                    "Project not initialized. Run start_initialization() first."
                )

        # Use default model if not provided
        if not coding_model:
            coding_model = self.config.models.coding

        # Normalize max_iterations (0 and None both mean unlimited)
        if max_iterations is None or max_iterations == 0:
            max_iterations = None  # Unlimited

        # Auto-continue loop for coding sessions
        iteration = 0
        last_session = None
        consecutive_degenerate = 0
        MAX_CONSECUTIVE_DEGENERATE = 3

        while True:
            # Check max_iterations
            if max_iterations is not None and iteration >= max_iterations:
                logger.info(f"Reached max_iterations ({max_iterations}). Stopping.")
                break

            # Check stop_after_current flag
            project_id_str = str(project_id)
            if self.stop_after_current.get(project_id_str, False):
                logger.info(f"Stop after current requested. Stopping.")
                # Clear flag
                self.stop_after_current[project_id_str] = False
                break

            # Check if project is already marked as complete
            async with DatabaseManager() as db:
                project = await db.get_project(project_id)
                if project and project.get('completed_at'):
                    logger.info(f"✅ Project already marked as complete (completed_at: {project['completed_at']}). Stopping auto-continue.")
                    # Notify via callback
                    if self.event_callback:
                        await self.event_callback(project_id, "project_already_complete", {
                            "completed_at": str(project['completed_at']),
                            "message": "Project was already marked as complete"
                        })
                    break

                # Also check if all epics are complete (for projects not yet marked complete)
                progress = await db.get_progress(project_id)
                if progress:
                    completed_epics = progress.get('completed_epics', 0)
                    total_epics = progress.get('total_epics', 0)
                    logger.info(f"Auto-continue check: {completed_epics}/{total_epics} epics complete")
                    if completed_epics == total_epics and total_epics > 0:
                        logger.info(f"✅ All epics complete ({completed_epics}/{total_epics}). Stopping auto-continue.")
                        # Notify via callback
                        if self.event_callback:
                            await self.event_callback(project_id, "all_epics_complete", {
                                "completed_epics": completed_epics,
                                "total_epics": total_epics,
                                "completed_tasks": progress.get('completed_tasks', 0),
                                "total_tasks": progress.get('total_tasks', 0)
                            })
                        break

            iteration += 1

            # Delay between sessions (except first)
            if iteration > 1:
                delay = self.config.timing.auto_continue_delay
                logger.info(f"Auto-continue delay: {delay}s before session {iteration}")

                # Notify via callback about delay
                if self.event_callback:
                    await self.event_callback(project_id, "auto_continue_delay", {
                        "delay": delay,
                        "next_iteration": iteration
                    })

                await asyncio.sleep(delay)

            # Run single coding session
            last_session = await self.start_session(
                project_id=project_id,
                initializer_model=None,  # Not needed
                coding_model=coding_model,
                max_iterations=None,  # Don't pass to individual session
                progress_callback=progress_callback
            )

            # Detect degenerate sessions (no useful work -- e.g., rate limit, auth failure)
            tool_count = (last_session.metrics or {}).get("tool_use_count", 0)
            is_degenerate = (
                last_session.status == SessionStatus.COMPLETED
                and tool_count == 0
            )

            if is_degenerate:
                consecutive_degenerate += 1
                logger.warning(
                    f"Degenerate session detected ({consecutive_degenerate}/{MAX_CONSECUTIVE_DEGENERATE}): "
                    f"0 tool calls in session {last_session.session_number}"
                )
                if consecutive_degenerate >= MAX_CONSECUTIVE_DEGENERATE:
                    reason = (
                        f"{MAX_CONSECUTIVE_DEGENERATE} consecutive sessions completed with no work done. "
                        f"The agent may be rate-limited or unable to make progress."
                    )
                    logger.error(f"Circuit breaker triggered: {reason}")

                    # Notify UI via WebSocket
                    if self.event_callback:
                        await self.event_callback(project_id, "session_error", {
                            "error": f"Auto-continue stopped: {reason}",
                            "consecutive_degenerate": consecutive_degenerate,
                        })
                    break
            else:
                consecutive_degenerate = 0  # Reset on any session that did actual work

            # Check if session failed or was blocked
            if last_session.status in [SessionStatus.ERROR, SessionStatus.INTERRUPTED, SessionStatus.BLOCKED]:
                logger.info(f"Session ended with status {last_session.status}. Stopping auto-continue.")
                if last_session.status == SessionStatus.BLOCKED:
                    logger.info("⚠️ Epic test intervention required. Auto-continue stopped.")
                break

            # Check if project is complete (all tasks done)
            async with DatabaseManager() as db:
                progress = await db.get_progress(project_id)
                total_tasks = progress.get('total_tasks', 0)
                completed_tasks = progress.get('completed_tasks', 0)

                if total_tasks > 0 and completed_tasks >= total_tasks:
                    logger.info(f"Project complete! All {total_tasks} tasks done.")

                    # Mark project as complete in database
                    await db.mark_project_complete(project_id)
                    # logger.info("✅ Project marked as complete in database")

                    # Run completion review (code-vs-spec verification)
                    try:
                        await self.quality.run_completion_review(project_id, db)
                    except Exception as e:
                        logger.error(f"Completion review failed (non-blocking): {e}", exc_info=True)

                    # Notify via callback
                    if self.event_callback:
                        await self.event_callback(project_id, "project_complete", {
                            "total_tasks": total_tasks,
                            "completed_tasks": completed_tasks
                        })
                    break

        return last_session

    async def start_session(
        self,
        project_id: UUID,
        initializer_model: Optional[str] = None,
        coding_model: Optional[str] = None,
        max_iterations: Optional[int] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        resume_context: Optional[Dict[str, Any]] = None,
    ) -> SessionInfo:
        """
        Start an agent session for a project.

        This is the main entry point for running the agent. It handles:
        - Determining session type (initializer vs coding)
        - Creating appropriate client and logger
        - Running the session
        - Updating session status

        Args:
            project_id: UUID of the project
            initializer_model: Model to use for initialization (if first session)
            coding_model: Model to use for coding sessions
            max_iterations: Maximum iterations for this invocation (None = unlimited)
            progress_callback: Optional async callback for real-time progress updates.
                             Called with event dict on each tool use/result.

        Returns:
            SessionInfo object with session details

        Raises:
            ValueError: If project doesn't exist or model not provided
        """
        # Cleanup any stale sessions before starting (handles ungraceful shutdowns)
        # This is especially important for CLI usage where the API's periodic cleanup isn't running
        await self.cleanup_stale_sessions()

        async with DatabaseManager() as db:
            # Get project info
            project = await db.get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            # CONCURRENCY CHECK: Prevent creating a new session while another is running
            # This prevents phantom sessions from double-clicks or rapid API calls
            active_session = await db.get_active_session(project_id)
            if active_session:
                raise ValueError(
                    f"Cannot start new session: Session {active_session['session_number']} "
                    f"is already running (started {active_session['started_at']}). "
                    f"Wait for it to complete or stop it first."
                )

            project_name = project['name']
            local_path = project.get('local_path', '')

            # Ensure project path is valid and exists
            if not local_path or local_path == '':
                # Create project directory
                projects_dir = Path(self.config.project.default_projects_dir)
                project_path = projects_dir / project_name
                project_path.mkdir(parents=True, exist_ok=True)

                # Update project with local path
                await db.update_project(project_id, local_path=str(project_path))
            else:
                project_path = Path(local_path)
                if not project_path.exists():
                    project_path.mkdir(parents=True, exist_ok=True)

            # Determine session type
            epics = await db.list_epics(project_id)
            is_initializer = len(epics) == 0

            if is_initializer and not initializer_model:
                raise ValueError("initializer_model required for first session")
            if not is_initializer and not coding_model:
                raise ValueError("coding_model required for coding sessions")

            session_type = SessionType.INITIALIZER if is_initializer else SessionType.CODING
            current_model = initializer_model if is_initializer else coding_model

            # Get next session number
            session_number = await db.get_next_session_number(project_id)

            # Create session in database with unique constraint protection
            try:
                session = await db.create_session(
                    project_id=project_id,
                    session_number=session_number,
                    session_type=session_type.value,
                    model=current_model,
                    max_iterations=max_iterations,
                )
            except asyncpg.UniqueViolationError as e:
                # Race condition: another session with same number was created concurrently
                # This can happen with rapid double-clicks or simultaneous API calls
                raise ValueError(
                    f"Session {session_number} already exists for this project. "
                    f"Another session may have started concurrently. Please try again."
                ) from e

            session_id = session['id']
            session_number = session['session_number']

            # Create session info
            # Note: PostgreSQL returns datetime objects, not strings
            created_at = session['created_at']
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)

            session_info = SessionInfo(
                session_id=str(session_id),
                project_id=str(project_id),
                session_number=session_number,
                session_type=session_type,
                model=current_model,
                status=SessionStatus.PENDING,
                created_at=created_at,
            )

            # Setup signal handlers for graceful shutdown
            session_manager = SessionManager()
            session_manager.setup_handlers()
            self.session_managers[str(session_id)] = session_manager

            try:
                # Create event callback for logger (sync wrapper for async callback)
                def logger_event_callback(event_type: str, data: dict):
                    """Sync wrapper for async event callback."""
                    if self.event_callback:
                        # Add project_id and session_id to event data
                        data['project_id'] = str(project_id)
                        data['session_id'] = str(session_id)
                        # Schedule async callback
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(self.event_callback(project_id, event_type, data))
                        except RuntimeError:
                            # No event loop running, skip
                            pass

                # Create logger with event callback
                session_logger = create_session_logger(
                    project_path, session_number, session_type.value, current_model,
                    event_callback=logger_event_callback
                )
                # Add session and project IDs for intervention system
                session_logger.session_id = str(session_id)
                session_logger.project_id = str(project_id)

                # Register logger with session manager
                session_manager.set_current_logger(session_logger)

                # Update session status
                await db.start_session(session_id)
                session_info.status = SessionStatus.RUNNING
                session_info.started_at = datetime.now()

                # Notify via callback that session has started
                if self.event_callback:
                    await self.event_callback(project_id, "session_started", {
                        "session": session_info.to_dict()
                    })

                # Create client with MCP task-manager
                client = create_client(
                    project_path,
                    current_model,
                    project_id=str(project_id),
                )

                # Get prompt based on session type and project type
                project_type = project.get('project_type', 'greenfield')

                if is_initializer:
                    base_prompt = get_initializer_prompt(
                        project_type=project_type,
                    )
                    # Inject PROJECT_ID at the beginning of the prompt for easy access
                    prompt = f"PROJECT_ID: {project_id}\n\n{base_prompt}"

                    # Inject pre-computed analysis if available
                    import json as json_mod
                    analysis = project.get('codebase_analysis', {})
                    if isinstance(analysis, str):
                        try:
                            analysis = json_mod.loads(analysis)
                        except (json_mod.JSONDecodeError, TypeError):
                            analysis = {}
                    if analysis:
                        analysis_str = json_mod.dumps(analysis, indent=2)
                        if project_type == 'brownfield':
                            prompt += (
                                f"\n\n## Codebase Analysis (Pre-computed)\n"
                                f"```json\n{analysis_str}\n```"
                            )
                        else:
                            prompt += (
                                f"\n\n## Spec Analysis (Pre-computed)\n"
                                f"Use this as a starting point for epic planning. "
                                f"Always verify against the actual spec files.\n"
                                f"```json\n{analysis_str}\n```"
                            )
                elif resume_context:
                    # Include resume context in the prompt
                    base_prompt = get_coding_prompt()
                    resume_prompt = resume_context.get("resume_prompt", "")
                    prompt = f"{base_prompt}\n\n{resume_prompt}"
                else:
                    base_prompt = get_coding_prompt()
                    project_context = (
                        f"PROJECT_ID: {project_id}\n"
                        f"PROJECT_DIR: {project_path.resolve()}\n\n"
                    )
                    if project_type == 'brownfield':
                        preamble = get_brownfield_coding_preamble()
                        prompt = f"{project_context}{preamble}\n\n{base_prompt}"
                    else:
                        prompt = f"{project_context}{base_prompt}"

                # Start heartbeat task to prevent false-positive stale detection
                heartbeat_task = None
                async def send_heartbeats():
                    """Send periodic heartbeats to indicate session is still active."""
                    try:
                        while True:
                            await asyncio.sleep(60)  # Send heartbeat every 60 seconds
                            await db.update_session_heartbeat(session_id)
                            logger.debug(f"Sent heartbeat for session {session_id}")
                    except asyncio.CancelledError:
                        logger.debug("Heartbeat task cancelled")
                        raise

                heartbeat_task = asyncio.create_task(send_heartbeats())

                # DISABLED: Old verification system - replaced by MCP test execution in Phase 2
                # The new workflow uses run_task_tests before update_task_status
                epic_manager = None
                # Verification system removed - function call deleted

                # Old code commented out:
                # if not is_initializer and self.config.verification.enabled:
                #     verification_integration = VerificationIntegration(
                #         project_path=project_path,
                #         db=db,
                #         enabled=self.config.verification.enabled,
                #         auto_retry=self.config.verification.auto_retry,
                #         max_retries=self.config.verification.max_retries
                #     )
                #     set_verification_integration(verification_integration)
                #     logger.info("Task verification system initialized")
                #
                #     # Initialize epic manager for epic validation
                #     from server.verification.epic_manager import EpicManager
                #     epic_manager = EpicManager(db, project_path, self.config)
                #     logger.info("Epic validation system initialized")
                # else:
                #     set_verification_integration(None)

                # Run session with retry logic (no timeout on agent session)
                max_retries = self.config.timing.initialization_max_retries

                for attempt in range(max_retries):
                    try:
                        async with client:
                            # Run session - no timeout for agent sessions
                            if is_initializer:
                                logger.info(f"Starting initialization session")

                                # Notify UI about attempt if retrying
                                if self.event_callback and attempt > 0:
                                    await self.event_callback(project_id, "initialization_retry", {
                                        "attempt": attempt + 1,
                                        "max_retries": max_retries,
                                        "message": f"Retrying initialization (attempt {attempt + 1}/{max_retries})"
                                    })

                                try:
                                    # No timeout for initialization - let it run as long as needed
                                    status, response, session_summary = await run_agent_session(
                                        client, prompt, project_path, logger=session_logger, verbose=self.verbose,
                                        session_manager=session_manager, progress_callback=progress_callback,
                                    )
                                    break  # Success, exit retry loop

                                except Exception as e:
                                    # This shouldn't happen anymore since we removed timeout
                                    # But keep for other potential exceptions
                                    if attempt < max_retries - 1:
                                        logger.warning(f"Initialization failed with error: {e}, retrying...")

                                        # Notify UI about failure and upcoming retry
                                        if self.event_callback:
                                            await self.event_callback(project_id, "initialization_error", {
                                                "attempt": attempt + 1,
                                                "will_retry": True,
                                                "error": str(e),
                                                "message": f"Initialization failed: {e}, retrying..."
                                            })

                                        # Recreate client for retry (the old one might be in a bad state)
                                        client = create_client(
                                            project_path,
                                            current_model,
                                            project_id=str(project_id),
                                        )
                                        await asyncio.sleep(5)  # Brief pause before retry
                                        continue
                                    else:
                                        # Final attempt failed
                                        logger.error(f"Initialization failed after {max_retries} attempts: {e}")

                                        # Notify UI about final failure
                                        if self.event_callback:
                                            await self.event_callback(project_id, "initialization_failed", {
                                                "attempts": max_retries,
                                                "error": str(e),
                                                "message": f"Initialization failed after multiple attempts: {e}"
                                            })

                                        status = "error"
                                        response = f"Initialization failed: {e}"
                                        session_summary = {"status": "error", "error": str(e)}
                                        break
                            else:
                                # For coding sessions, no timeout (they can run for a long time)
                                status, response, session_summary = await run_agent_session(
                                    client, prompt, project_path, logger=session_logger, verbose=self.verbose,
                                    session_manager=session_manager, progress_callback=progress_callback,
                                )
                                break

                    except Exception as e:
                        # Handle other exceptions during session
                        if attempt < max_retries - 1 and is_initializer:
                            logger.warning(f"Session failed with error: {e}, retrying...")
                            await asyncio.sleep(5)
                            # Recreate client for retry
                            client = create_client(
                                project_path,
                                current_model,
                                project_id=str(project_id),
                            )
                            continue
                        else:
                            raise  # Re-raise if final attempt or not initializer

                # Finally block should be outside the for loop
                try:
                    pass  # Nothing to do here
                finally:
                    # Stop heartbeat task
                    if heartbeat_task:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass

                # Store session summary in database
                # This includes all metrics from MetricsCollector plus quality scores
                metrics = session_summary

                # Update session info based on result
                if status == "error":
                    session_info.status = SessionStatus.ERROR
                    session_info.error_message = response
                    await db.end_session(session_id, SessionStatus.ERROR.value, error_message=response, metrics=metrics)
                elif status == "blocked":
                    session_info.status = SessionStatus.BLOCKED
                    session_info.error_message = "Epic test failure - intervention required"
                    await db.end_session(session_id, SessionStatus.BLOCKED.value, error_message="Epic test failure - intervention required", metrics=metrics)
                else:
                    session_info.status = SessionStatus.COMPLETED
                    await db.end_session(session_id, SessionStatus.COMPLETED.value, metrics=metrics)

                session_info.ended_at = datetime.now()
                session_info.metrics = metrics

                # Check for epic completion and run validation if enabled
                if not is_initializer and epic_manager and status != "error":
                    # Check if current task's epic is complete
                    current_task = session_summary.get("current_task")
                    if current_task and current_task.get("epic_id"):
                        epic_id = current_task["epic_id"]
                        should_continue, validation_result = await epic_manager.check_epic_completion(
                            epic_id=epic_id,
                            session_id=session_id
                        )

                        if validation_result:
                            # Log epic validation result
                            if validation_result.get("status") == "passed":
                                #logger.info(f"✅ Epic {epic_id} validation PASSED")
                                metrics["epic_validations_passed"] = 1
                            else:
                                logger.warning(f"⚠️ Epic {epic_id} validation FAILED - rework tasks created")
                                metrics["epic_validations_failed"] = 1
                                metrics["rework_tasks_created"] = validation_result.get("rework_tasks_created", 0)

                # Trigger deep review after every coding session
                if not is_initializer:
                    quality_score = metrics.get("quality_score", 0)
                    await self.quality.maybe_trigger_deep_review(session_id, project_path, quality_score)

                # Test Coverage Analysis: Run after Session 0
                if is_initializer and status != "error":
                    await self.quality.run_test_coverage_analysis(project_id, db)

                # Clear logger from session manager
                session_manager.set_current_logger(None)

            except KeyboardInterrupt:
                # Graceful shutdown was triggered
                session_info.status = SessionStatus.INTERRUPTED
                session_info.ended_at = datetime.now()

                duration = (session_info.ended_at - session_info.started_at).total_seconds() if session_info.started_at else 0
                metrics = {"duration_seconds": duration, "status": "interrupted"}

                await db.end_session(
                    session_id,
                    SessionStatus.INTERRUPTED.value,
                    interruption_reason="User interrupted",
                    metrics=metrics
                )

                # Finalize the logger
                if session_manager.current_logger:
                    try:
                        session_manager.current_logger.finalize("interrupted", "Session interrupted by user")
                    except Exception as e:
                        print(f"Warning: Could not finalize session logs: {e}")

                # Clear logger from session manager
                session_manager.set_current_logger(None)

            except Exception as e:
                # Check if this is an epic test intervention (not a real error)
                error_msg = str(e)

                if "Epic test failure blocked" in error_msg:
                    # This is a blocked session due to epic test failure
                    session_info.status = SessionStatus.BLOCKED
                    session_info.error_message = error_msg
                    session_info.ended_at = datetime.now()

                    duration = (session_info.ended_at - session_info.started_at).total_seconds() if session_info.started_at else 0
                    metrics = session_summary if 'session_summary' in locals() else {"duration_seconds": duration, "status": "blocked"}

                    await db.end_session(
                        session_id,
                        SessionStatus.BLOCKED.value,
                        error_message=error_msg,
                        metrics=metrics
                    )

                    logger.warning(f"Session {session_id} blocked due to epic test failure")

                    # Write blocker info to yokeflow/agent-progress.md
                    await self._write_blocker_info(project_path, session_number, error_msg)

                    # Notify via callback
                    if self.event_callback:
                        await self.event_callback(project_id, "session_blocked", {
                            "session": session_info.to_dict(),
                            "reason": error_msg
                        })
                else:
                    # Unexpected error - existing handling
                    session_info.status = SessionStatus.ERROR
                    session_info.error_message = error_msg
                    session_info.ended_at = datetime.now()

                    duration = (session_info.ended_at - session_info.started_at).total_seconds() if session_info.started_at else 0
                    metrics = {"duration_seconds": duration, "status": "error"}

                    await db.end_session(
                        session_id,
                        SessionStatus.ERROR.value,
                        error_message=error_msg,
                        metrics=metrics
                    )

                    # Log the error for debugging
                    logger.error(f"Session {session_id} failed with error: {e}", exc_info=True)

                    # Don't re-raise - return session_info with ERROR status instead
                    # This allows the API auto-continue loop to detect the error and stop
                    # (line 1247 in api/main.py checks session.status == "error")

            finally:
                # Restore signal handlers
                session_manager.restore_handlers()

                # Remove from session managers
                if str(session_id) in self.session_managers:
                    del self.session_managers[str(session_id)]

            return session_info

    async def stop_session(self, session_id: UUID, reason: str = "User requested stop") -> bool:
        """
        Stop an active session immediately.

        Args:
            session_id: UUID of the session to stop
            reason: Reason for stopping

        Returns:
            True if session was stopped, False if not found or not running
        """
        session_id_str = str(session_id)

        if session_id_str in self.session_managers:
            manager = self.session_managers[session_id_str]
            manager.interrupted = True

            # Update database
            async with DatabaseManager() as db:
                await db.end_session(
                    session_id,
                    SessionStatus.INTERRUPTED.value,
                    interruption_reason=reason
                )

            return True

        return False

    def set_stop_after_current(self, project_id: UUID, stop: bool = True):
        """
        Set flag to stop auto-continue after current session completes.

        This allows graceful stopping: the current session finishes normally,
        but no new session is started.

        Args:
            project_id: UUID of the project
            stop: If True, stop after current. If False, clear flag.
        """
        self.stop_after_current[str(project_id)] = stop

    def should_stop_after_current(self, project_id: UUID) -> bool:
        """
        Check if auto-continue should be stopped after current session.

        Args:
            project_id: UUID of the project

        Returns:
            True if should stop after current session
        """
        return self.stop_after_current.get(str(project_id), False)

    async def get_session_info(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get information about a session.

        Args:
            session_id: UUID of the session

        Returns:
            Session dict if found, None otherwise
        """
        async with DatabaseManager() as db:
            # Get session from history (there's no get_session method)
            # We'll need to query by session_id from the sessions table
            async with db.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM sessions WHERE id = $1",
                    session_id
                )
                return dict(row) if row else None

    async def list_sessions(self, project_id: UUID) -> List[Dict[str, Any]]:
        """
        List all sessions for a project.

        Args:
            project_id: UUID of the project

        Returns:
            List of session dicts
        """
        async with DatabaseManager() as db:
            return await db.get_session_history(project_id, limit=100)

    async def get_active_sessions(self) -> List[Dict[str, Any]]:
        """
        Get all currently active sessions.

        Returns:
            List of active session dicts
        """
        async with DatabaseManager() as db:
            # Get all projects and check for active sessions
            projects = await db.list_projects()
            active_sessions = []
            for project in projects:
                session = await db.get_active_session(project['id'])
                if session:
                    active_sessions.append(session)
            return active_sessions

    # =========================================================================
    # Environment Configuration
    # =========================================================================

    async def mark_env_configured(self, project_id: UUID) -> bool:
        """
        Mark a project's environment as configured.

        Args:
            project_id: UUID of the project

        Returns:
            True if successful
        """
        async with DatabaseManager() as db:
            await db.update_project_env_configured(project_id, configured=True)
            return True

    async def delete_project(self, project_id: UUID) -> bool:
        """
        Delete a project and all associated data.

        This removes:
        - Database records (project, epics, tasks, tests, sessions)
        - Generated code directory
        - Log files

        Args:
            project_id: UUID of the project to delete

        Returns:
            True if successful

        Raises:
            ValueError: If project doesn't exist
        """
        import shutil

        async with DatabaseManager() as db:
            # Get project info
            project = await db.get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            # Get project path
            project_name = project['name']
            projects_dir = Path(self.config.project.default_projects_dir)
            project_path = projects_dir / project_name

            # Delete from database first (this will cascade to all related tables)
            await db.delete_project(project_id)

            # Delete project directory if it exists
            if project_path.exists():
                try:
                    # First attempt: normal deletion with custom error handler
                    def handle_remove_readonly(func, path, exc):
                        """Error handler for Windows/macOS readonly files."""
                        import stat
                        import os
                        if not os.access(path, os.W_OK):
                            # Add write permissions and retry
                            os.chmod(path, stat.S_IWUSR | stat.S_IREAD)
                            func(path)
                        else:
                            raise

                    shutil.rmtree(project_path, onerror=handle_remove_readonly)
                    logger.info(f"Successfully deleted project directory: {project_path}")
                except (PermissionError, OSError) as e:
                    logger.warning(f"Permission error deleting {project_path}, retrying with ignore_errors: {e}")
                    shutil.rmtree(project_path, ignore_errors=True)
                    if project_path.exists():
                        logger.warning(f"Project directory partially deleted (some files may remain): {project_path}")
                    else:
                        logger.info(f"Successfully deleted project directory: {project_path}")

            return True

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def is_postgresql_configured(self) -> bool:
        """Check if PostgreSQL is configured."""
        return is_postgresql_configured()

    async def _write_blocker_info(self, project_path: Path, session_number: int, error_msg: str) -> None:
        """
        Write epic test block information to yokeflow/agent-progress.md.

        Args:
            project_path: Path to project directory
            session_number: Session number that was blocked
            error_msg: Error message from epic test failure
        """
        try:
            yokeflow_dir = project_path / "yokeflow"
            yokeflow_dir.mkdir(exist_ok=True)

            progress_file = yokeflow_dir / "agent-progress.md"

            # Read existing content
            existing_content = ""
            if progress_file.exists():
                existing_content = progress_file.read_text()

            # Parse error message to extract details
            # Error format: "Epic test failure blocked in {mode} mode: {reason}\nFailed tests: {tests}"
            lines = error_msg.split('\n')
            header_line = lines[0] if lines else error_msg
            failed_tests_line = lines[1] if len(lines) > 1 else ""

            # Create blocker entry
            blocker_entry = f"""
## ⚠️ Session {session_number} BLOCKED - Epic Test Failure

**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Status**: Session stopped due to epic test failure

**Details**:
```
{error_msg}
```

**What This Means**:
The session was automatically stopped because one or more epic tests failed in strict mode.
Epic tests verify that completed functionality works correctly. The session cannot continue
until these tests pass.

**Next Steps**:
1. Review the failed tests listed above
2. Identify which implementation needs to be fixed
3. Fix the code to make the tests pass
4. You can resume the session after fixing the issues

**For More Information**:
- Check the session logs in `logs/session_{session_number:03d}_*.jsonl`
- Review epic test results in the database
- See QUALITY_PLAN.md for information about epic test blocking

---

"""

            # Prepend to file (most recent first)
            new_content = blocker_entry + existing_content

            progress_file.write_text(new_content)
            logger.info(f"✅ Wrote blocker info to {progress_file}")

        except Exception as e:
            logger.error(f"Failed to write blocker info to progress file: {e}")
            # Don't raise - this is informational only

    async def cleanup_stale_sessions(self) -> int:
        """
        Clean up stale sessions across all projects.

        Marks sessions as 'interrupted' if they're still marked as 'running'
        but have been inactive for longer than type-specific thresholds:
        - Initializer: 30 minutes
        - Coding: 10 minutes
        - Review: 5 minutes

        This handles ungraceful shutdowns:
        - System sleep/hibernation
        - Process killed without cleanup
        - Orchestrator crash

        Returns:
            Number of sessions marked as interrupted
        """
        async with DatabaseManager() as db:
            return await db.cleanup_stale_sessions()
