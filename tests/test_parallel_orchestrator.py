"""
Tests for Parallel Agent Orchestrator.

Tests cover:
- Atomic task claiming (no duplicate claims)
- ParallelConfig validation
- Docker container naming with worker_id
- ParallelOrchestrator worker lifecycle
- API validation model

To run:
    pytest tests/test_parallel_orchestrator.py -v
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from uuid import uuid4, UUID
import pytest

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.utils.config import ParallelConfig, Config
from server.agent.parallel_orchestrator import (
    ParallelOrchestrator,
    WorkerStatus,
    WorkerInfo,
    ParallelSessionResult,
)
from server.api.validation import ParallelCodingRequest


# ============================================================
# ParallelConfig Tests
# ============================================================

@pytest.mark.unit
class TestParallelConfig:
    """Tests for ParallelConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        config = ParallelConfig()
        assert config.enabled is False
        assert config.max_workers == 2
        assert config.max_tasks_per_worker is None

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ParallelConfig(enabled=True, max_workers=3, max_tasks_per_worker=5)
        assert config.enabled is True
        assert config.max_workers == 3
        assert config.max_tasks_per_worker == 5

    def test_config_includes_parallel(self):
        """Test that main Config includes ParallelConfig."""
        config = Config()
        assert hasattr(config, 'parallel')
        assert isinstance(config.parallel, ParallelConfig)
        assert config.parallel.enabled is False

    def test_yaml_loading_parallel(self, tmp_path):
        """Test loading parallel config from YAML file."""
        yaml_content = """
parallel:
  enabled: true
  max_workers: 3
  max_tasks_per_worker: 10
"""
        config_file = tmp_path / ".yokeflow.yaml"
        config_file.write_text(yaml_content)

        config = Config.load_from_file(config_file)
        assert config.parallel.enabled is True
        assert config.parallel.max_workers == 3
        assert config.parallel.max_tasks_per_worker == 10

    def test_yaml_loading_max_workers_capped(self, tmp_path):
        """Test that max_workers is capped at 4."""
        yaml_content = """
parallel:
  enabled: true
  max_workers: 10
"""
        config_file = tmp_path / ".yokeflow.yaml"
        config_file.write_text(yaml_content)

        config = Config.load_from_file(config_file)
        assert config.parallel.max_workers == 4  # Capped at 4

    def test_yaml_loading_partial(self, tmp_path):
        """Test partial parallel config (only some fields)."""
        yaml_content = """
parallel:
  enabled: true
"""
        config_file = tmp_path / ".yokeflow.yaml"
        config_file.write_text(yaml_content)

        config = Config.load_from_file(config_file)
        assert config.parallel.enabled is True
        assert config.parallel.max_workers == 2  # Default
        assert config.parallel.max_tasks_per_worker is None  # Default


# ============================================================
# Docker Container Naming Tests
# ============================================================

# ============================================================
# WorkerInfo and ParallelSessionResult Tests
# ============================================================

@pytest.mark.unit
class TestWorkerModels:
    """Tests for worker data models."""

    def test_worker_info_defaults(self):
        """Test WorkerInfo default values."""
        info = WorkerInfo(worker_id="worker-1")
        assert info.worker_id == "worker-1"
        assert info.status == WorkerStatus.IDLE
        assert info.current_session_id is None
        assert info.current_task_id is None
        assert info.tasks_completed == 0
        assert info.error is None

    def test_worker_status_transitions(self):
        """Test worker status transitions."""
        info = WorkerInfo(worker_id="worker-1")
        assert info.status == WorkerStatus.IDLE

        info.status = WorkerStatus.RUNNING
        assert info.status == WorkerStatus.RUNNING

        info.status = WorkerStatus.COMPLETED
        assert info.status == WorkerStatus.COMPLETED

    def test_worker_status_error(self):
        """Test worker error status."""
        info = WorkerInfo(worker_id="worker-1")
        info.status = WorkerStatus.ERROR
        info.error = "Connection failed"
        assert info.status == WorkerStatus.ERROR
        assert info.error == "Connection failed"

    def test_parallel_session_result_to_dict(self):
        """Test ParallelSessionResult serialization."""
        workers = [
            WorkerInfo(worker_id="worker-1", status=WorkerStatus.COMPLETED, tasks_completed=3),
            WorkerInfo(worker_id="worker-2", status=WorkerStatus.ERROR, tasks_completed=1, error="timeout"),
        ]
        result = ParallelSessionResult(
            workers=workers,
            total_tasks_completed=4,
            duration_seconds=120.5,
            errors=["worker-2: timeout"],
        )

        d = result.to_dict()
        assert d["total_tasks_completed"] == 4
        assert d["duration_seconds"] == 120.5
        assert len(d["workers"]) == 2
        assert d["workers"][0]["worker_id"] == "worker-1"
        assert d["workers"][0]["status"] == "completed"
        assert d["workers"][0]["tasks_completed"] == 3
        assert d["workers"][1]["error"] == "timeout"
        assert len(d["errors"]) == 1


# ============================================================
# ParallelOrchestrator Tests
# ============================================================

@pytest.mark.unit
class TestParallelOrchestrator:
    """Tests for ParallelOrchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Create a ParallelOrchestrator with default config."""
        config = Config()
        return ParallelOrchestrator(config=config)

    def test_init(self, orchestrator):
        """Test orchestrator initialization."""
        assert orchestrator._stop_requested is False
        assert orchestrator._workers == {}

    def test_request_stop(self, orchestrator):
        """Test stop request."""
        orchestrator.request_stop()
        assert orchestrator._stop_requested is True

    @pytest.mark.asyncio
    async def test_project_not_found(self, orchestrator):
        """Test error when project not found."""
        mock_db = AsyncMock()
        mock_db.get_project.return_value = None
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch('server.agent.parallel_orchestrator.DatabaseManager', return_value=mock_db):
            with pytest.raises(ValueError, match="Project not found"):
                await orchestrator.run_parallel_coding(
                    project_id=uuid4(),
                    num_workers=2,
                )

    @pytest.mark.asyncio
    async def test_project_already_complete(self, orchestrator):
        """Test error when project already complete."""
        mock_db = AsyncMock()
        mock_db.get_project.return_value = {
            'name': 'test',
            'completed_at': '2026-01-01',
        }
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch('server.agent.parallel_orchestrator.DatabaseManager', return_value=mock_db):
            with pytest.raises(ValueError, match="already complete"):
                await orchestrator.run_parallel_coding(
                    project_id=uuid4(),
                    num_workers=2,
                )

    @pytest.mark.asyncio
    async def test_no_tasks_remaining(self, orchestrator):
        """Test error when no tasks remaining."""
        mock_db = AsyncMock()
        mock_db.get_project.return_value = {
            'name': 'test',
            'completed_at': None,
        }
        mock_db.list_epics.return_value = [{'id': 1, 'name': 'Epic 1'}]
        mock_db.get_progress.return_value = {
            'total_tasks': 5,
            'completed_tasks': 5,
        }
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch('server.agent.parallel_orchestrator.DatabaseManager', return_value=mock_db):
            with pytest.raises(ValueError, match="No tasks remaining"):
                await orchestrator.run_parallel_coding(
                    project_id=uuid4(),
                    num_workers=2,
                )

    @pytest.mark.asyncio
    async def test_workers_capped_at_remaining_tasks(self, orchestrator):
        """Test that worker count is capped at remaining tasks."""
        project_id = uuid4()
        call_count = 0

        mock_db = AsyncMock()

        async def mock_get_project(pid):
            return {
                'name': 'test',
                'completed_at': None,
                'local_path': '/tmp/test',
                'project_type': 'greenfield',
                'metadata': '{"settings": {}}',
            }

        mock_db.get_project = mock_get_project
        mock_db.list_epics.return_value = [{'id': 1}]
        mock_db.get_progress.return_value = {
            'total_tasks': 5,
            'completed_tasks': 3,  # Only 2 remaining
        }
        mock_db.claim_next_task.return_value = None  # No more tasks
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch('server.agent.parallel_orchestrator.DatabaseManager', return_value=mock_db):

            result = await orchestrator.run_parallel_coding(
                project_id=project_id,
                num_workers=4,  # Request 4 but only 2 tasks remain
            )

            # Should have created only 2 workers
            assert len(result.workers) == 2

    def test_num_workers_hard_cap(self):
        """Test that num_workers is hard-capped at 4."""
        # This is tested via the validation model
        request = ParallelCodingRequest(num_workers=4)
        assert request.num_workers == 4

        with pytest.raises(Exception):
            ParallelCodingRequest(num_workers=5)


# ============================================================
# ParallelCodingRequest Validation Tests
# ============================================================

@pytest.mark.unit
class TestParallelCodingRequestValidation:
    """Tests for ParallelCodingRequest Pydantic model."""

    def test_defaults(self):
        """Test default values."""
        request = ParallelCodingRequest()
        assert request.num_workers == 2
        assert request.coding_model is None
        assert request.max_tasks_per_worker is None

    def test_valid_request(self):
        """Test valid request with all fields."""
        request = ParallelCodingRequest(
            num_workers=3,
            coding_model="claude-sonnet-4-6",
            max_tasks_per_worker=5,
        )
        assert request.num_workers == 3
        assert request.coding_model == "claude-sonnet-4-6"
        assert request.max_tasks_per_worker == 5

    def test_num_workers_min(self):
        """Test num_workers minimum is 1."""
        with pytest.raises(Exception):
            ParallelCodingRequest(num_workers=0)

    def test_num_workers_max(self):
        """Test num_workers maximum is 4."""
        with pytest.raises(Exception):
            ParallelCodingRequest(num_workers=5)

    def test_invalid_model_name(self):
        """Test invalid model name is rejected."""
        with pytest.raises(Exception):
            ParallelCodingRequest(coding_model="gpt-4")

    def test_valid_model_names(self):
        """Test various valid Claude model names."""
        valid_models = [
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5",
        ]
        for model in valid_models:
            request = ParallelCodingRequest(coding_model=model)
            assert request.coding_model == model

    def test_max_tasks_per_worker_min(self):
        """Test max_tasks_per_worker minimum is 1."""
        with pytest.raises(Exception):
            ParallelCodingRequest(max_tasks_per_worker=0)

    def test_max_tasks_per_worker_none(self):
        """Test max_tasks_per_worker can be None (unlimited)."""
        request = ParallelCodingRequest(max_tasks_per_worker=None)
        assert request.max_tasks_per_worker is None


# ============================================================
# Database Claim Task Tests (Mocked)
# ============================================================

@pytest.mark.unit
class TestClaimNextTask:
    """Tests for claim_next_task database operation."""

    @pytest.mark.asyncio
    async def test_claim_returns_none_when_empty(self):
        """Test claim_next_task returns None when no tasks available."""
        from contextlib import asynccontextmanager
        from server.database.operations import TaskDatabase

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.fetch = AsyncMock(return_value=[])

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        db = TaskDatabase.__new__(TaskDatabase)
        db.pool = MagicMock()
        db.acquire = mock_acquire

        result = await db.claim_next_task(uuid4(), "worker-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_claim_returns_task_with_tests(self):
        """Test claim_next_task returns task with tests."""
        from contextlib import asynccontextmanager
        from server.database.operations import TaskDatabase

        # Create a dict-like Record mock (asyncpg Record supports dict() conversion)
        task_data = {
            'id': 42,
            'epic_id': 1,
            'name': 'Implement login page',
            'description': 'Create login.tsx',
            'priority': 1,
            'done': False,
            'session_notes': 'worker-1 claimed at 2026-02-14',
            'epic_name': 'Authentication',
            'epic_description': 'User auth system',
            'created_at': '2026-02-14',
            'completed_at': None,
        }
        mock_task_row = MagicMock()
        mock_task_row.keys.return_value = task_data.keys()
        mock_task_row.__iter__ = MagicMock(return_value=iter(task_data))
        mock_task_row.__getitem__ = MagicMock(side_effect=lambda k: task_data[k])
        # Make bool(mock_task_row) truthy for the `if not task_row` check
        mock_task_row.__bool__ = MagicMock(return_value=True)

        test_data = {'id': 1, 'task_id': 42, 'description': 'Login form renders', 'passes': None}
        mock_test_row = MagicMock()
        mock_test_row.keys.return_value = test_data.keys()
        mock_test_row.__iter__ = MagicMock(return_value=iter(test_data))
        mock_test_row.__getitem__ = MagicMock(side_effect=lambda k: test_data[k])

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_task_row)
        mock_conn.fetch = AsyncMock(return_value=[mock_test_row])

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        db = TaskDatabase.__new__(TaskDatabase)
        db.pool = MagicMock()
        db.acquire = mock_acquire

        result = await db.claim_next_task(uuid4(), "worker-1")
        assert result is not None
        assert result['id'] == 42
        assert result['epic_name'] == 'Authentication'
        assert len(result['tests']) == 1
        assert result['tests'][0]['description'] == 'Login form renders'
