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
    get_expansion_prompt,
    get_coding_prompt,
    get_brownfield_coding_preamble,
    copy_spec_to_project,
)
from server.agent.codebase_import import CodebaseImporter
from server.utils.observability import SessionLogger, QuietOutputFilter, create_session_logger
from server.agent.agent import run_agent_session, SessionManager
from server.utils.config import Config
from server.sandbox.manager import SandboxManager
from server.sandbox.hooks import set_active_sandbox, clear_active_sandbox
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

        # Expansion worker tasks for cancellation (session_id -> asyncio.Task)
        self._expansion_tasks: Dict[str, asyncio.Task] = {}

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
        sandbox_type: str = "docker",
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
            sandbox_type: Sandbox type (docker or local), default: docker
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

            # Create project directory in generations
            generations_dir = Path(self.config.project.default_generations_dir)
            project_path = generations_dir / project_name
            project_path.mkdir(parents=True, exist_ok=True)

            # Copy spec files to project directory if source provided
            if spec_source:
                copy_spec_to_project(project_path, spec_source)
            elif spec_content:
                # Write spec_content to app_spec.txt if no source file provided
                (project_path / "app_spec.txt").write_text(spec_content)

            # Create project in database
            project = await db.create_project(
                name=project_name,
                spec_file_path=spec_path or "",
                spec_content=spec_content,
                user_id=user_id,
            )

            # Update project with local_path and initial settings
            await db.update_project(project['id'], local_path=str(project_path))
            project['local_path'] = str(project_path)

            # Set initial project settings
            settings = {
                'sandbox_type': sandbox_type,
                'max_iterations': None,  # None = unlimited (auto-continue)
            }
            if initializer_model:
                settings['initializer_model'] = initializer_model
            if coding_model:
                settings['coding_model'] = coding_model

            await db.update_project_settings(project['id'], settings)

            return project

    async def create_brownfield_project(
        self,
        project_name: str,
        source_url: Optional[str] = None,
        source_path: Optional[str] = None,
        branch: str = "main",
        change_spec_content: Optional[str] = None,
        user_id: Optional[UUID] = None,
        sandbox_type: str = "docker",
        initializer_model: Optional[str] = None,
        coding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a brownfield project from an existing codebase.

        The codebase is imported into generations/<project_name>/, analyzed,
        and prepared for the brownfield initializer session which creates
        epics/tasks scoped to the requested changes.

        Args:
            project_name: Name for the project (must be unique)
            source_url: Git repository URL to clone from
            source_path: Local filesystem path to copy from
            branch: Git branch to import (default: main)
            change_spec_content: Description of changes to make
            user_id: User ID (optional)
            sandbox_type: Sandbox type (docker or local)
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
            generations_dir = Path(self.config.project.default_generations_dir)
            project_path = generations_dir / project_name
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

            # Write change spec
            if change_spec_content:
                (project_path / "change_spec.md").write_text(change_spec_content)
                (project_path / "app_spec.txt").write_text(
                    "# Brownfield Project - Change Specification\n\n"
                    "This is a brownfield project. The change specification "
                    "is in: `change_spec.md`\n\n"
                    "**Please read change_spec.md for what needs to be changed.**\n"
                )

            # Set up git feature branch
            feature_branch = await importer.setup_brownfield_git(
                project_path,
                branch_name=f"{self.config.brownfield.default_feature_branch_prefix}modifications"
            )

            # Create project in database
            project = await db.create_project(
                name=project_name,
                spec_file_path="change_spec.md",
                spec_content=change_spec_content,
                user_id=user_id,
                project_type='brownfield',
                source_commit_sha=import_result.commit_sha,
                codebase_analysis=analysis.to_dict(),
            )

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
                'sandbox_type': sandbox_type,
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
            generations_dir = Path(self.config.project.default_generations_dir)
            project_path = generations_dir / project['name']
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
        parallel_expansion: Optional[bool] = None,
    ) -> SessionInfo:
        """
        Run initialization session (Session 0) for a project.

        This method:
        - Creates the project structure (epics, tasks, tests)
        - Runs init.sh to setup the environment
        - ALWAYS stops after Session 0 completes
        - Does NOT auto-continue to coding sessions

        When parallel_expansion is enabled:
        - Session 0 runs with planning-only prompt (creates epics, structure, git)
        - After Session 0, parallel workers expand epics into tasks and tests

        Args:
            project_id: UUID of the project
            initializer_model: Model to use (defaults to config.models.initializer)
            progress_callback: Optional async callback for real-time progress updates
            parallel_expansion: Override config.parallel.parallel_expansion setting

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

        # Determine parallel expansion setting
        use_parallel = parallel_expansion if parallel_expansion is not None else self.config.parallel.parallel_expansion
        planning_only = use_parallel

        # Run Session 0 (with planning_only if parallel expansion enabled)
        session_info = await self.start_session(
            project_id=project_id,
            initializer_model=initializer_model,
            coding_model=None,  # Not needed for initialization
            max_iterations=None,  # Not applicable
            progress_callback=progress_callback,
            planning_only=planning_only,
        )

        # Notify that Session 0 is complete (so UI can update before expansion)
        if self.event_callback:
            await self.event_callback(project_id, "session_complete", {
                "session": session_info.to_dict()
            })

        # If parallel expansion enabled, run expansion workers after Session 0
        if use_parallel and session_info.status != SessionStatus.ERROR:
            # Re-fetch project after Session 0 (local_path may have been set during start_session)
            async with DatabaseManager() as db:
                project = await db.get_project(project_id)
            local_path = project.get('local_path', '')
            if local_path:
                project_path = Path(local_path)
            else:
                # Fallback: reconstruct from generations dir + project name
                logger.warning(f"Project {project_id} has no local_path, reconstructing from project name")
                project_name = project.get('name', str(project_id))
                project_path = Path(self.config.project.default_generations_dir) / project_name
            project_type = project.get('project_type', 'greenfield')

            # Get sandbox type from project metadata
            project_metadata = project.get('metadata', {})
            if isinstance(project_metadata, str):
                import json
                project_metadata = json.loads(project_metadata)
            project_sandbox_type = project_metadata.get('settings', {}).get('sandbox_type')
            if not project_sandbox_type:
                project_sandbox_type = self.config.sandbox.type

            # Get codebase analysis for brownfield
            codebase_analysis = None
            if project_type == 'brownfield':
                codebase_analysis = project.get('codebase_analysis', {})
                if isinstance(codebase_analysis, str):
                    import json as json_mod
                    try:
                        codebase_analysis = json_mod.loads(codebase_analysis)
                    except (json_mod.JSONDecodeError, TypeError):
                        codebase_analysis = {}

            num_workers = self.config.parallel.max_expansion_workers
            expansion_result = await self._run_parallel_expansion(
                project_id=project_id,
                project_path=project_path,
                project_type=project_type,
                project_sandbox_type=project_sandbox_type,
                initializer_model=initializer_model,
                num_workers=num_workers,
                progress_callback=progress_callback,
                codebase_analysis=codebase_analysis,
            )

            logger.info(
                f"Parallel expansion complete: {expansion_result.get('epics_expanded', 0)} epics expanded "
                f"by {expansion_result.get('workers', 0)} workers"
            )

            if expansion_result.get('errors'):
                for error in expansion_result['errors']:
                    logger.error(f"Expansion error: {error}")

            # Run test coverage analysis now that tests exist (deferred from Session 0)
            if expansion_result.get('epics_expanded', 0) > 0:
                try:
                    async with DatabaseManager() as db:
                        await self.quality.run_test_coverage_analysis(project_id, db)
                except Exception as e:
                    logger.warning(f"Test coverage analysis failed after expansion: {e}")

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

                    # NOTE: Project Completion Review (Phase 7) is disabled for now
                    # Current implementation compares spec to epics/tasks/tests (the plan),
                    # not the actual working implementation. This is more useful as a
                    # post-initialization check rather than a final completion check.
                    # See YOKEFLOW_FUTURE_PLAN.md for plans to enhance this feature.
                    #
                    # To manually run a completion review, use the API endpoint:
                    # POST /api/projects/{project_id}/completion-review
                    #
                    # try:
                    #     logger.info("Triggering project completion review...")
                    #     from server.quality.completion_analyzer import CompletionAnalyzer
                    #
                    #     analyzer = CompletionAnalyzer(use_semantic_matching=True)
                    #     review = await analyzer.analyze_completion(project_id, db)
                    #
                    #     # Store in database
                    #     review_id = await db.store_completion_review(project_id, review)
                    #
                    #     logger.info(
                    #         f"Completion review finished: {review['recommendation'].upper()} "
                    #         f"(score={review['overall_score']}, coverage={review['coverage_percentage']:.1f}%)"
                    #     )
                    #
                    #     # Notify via callback
                    #     if self.event_callback:
                    #         await self.event_callback(project_id, "completion_review_complete", {
                    #             "review_id": str(review_id),
                    #             "score": review['overall_score'],
                    #             "recommendation": review['recommendation'],
                    #             "coverage_percentage": review['coverage_percentage']
                    #         })
                    #
                    # except Exception as e:
                    #     logger.error(f"Failed to generate completion review (non-fatal): {e}", exc_info=True)
                    #     # Don't fail project completion if review fails

                    # Stop Docker container to free up ports
                    # This is best-effort - don't fail if container doesn't exist or can't be stopped
                    try:
                        from server.sandbox.manager import SandboxManager
                        project = await db.get_project(project_id)
                        if project and project.get('sandbox_type') == 'docker':
                            project_name = project.get('name')
                            logger.info(f"Stopping Docker container for completed project: {project_name}")
                            stopped = SandboxManager.stop_docker_container(project_name)
                            #if stopped:
                                #logger.info(f"✅ Docker container stopped successfully")
                            #lse:
                                #logger.info(f"Docker container was not running or doesn't exist")
                    except Exception as e:
                        logger.warning(f"Failed to stop Docker container (non-fatal): {e}")

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
        planning_only: bool = False,
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

            # Get sandbox type from project metadata (not global config)
            project_metadata = project.get('metadata', {})
            if isinstance(project_metadata, str):
                import json
                project_metadata = json.loads(project_metadata)

            # Extract sandbox_type from metadata, default to config if not found
            project_sandbox_type = project_metadata.get('settings', {}).get('sandbox_type')
            if not project_sandbox_type:
                project_sandbox_type = self.config.sandbox.type
                logger.warning(f"No sandbox_type in project metadata, using config default: {project_sandbox_type}")

            # Ensure project path is valid and exists
            if not local_path or local_path == '':
                # Create project directory
                generations_dir = Path(self.config.project.default_generations_dir)
                project_path = generations_dir / project_name
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

            # Create sandbox using project-specific sandbox type
            sandbox_config = {
                "image": self.config.sandbox.docker_image,
                "network": self.config.sandbox.docker_network,
                "memory_limit": self.config.sandbox.docker_memory_limit,
                "cpu_limit": self.config.sandbox.docker_cpu_limit,
                "ports": self.config.sandbox.docker_ports,
                "session_type": session_type.value,  # "initializer" or "coding"
                "project_type": project.get('project_type', 'greenfield'),
            }
            #logger.info(f"Creating {project_sandbox_type} sandbox for project {project_name}")
            sandbox = SandboxManager.create_sandbox(
                sandbox_type=project_sandbox_type,  # Use project-specific, not global config
                project_dir=project_path,
                config=sandbox_config
            )

            try:
                # Start sandbox with timeout
                # Docker sandbox setup can hang during package installation
                sandbox_timeout = self.config.timing.sandbox_startup_timeout
                logger.info(f"Starting {project_sandbox_type} sandbox (timeout: {sandbox_timeout}s)")

                try:
                    await asyncio.wait_for(sandbox.start(), timeout=sandbox_timeout)
                except asyncio.TimeoutError:
                    logger.error(f"Sandbox failed to start within {sandbox_timeout}s - likely hung during package installation")
                    # Clean up the hung sandbox
                    try:
                        await sandbox.stop()
                    except Exception:
                        pass  # Ignore cleanup errors

                    # For initialization, we should retry
                    if is_initializer:
                        # Notify via callback about sandbox failure
                        if self.event_callback:
                            await self.event_callback(project_id, "sandbox_timeout", {
                                "message": "Docker sandbox setup timed out, likely due to package installation issues",
                                "timeout_seconds": sandbox_timeout
                            })

                        # Mark session as error for retry
                        await db.end_session(session_id, SessionStatus.ERROR.value,
                                           error_message="Sandbox startup timeout",
                                           metrics={"status": "sandbox_timeout"})

                        raise RuntimeError(f"Sandbox failed to start within {sandbox_timeout}s. This may be due to network issues during package installation. Please try again.")
                    else:
                        raise

                set_active_sandbox(sandbox)

                # Get Docker container name if sandbox is Docker
                docker_container = None
                from server.sandbox.manager import DockerSandbox
                if isinstance(sandbox, DockerSandbox):
                    docker_container = sandbox.container_name
                    logger.info(f"Docker sandbox active: {docker_container}")

                # Determine sandbox type for prompt selection and logging
                sandbox_type = "docker" if docker_container else "local"

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

                # Create logger with event callback and sandbox type
                session_logger = create_session_logger(
                    project_path, session_number, session_type.value, current_model,
                    sandbox_type=sandbox_type,
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

                # Create client (pass project_id and docker_container for MCP task-manager)
                client = create_client(
                    project_path,
                    current_model,
                    project_id=str(project_id),
                    docker_container=docker_container
                )

                # Get prompt based on session type, sandbox, and project type
                project_type = project.get('project_type', 'greenfield')

                if is_initializer:
                    base_prompt = get_initializer_prompt(
                        project_type=project_type,
                        planning_only=planning_only,
                    )
                    # Inject PROJECT_ID at the beginning of the prompt for easy access
                    prompt = f"PROJECT_ID: {project_id}\n\n{base_prompt}"

                    # For brownfield, inject codebase analysis
                    if project_type == 'brownfield':
                        import json as json_mod
                        analysis = project.get('codebase_analysis', {})
                        if isinstance(analysis, str):
                            try:
                                analysis = json_mod.loads(analysis)
                            except (json_mod.JSONDecodeError, TypeError):
                                analysis = {}
                        if analysis:
                            analysis_str = json_mod.dumps(analysis, indent=2)
                            prompt += (
                                f"\n\n## Codebase Analysis (Pre-computed)\n"
                                f"```json\n{analysis_str}\n```"
                            )
                elif resume_context:
                    # Include resume context in the prompt
                    base_prompt = get_coding_prompt(sandbox_type=sandbox_type)
                    resume_prompt = resume_context.get("resume_prompt", "")
                    prompt = f"{base_prompt}\n\n{resume_prompt}"
                else:
                    base_prompt = get_coding_prompt(sandbox_type=sandbox_type)
                    if project_type == 'brownfield':
                        preamble = get_brownfield_coding_preamble()
                        prompt = f"{preamble}\n\n{base_prompt}"
                    else:
                        prompt = base_prompt

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
                            # Prepare intervention config
                            intervention_config = {
                                "enabled": self.config.intervention.enabled,
                                "max_retries": self.config.intervention.max_retries,
                                "environment": sandbox_type  # Pass sandbox type (docker or local)
                            }

                            # Run session - no timeout for initialization once sandbox is running
                            # The real issue is sandbox startup, not the agent session
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
                                    # The sandbox startup timeout catches the real issue
                                    status, response, session_summary = await run_agent_session(
                                        client, prompt, project_path, logger=session_logger, verbose=self.verbose,
                                        session_manager=session_manager, progress_callback=progress_callback,
                                        intervention_config=intervention_config
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
                                            docker_container=docker_container
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
                                    intervention_config=intervention_config
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
                                docker_container=docker_container
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

                # Trigger deep review if needed (only for coding sessions)
                # The quality score and needs_deep_review are already calculated in session_summary
                if not is_initializer and metrics.get("needs_deep_review", False):
                    quality_score = metrics.get("quality_score", 0)
                    await self.quality.maybe_trigger_deep_review(session_id, project_path, quality_score)

                # Test Coverage Analysis: Run after initialization session
                # Skip when planning_only=True (tests created by expansion workers later)
                if is_initializer and status != "error" and not planning_only:
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

                    # Write blocker info to claude-progress.md
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
                # Stop sandbox
                try:
                    clear_active_sandbox()
                    await sandbox.stop()
                    logger.info(f"Sandbox stopped for session {session_number}")
                except Exception as e:
                    logger.error(f"Error stopping sandbox: {e}")

                # Restore signal handlers
                session_manager.restore_handlers()

                # Remove from session managers
                if str(session_id) in self.session_managers:
                    del self.session_managers[str(session_id)]

            return session_info

    # ── Parallel Expansion ───────────────────────────────────────────

    async def _run_parallel_expansion(
        self,
        project_id: UUID,
        project_path: Path,
        project_type: str,
        project_sandbox_type: str,
        initializer_model: str,
        num_workers: int = 2,
        progress_callback: Optional[Callable] = None,
        codebase_analysis: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Spawn parallel workers to expand epics into tasks and tests.
        Called after Session 0 creates epics with planning-only prompt.

        Args:
            project_id: Project UUID
            project_path: Path to project directory
            project_type: 'greenfield' or 'brownfield'
            project_sandbox_type: Sandbox type from project metadata
            initializer_model: Model to use for expansion (same as Session 0)
            num_workers: Number of parallel expansion workers
            progress_callback: Optional async callback for progress events
            codebase_analysis: Codebase analysis dict for brownfield projects

        Returns:
            Dict with workers count, epics_expanded, and errors
        """
        import time as time_mod

        start_time = time_mod.time()

        async with DatabaseManager() as db:
            unexpanded = await db.get_epics_needing_expansion(project_id)

        if not unexpanded:
            logger.info("All epics already expanded, skipping parallel expansion")
            return {"workers": 0, "epics_expanded": 0, "errors": []}

        # Auto-scale workers based on epic count (~6 epics per worker)
        # Then cap at the configured maximum and number of epics
        EPICS_PER_WORKER = 6
        auto_workers = max(1, (len(unexpanded) + EPICS_PER_WORKER - 1) // EPICS_PER_WORKER)
        num_workers = min(auto_workers, num_workers, len(unexpanded))

        logger.info(
            f"Starting parallel expansion: {num_workers} workers for "
            f"{len(unexpanded)} unexpanded epics"
        )

        # Notify
        if self.event_callback:
            await self.event_callback(project_id, "expansion_started", {
                "num_workers": num_workers,
                "total_epics": len(unexpanded),
            })

        # Round-robin assign epics to workers
        assignments: List[List[Dict]] = [[] for _ in range(num_workers)]
        for i, epic in enumerate(unexpanded):
            assignments[i % num_workers].append(epic)

        # Launch workers concurrently
        tasks = []
        for i, epic_list in enumerate(assignments):
            worker_id = f"expander-{i + 1}"
            tasks.append(asyncio.create_task(
                self._run_expansion_worker(
                    worker_id=worker_id,
                    project_id=project_id,
                    project_path=project_path,
                    project_type=project_type,
                    project_sandbox_type=project_sandbox_type,
                    model=initializer_model,
                    assigned_epics=epic_list,
                    progress_callback=progress_callback,
                    codebase_analysis=codebase_analysis,
                )
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect errors
        errors = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                error_msg = f"expander-{i + 1}: {str(r)}"
                errors.append(error_msg)
                logger.error(f"Expansion worker error: {error_msg}")

        # Check for any unexpanded epics remaining
        async with DatabaseManager() as db:
            still_unexpanded = await db.get_epics_needing_expansion(project_id)

        epics_expanded = len(unexpanded) - len(still_unexpanded)
        duration = time_mod.time() - start_time

        if still_unexpanded:
            logger.warning(
                f"{len(still_unexpanded)} epics still unexpanded after parallel expansion"
            )

        logger.info(
            f"Parallel expansion complete: {epics_expanded}/{len(unexpanded)} epics expanded "
            f"in {duration:.1f}s with {len(errors)} errors"
        )

        # Notify
        if self.event_callback:
            await self.event_callback(project_id, "expansion_complete", {
                "total_epics_expanded": epics_expanded,
                "total_epics": len(unexpanded),
                "duration_seconds": duration,
                "errors": errors,
            })

        return {
            "workers": num_workers,
            "epics_expanded": epics_expanded,
            "duration_seconds": duration,
            "errors": errors,
        }

    async def _run_expansion_worker(
        self,
        worker_id: str,
        project_id: UUID,
        project_path: Path,
        project_type: str,
        project_sandbox_type: str,
        model: str,
        assigned_epics: List[Dict],
        progress_callback: Optional[Callable] = None,
        codebase_analysis: Optional[Dict] = None,
    ) -> None:
        """
        Single expansion worker: expand assigned epics into tasks + tests.

        Each worker gets its own ClaudeSDKClient with MCP server access
        and runs the expansion prompt for its assigned epics.

        Args:
            worker_id: Worker identifier (e.g., 'expander-1')
            project_id: Project UUID
            project_path: Path to project directory
            project_type: 'greenfield' or 'brownfield'
            project_sandbox_type: Sandbox type
            model: Model to use (initializer model)
            assigned_epics: List of epic dicts to expand
            progress_callback: Optional progress callback
            codebase_analysis: Codebase analysis for brownfield projects
        """
        epic_names = [e.get('name', 'unnamed') for e in assigned_epics]
        logger.info(
            f"[{worker_id}] Starting expansion worker for {len(assigned_epics)} epics: "
            f"{', '.join(epic_names)}"
        )

        # Build epic list for prompt injection
        epic_lines = []
        for epic in assigned_epics:
            epic_lines.append(
                f"- **Epic ID**: `{epic['id']}`\n"
                f"  **Name**: {epic.get('name', 'N/A')}\n"
                f"  **Description**: {epic.get('description', 'N/A')}\n"
                f"  **Priority**: {epic.get('priority', 0)}"
            )

        # Load expansion prompt and inject epic assignments + project ID
        base_prompt = get_expansion_prompt()
        prompt = (
            f"PROJECT_ID: {project_id}\n\n"
            f"## Your Assigned Epics ({len(assigned_epics)} epics)\n\n"
            + "\n\n".join(epic_lines)
            + f"\n\n{base_prompt}"
        )

        # For brownfield: inject codebase analysis
        if project_type == 'brownfield' and codebase_analysis:
            import json as json_mod
            analysis_str = json_mod.dumps(codebase_analysis, indent=2)
            prompt += (
                f"\n\n## Codebase Analysis (Pre-computed)\n"
                f"Use this to understand the existing codebase when creating tasks.\n"
                f"Reference specific files and patterns in task descriptions.\n"
                f"Include regression tests where changes affect existing behavior.\n"
                f"```json\n{analysis_str}\n```"
            )

        # Create DB session for this worker
        # Expansion sessions use negative numbers (-1, -2, ...) so they don't
        # interfere with regular session numbering (0=initializer, 1+=coding)
        # Uses atomic INSERT...SELECT to avoid race conditions between concurrent workers
        session_id = None
        session_number = None
        try:
            async with DatabaseManager() as db:
                session = await db.create_expansion_session(
                    project_id=project_id,
                    session_type=SessionType.EXPANSION.value,
                    model=model,
                )

                session_id = session['id']
                session_number = session['session_number']
                await db.start_session(session_id)

            # Notify UI that expansion worker session has started
            if self.event_callback:
                await self.event_callback(project_id, "session_started", {
                    "session": {
                        "session_id": str(session_id),
                        "session_number": session_number,
                        "session_type": SessionType.EXPANSION.value,
                        "model": model,
                        "status": "running",
                        "worker_id": worker_id,
                    }
                })

            # Register session for cancellation support
            current_task = asyncio.current_task()
            if current_task and session_id:
                self._expansion_tasks[str(session_id)] = current_task

            # Create event callback for logger (sync wrapper for async callback)
            def logger_event_callback(event_type: str, data: dict):
                """Sync wrapper for async event callback."""
                if self.event_callback:
                    data['project_id'] = str(project_id)
                    data['session_id'] = str(session_id)
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(self.event_callback(project_id, event_type, data))
                    except RuntimeError:
                        pass

            # Create session logger
            session_logger = create_session_logger(
                project_path, session_number, SessionType.EXPANSION.value,
                model, sandbox_type="local",
                event_callback=logger_event_callback,
            )
            session_logger.session_id = str(session_id)
            session_logger.project_id = str(project_id)

            # Create SDK client (no docker_container needed -- expansion is DB-only)
            client = create_client(
                project_path,
                model,
                project_id=str(project_id),
            )

            # Run agent session
            session_status = SessionStatus.COMPLETED
            error_msg = None
            try:
                async with client:
                    status, response_text, _summary = await run_agent_session(
                        client=client,
                        message=prompt,
                        project_dir=project_path,
                        logger=session_logger,
                        verbose=False,
                        progress_callback=progress_callback,
                    )

                    if status == "error":
                        session_status = SessionStatus.ERROR
                        error_msg = response_text[:500] if response_text else "Unknown error"

            except Exception as e:
                session_status = SessionStatus.ERROR
                error_msg = str(e)[:500]
                logger.error(f"[{worker_id}] Expansion session error: {e}", exc_info=True)

            # End session in DB
            async with DatabaseManager() as db:
                await db.end_session(
                    session_id=session_id,
                    status=session_status.value,
                    error_message=error_msg,
                    metrics={
                        "worker_id": worker_id,
                        "assigned_epics": [str(e['id']) for e in assigned_epics],
                        "parallel_expansion": True,
                    },
                )

            logger.info(
                f"[{worker_id}] Expansion session {session_number} ended: {session_status.value}"
            )

            # Notify: expansion-specific event + generic session_complete for UI refresh
            if self.event_callback:
                await self.event_callback(project_id, "expansion_worker_complete", {
                    "worker_id": worker_id,
                    "session_number": session_number,
                    "status": session_status.value,
                    "epics_assigned": len(assigned_epics),
                })
                await self.event_callback(project_id, "session_complete", {
                    "session_id": str(session_id),
                    "session_number": session_number,
                    "status": session_status.value,
                })

            if session_status == SessionStatus.ERROR:
                raise RuntimeError(f"Expansion worker {worker_id} failed: {error_msg}")

        except Exception as e:
            # Ensure session is ended even on unexpected errors
            if session_id:
                try:
                    async with DatabaseManager() as db:
                        await db.end_session(
                            session_id=session_id,
                            status=SessionStatus.ERROR.value,
                            error_message=str(e)[:500],
                        )
                except Exception:
                    pass
            raise
        finally:
            # Clean up expansion task reference
            if session_id and str(session_id) in self._expansion_tasks:
                del self._expansion_tasks[str(session_id)]

    async def stop_session(self, session_id: UUID, reason: str = "User requested stop") -> bool:
        """
        Stop an active session immediately.

        Handles both regular sessions (via SessionManager) and expansion
        worker sessions (via asyncio task cancellation).

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

        # Check if this is an expansion worker session
        if session_id_str in self._expansion_tasks:
            task = self._expansion_tasks[session_id_str]
            task.cancel()

            # Update database
            async with DatabaseManager() as db:
                await db.end_session(
                    session_id,
                    SessionStatus.INTERRUPTED.value,
                    interruption_reason=reason
                )

            del self._expansion_tasks[session_id_str]
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
        - Docker container (if it exists)

        Args:
            project_id: UUID of the project to delete

        Returns:
            True if successful

        Raises:
            ValueError: If project doesn't exist
        """
        import shutil
        from server.sandbox.manager import SandboxManager

        async with DatabaseManager() as db:
            # Get project info
            project = await db.get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            # Get project path
            project_name = project['name']
            generations_dir = Path(self.config.project.default_generations_dir)
            project_path = generations_dir / project_name

            # Delete from database first (this will cascade to all related tables)
            await db.delete_project(project_id)

            # Delete Docker container if it exists (best effort - don't fail if error)
            try:
                deleted = SandboxManager.delete_docker_container(project_name)
                if deleted:
                    logger.info(f"Successfully deleted Docker container for project {project_name}")
                else:
                    logger.info(f"No Docker container found for project {project_name}")
            except Exception as e:
                logger.error(f"Failed to delete Docker container for project {project_name}: {e}", exc_info=True)

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
                    logger.warning(f"Permission denied deleting {project_path}, attempting Docker-based removal")

                    # Second attempt: use Docker to remove files created with root permissions
                    try:
                        import subprocess
                        # Use a Docker container to remove the directory with root permissions
                        # This handles cases where node_modules or other files were created by Docker
                        docker_cmd = [
                            "docker", "run", "--rm",
                            "-v", f"{project_path.absolute()}:/workspace",
                            "alpine:latest",
                            "sh", "-c", "rm -rf /workspace/* /workspace/.[!.]* /workspace/..?*"
                        ]
                        result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=30)

                        if result.returncode == 0:
                            # Docker removed the contents, now remove the empty directory
                            # Use shutil.rmtree with ignore_errors in case some hidden files remain
                            if project_path.exists():
                                try:
                                    project_path.rmdir()
                                except OSError:
                                    # If rmdir fails, try shutil.rmtree with ignore_errors
                                    shutil.rmtree(project_path, ignore_errors=True)
                            logger.info(f"Successfully deleted project directory using Docker: {project_path}")
                        else:
                            raise Exception(f"Docker removal failed: {result.stderr}")
                    except Exception as docker_error:
                        # Final fallback: delete with ignore_errors
                        logger.error(f"Docker removal failed: {docker_error}, using ignore_errors fallback")
                        shutil.rmtree(project_path, ignore_errors=True)
                        logger.warning(f"Project directory partially deleted (some files may remain): {project_path}")

            return True

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def is_postgresql_configured(self) -> bool:
        """Check if PostgreSQL is configured."""
        return is_postgresql_configured()

    async def _write_blocker_info(self, project_path: Path, session_number: int, error_msg: str) -> None:
        """
        Write epic test block information to claude-progress.md.

        Args:
            project_path: Path to project directory
            session_number: Session number that was blocked
            error_msg: Error message from epic test failure
        """
        try:
            yokeflow_dir = project_path / "yokeflow"
            yokeflow_dir.mkdir(exist_ok=True)

            progress_file = yokeflow_dir / "claude-progress.md"

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
