"""
Parallel Agent Orchestrator
============================

Manages multiple concurrent SDK agent workers for a single project.

Each worker gets its own ClaudeSDKClient + MCP server,
and independently claims and implements tasks using atomic database locking.

Usage:
    orchestrator = ParallelOrchestrator(config=config, event_callback=callback)
    result = await orchestrator.run_parallel_coding(
        project_id=uuid,
        num_workers=3,
    )
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Awaitable
from uuid import UUID
from datetime import datetime

import asyncpg

from server.client.claude import create_client
from server.client.prompts import get_coding_prompt, get_brownfield_coding_preamble
from server.database.connection import DatabaseManager
from server.agent.agent import run_agent_session, SessionManager
from server.agent.models import SessionStatus, SessionType, SessionInfo
from server.utils.observability import create_session_logger
from server.utils.config import Config
from server.utils.logging import get_logger

logger = get_logger(__name__)


class WorkerStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class WorkerInfo:
    """Tracks the state of a single parallel worker."""
    worker_id: str
    status: WorkerStatus = WorkerStatus.IDLE
    current_session_id: Optional[str] = None
    current_task_id: Optional[str] = None
    tasks_completed: int = 0
    error: Optional[str] = None


@dataclass
class ParallelSessionResult:
    """Result of a parallel coding session."""
    workers: List[WorkerInfo] = field(default_factory=list)
    total_tasks_completed: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workers": [
                {
                    "worker_id": w.worker_id,
                    "status": w.status.value,
                    "tasks_completed": w.tasks_completed,
                    "error": w.error,
                }
                for w in self.workers
            ],
            "total_tasks_completed": self.total_tasks_completed,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
        }


class ParallelOrchestrator:
    """
    Manages multiple concurrent agent workers for a single project.

    Each worker independently:
    1. Claims a task atomically (FOR UPDATE SKIP LOCKED)
    2. Creates its own SDK client with MCP servers
    3. Runs the agent loop
    4. Repeats until no tasks remain
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        event_callback: Optional[Callable] = None,
    ):
        self.config = config or Config.load_default()
        self.event_callback = event_callback
        self._stop_requested = False
        self._workers: Dict[str, WorkerInfo] = {}

    def request_stop(self):
        """Request all workers to stop after their current task."""
        self._stop_requested = True
        logger.info("Parallel orchestrator: stop requested")

    @property
    def workers(self) -> Dict[str, WorkerInfo]:
        return self._workers

    async def run_parallel_coding(
        self,
        project_id: UUID,
        num_workers: int = 2,
        coding_model: Optional[str] = None,
        max_tasks_per_worker: Optional[int] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> ParallelSessionResult:
        """
        Spawn N agents that concurrently implement different tasks.

        Args:
            project_id: Project UUID
            num_workers: Number of concurrent workers (capped at 4)
            coding_model: Model to use (defaults to config.models.coding)
            max_tasks_per_worker: Max tasks per worker (None = unlimited)
            progress_callback: Optional async callback for progress events

        Returns:
            ParallelSessionResult with summary of all workers
        """
        # Apply hard cap
        num_workers = min(num_workers, 4)
        coding_model = coding_model or self.config.models.coding
        self._stop_requested = False
        start_time = time.time()

        # Validate project
        async with DatabaseManager() as db:
            project = await db.get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            if project.get('completed_at'):
                raise ValueError(f"Project '{project['name']}' is already complete")

            epics = await db.list_epics(project_id)
            if len(epics) == 0:
                raise ValueError("Project not initialized. Run initialization first.")

            # Check remaining tasks
            progress = await db.get_progress(project_id)
            total_tasks = progress.get('total_tasks', 0)
            completed_tasks = progress.get('completed_tasks', 0)
            remaining = total_tasks - completed_tasks

            if remaining == 0:
                raise ValueError("No tasks remaining to implement")

            # Don't spawn more workers than tasks
            num_workers = min(num_workers, remaining)

        project_name = project['name']
        project_path = Path(project.get('local_path', ''))
        project_type = project.get('project_type', 'greenfield')

        logger.info(
            f"Starting parallel coding: {num_workers} workers for project "
            f"'{project_name}' ({remaining} tasks remaining)"
        )

        # Notify
        if self.event_callback:
            await self.event_callback(project_id, "parallel_coding_started", {
                "num_workers": num_workers,
                "remaining_tasks": remaining,
            })

        # Create worker infos
        worker_infos = []
        for i in range(num_workers):
            worker_id = f"worker-{i + 1}"
            info = WorkerInfo(worker_id=worker_id)
            self._workers[worker_id] = info
            worker_infos.append(info)

        # Launch workers concurrently
        tasks = [
            asyncio.create_task(
                self._run_coding_worker(
                    worker_info=info,
                    project_id=project_id,
                    project_name=project_name,
                    project_path=project_path,
                    project_type=project_type,
                    coding_model=coding_model,
                    max_tasks=max_tasks_per_worker,
                    progress_callback=progress_callback,
                )
            )
            for info in worker_infos
        ]

        # Wait for all workers to finish
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        result = ParallelSessionResult(
            workers=worker_infos,
            duration_seconds=time.time() - start_time,
        )

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                error_msg = f"{worker_infos[i].worker_id}: {str(r)}"
                result.errors.append(error_msg)
                worker_infos[i].status = WorkerStatus.ERROR
                worker_infos[i].error = str(r)

        result.total_tasks_completed = sum(w.tasks_completed for w in worker_infos)

        logger.info(
            f"Parallel coding complete: {result.total_tasks_completed} tasks "
            f"in {result.duration_seconds:.1f}s with {len(result.errors)} errors"
        )

        # Notify
        if self.event_callback:
            await self.event_callback(project_id, "parallel_coding_complete", result.to_dict())

        # Check if project is now complete
        async with DatabaseManager() as db:
            progress = await db.get_progress(project_id)
            total_tasks = progress.get('total_tasks', 0)
            completed_tasks = progress.get('completed_tasks', 0)

            if total_tasks > 0 and completed_tasks >= total_tasks:
                await db.mark_project_complete(project_id)
                logger.info(f"Project '{project_name}' marked as complete!")

                if self.event_callback:
                    await self.event_callback(project_id, "project_complete", {
                        "total_tasks": total_tasks,
                        "completed_tasks": completed_tasks,
                    })

        # Cleanup workers
        self._workers.clear()

        return result

    async def _run_coding_worker(
        self,
        worker_info: WorkerInfo,
        project_id: UUID,
        project_name: str,
        project_path: Path,
        project_type: str,
        coding_model: str,
        max_tasks: Optional[int],
        progress_callback: Optional[Callable] = None,
    ):
        """
        Single worker loop: claim task → create session → run agent → repeat.
        """
        worker_id = worker_info.worker_id
        tasks_completed = 0

        logger.info(f"[{worker_id}] Starting worker")

        try:
            while True:
                # Check stop request
                if self._stop_requested:
                    logger.info(f"[{worker_id}] Stop requested, exiting")
                    break

                # Check task limit
                if max_tasks is not None and tasks_completed >= max_tasks:
                    logger.info(f"[{worker_id}] Reached max tasks ({max_tasks}), exiting")
                    break

                # Claim next task atomically
                async with DatabaseManager() as db:
                    task = await db.claim_next_task(project_id, worker_id)

                if not task:
                    logger.info(f"[{worker_id}] No more tasks available, exiting")
                    break

                task_id = task['id']
                task_desc = task.get('name', '')[:80]
                worker_info.current_task_id = str(task_id)
                worker_info.status = WorkerStatus.RUNNING

                logger.info(f"[{worker_id}] Claimed task {task_id}: {task_desc}")

                # Create DB session for this task
                async with DatabaseManager() as db:
                    session_number = await db.get_next_session_number(project_id)
                    try:
                        session = await db.create_session(
                            project_id=project_id,
                            session_number=session_number,
                            session_type=SessionType.CODING.value,
                            model=coding_model,
                        )
                    except asyncpg.UniqueViolationError:
                        # Race condition on session number - retry with next number
                        session_number = await db.get_next_session_number(project_id)
                        session = await db.create_session(
                            project_id=project_id,
                            session_number=session_number,
                            session_type=SessionType.CODING.value,
                            model=coding_model,
                        )

                    session_id = session['id']
                    worker_info.current_session_id = str(session_id)

                    await db.start_session(session_id)

                # Create session logger
                session_logger = create_session_logger(
                    project_path, session_number, SessionType.CODING.value,
                    coding_model,
                )
                session_logger.session_id = str(session_id)
                session_logger.project_id = str(project_id)

                # Build prompt with parallel mode preamble
                base_prompt = get_coding_prompt()
                if project_type == 'brownfield':
                    preamble = get_brownfield_coding_preamble()
                    base_prompt = f"{preamble}\n\n{base_prompt}"

                parallel_preamble = (
                    f"## PARALLEL EXECUTION MODE\n"
                    f"You are worker '{worker_id}'. Task {task_id} has been pre-assigned to you.\n"
                    f"Use `start_task` with task_id={task_id} to begin, then implement it.\n"
                    f"Do NOT call `get_next_task` — your task is already assigned.\n"
                    f"After completing this task, your session will end. "
                    f"Do not attempt to get another task.\n"
                )
                prompt = f"{parallel_preamble}\n\n{base_prompt}"

                # Create SDK client
                client = create_client(
                    project_path,
                    coding_model,
                    project_id=str(project_id),
                )

                # Run agent session
                session_status = SessionStatus.COMPLETED
                error_msg = None
                try:
                    async with client:
                        intervention_config = {
                            "enabled": self.config.intervention.enabled,
                            "max_retries": self.config.intervention.max_retries,
                            "environment": "local",
                        }
                        status, response_text, _summary = await run_agent_session(
                            client=client,
                            message=prompt,
                            project_dir=project_path,
                            logger=session_logger,
                            verbose=False,
                            intervention_config=intervention_config,
                            progress_callback=progress_callback,
                        )

                        if status == "error":
                            session_status = SessionStatus.ERROR
                            error_msg = response_text[:500] if response_text else "Unknown error"
                        else:
                            tasks_completed += 1
                            worker_info.tasks_completed = tasks_completed

                except KeyboardInterrupt:
                    session_status = SessionStatus.INTERRUPTED
                    logger.info(f"[{worker_id}] Session interrupted")
                    self._stop_requested = True
                except Exception as e:
                    session_status = SessionStatus.ERROR
                    error_msg = str(e)[:500]
                    logger.error(f"[{worker_id}] Session error: {e}", exc_info=True)

                # End session in DB
                async with DatabaseManager() as db:
                    await db.end_session(
                        session_id=session_id,
                        status=session_status.value,
                        error_message=error_msg,
                        metrics={
                            "worker_id": worker_id,
                            "task_id": str(task_id),
                            "parallel_mode": True,
                        },
                    )

                logger.info(
                    f"[{worker_id}] Session {session_number} ended: {session_status.value}"
                )

                # Notify
                if self.event_callback:
                    await self.event_callback(project_id, "worker_task_complete", {
                        "worker_id": worker_id,
                        "task_id": str(task_id),
                        "session_number": session_number,
                        "status": session_status.value,
                        "tasks_completed": tasks_completed,
                    })

                # If session errored, stop this worker
                if session_status == SessionStatus.ERROR:
                    worker_info.error = error_msg
                    break

                # Brief delay between tasks
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"[{worker_id}] Worker failed: {e}", exc_info=True)
            worker_info.status = WorkerStatus.ERROR
            worker_info.error = str(e)
            raise
        finally:
            # Mark worker as completed if not errored
            if worker_info.status != WorkerStatus.ERROR:
                worker_info.status = WorkerStatus.COMPLETED

        logger.info(f"[{worker_id}] Worker finished: {tasks_completed} tasks completed")
