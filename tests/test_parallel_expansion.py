"""
Tests for Parallel Initialization (Epic Expansion Workers).

Tests cover:
- Planning-only prompt loading
- Expansion prompt loading
- ParallelConfig expansion settings
- Round-robin epic assignment
- is_expansion_complete() database method
- Orchestrator parallel expansion flow

To run:
    pytest tests/test_parallel_expansion.py -v
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from uuid import uuid4, UUID
import pytest

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.utils.config import ParallelConfig, Config
from server.client.prompts import (
    get_initializer_prompt,
    get_expansion_prompt,
)
from server.agent.orchestrator import AgentOrchestrator
from server.agent.models import SessionStatus, SessionType, SessionInfo


# ============================================================
# Prompt Loading Tests
# ============================================================

@pytest.mark.unit
class TestPlanningOnlyPrompts:
    """Tests for planning-only and expansion prompt loading."""

    def test_planning_only_greenfield_loads(self):
        """Verify planning-only greenfield prompt loads correctly."""
        prompt = get_initializer_prompt(project_type="greenfield", planning_only=True)
        assert "Planning Only" in prompt or "PARALLEL MODE" in prompt
        assert "create_epic" in prompt
        # Should NOT mention expand_epic as an allowed tool
        assert "FORBIDDEN" in prompt
        # Should mention parallel workers
        assert "parallel" in prompt.lower()

    def test_planning_only_brownfield_loads(self):
        """Verify planning-only brownfield prompt loads correctly."""
        prompt = get_initializer_prompt(project_type="brownfield", planning_only=True)
        assert "BROWNFIELD" in prompt
        assert "PARALLEL MODE" in prompt
        assert "create_epic" in prompt

    def test_standard_greenfield_unchanged(self):
        """Verify standard greenfield prompt is unaffected by planning_only=False."""
        prompt = get_initializer_prompt(project_type="greenfield", planning_only=False)
        assert "expand_epic" in prompt
        assert "create_task_test" in prompt
        # This is the full prompt, should have TASK 2 (Expand Epics)
        assert "TASK 2" in prompt

    def test_standard_brownfield_unchanged(self):
        """Verify standard brownfield prompt is unaffected by planning_only=False."""
        prompt = get_initializer_prompt(project_type="brownfield", planning_only=False)
        assert "expand_epic" in prompt
        assert "BROWNFIELD" in prompt

    def test_expansion_prompt_loads(self):
        """Verify expansion worker prompt loads correctly."""
        prompt = get_expansion_prompt()
        assert "Epic Expansion Agent" in prompt
        assert "expand_epic" in prompt
        assert "create_task_test" in prompt
        assert "create_epic_test" in prompt
        # Should forbid coding tools
        assert "get_next_task" in prompt
        assert "FORBIDDEN" in prompt

    def test_planning_only_default_false(self):
        """Verify planning_only defaults to False."""
        prompt_default = get_initializer_prompt(project_type="greenfield")
        prompt_explicit = get_initializer_prompt(project_type="greenfield", planning_only=False)
        # Both should be identical (the full prompt)
        assert prompt_default == prompt_explicit


# ============================================================
# ParallelConfig Expansion Tests
# ============================================================

@pytest.mark.unit
class TestParallelExpansionConfig:
    """Tests for parallel expansion configuration."""

    def test_expansion_defaults(self):
        """Test default expansion config values."""
        config = ParallelConfig()
        assert config.parallel_expansion is True
        assert config.max_expansion_workers == 4

    def test_expansion_custom_values(self):
        """Test custom expansion config values."""
        config = ParallelConfig(parallel_expansion=False, max_expansion_workers=3)
        assert config.parallel_expansion is False
        assert config.max_expansion_workers == 3

    def test_expansion_config_in_main_config(self):
        """Test expansion config accessible from main Config."""
        config = Config()
        assert config.parallel.parallel_expansion is True
        assert config.parallel.max_expansion_workers == 4

    def test_yaml_loading_expansion(self, tmp_path):
        """Test loading expansion config from YAML."""
        yaml_content = """
parallel:
  parallel_expansion: false
  max_expansion_workers: 3
"""
        config_file = tmp_path / ".yokeflow.yaml"
        config_file.write_text(yaml_content)

        config = Config.load_from_file(config_file)
        assert config.parallel.parallel_expansion is False
        assert config.parallel.max_expansion_workers == 3

    def test_yaml_expansion_workers_cap(self, tmp_path):
        """Test max_expansion_workers is capped at 4."""
        yaml_content = """
parallel:
  max_expansion_workers: 10
"""
        config_file = tmp_path / ".yokeflow.yaml"
        config_file.write_text(yaml_content)

        config = Config.load_from_file(config_file)
        assert config.parallel.max_expansion_workers == 4  # Capped at 4

    def test_yaml_backward_compat_expansion_workers(self, tmp_path):
        """Test old expansion_workers key still works."""
        yaml_content = """
parallel:
  expansion_workers: 3
"""
        config_file = tmp_path / ".yokeflow.yaml"
        config_file.write_text(yaml_content)

        config = Config.load_from_file(config_file)
        assert config.parallel.max_expansion_workers == 3

    def test_yaml_mixed_parallel_config(self, tmp_path):
        """Test mixing coding parallel and expansion config."""
        yaml_content = """
parallel:
  enabled: true
  max_workers: 3
  parallel_expansion: true
  max_expansion_workers: 2
"""
        config_file = tmp_path / ".yokeflow.yaml"
        config_file.write_text(yaml_content)

        config = Config.load_from_file(config_file)
        assert config.parallel.enabled is True
        assert config.parallel.max_workers == 3
        assert config.parallel.parallel_expansion is True
        assert config.parallel.max_expansion_workers == 2


# ============================================================
# Auto-Scaling Worker Count Tests
# ============================================================

@pytest.mark.unit
class TestAutoScalingWorkers:
    """Tests for dynamic worker count based on epic count (~6 epics/worker)."""

    def _compute_workers(self, num_epics: int, max_workers: int = 4) -> int:
        """Reproduce the auto-scaling logic from _run_parallel_expansion."""
        EPICS_PER_WORKER = 6
        auto_workers = max(1, (num_epics + EPICS_PER_WORKER - 1) // EPICS_PER_WORKER)
        return min(auto_workers, max_workers, num_epics)

    def test_small_project_one_worker(self):
        """5 epics -> 1 worker (under threshold)."""
        assert self._compute_workers(5) == 1

    def test_six_epics_one_worker(self):
        """6 epics -> 1 worker (exactly one batch)."""
        assert self._compute_workers(6) == 1

    def test_seven_epics_two_workers(self):
        """7 epics -> 2 workers (spills into second batch)."""
        assert self._compute_workers(7) == 2

    def test_twelve_epics_two_workers(self):
        """12 epics -> 2 workers (two full batches)."""
        assert self._compute_workers(12) == 2

    def test_fifteen_epics_three_workers(self):
        """15 epics -> 3 workers."""
        assert self._compute_workers(15) == 3

    def test_twenty_epics_four_workers(self):
        """20 epics -> 4 workers (hits default cap)."""
        assert self._compute_workers(20) == 4

    def test_thirty_epics_capped_at_max(self):
        """30 epics -> 4 workers (capped at max_expansion_workers)."""
        assert self._compute_workers(30) == 4

    def test_custom_max_cap(self):
        """15 epics with max=2 -> 2 workers (capped)."""
        assert self._compute_workers(15, max_workers=2) == 2

    def test_one_epic_one_worker(self):
        """1 epic -> 1 worker (minimum)."""
        assert self._compute_workers(1) == 1


# ============================================================
# Round-Robin Epic Assignment Tests
# ============================================================

@pytest.mark.unit
class TestEpicAssignment:
    """Tests for round-robin epic assignment logic."""

    def test_even_distribution(self):
        """Test epics are evenly distributed across workers."""
        epics = [{"id": i, "name": f"Epic {i}"} for i in range(6)]
        num_workers = 3

        assignments = [[] for _ in range(num_workers)]
        for i, epic in enumerate(epics):
            assignments[i % num_workers].append(epic)

        assert len(assignments[0]) == 2
        assert len(assignments[1]) == 2
        assert len(assignments[2]) == 2
        # Check correct assignment
        assert assignments[0][0]["id"] == 0
        assert assignments[0][1]["id"] == 3
        assert assignments[1][0]["id"] == 1
        assert assignments[1][1]["id"] == 4

    def test_uneven_distribution(self):
        """Test uneven epic distribution (more epics than divisible by workers)."""
        epics = [{"id": i, "name": f"Epic {i}"} for i in range(7)]
        num_workers = 3

        assignments = [[] for _ in range(num_workers)]
        for i, epic in enumerate(epics):
            assignments[i % num_workers].append(epic)

        assert len(assignments[0]) == 3  # Gets extra
        assert len(assignments[1]) == 2
        assert len(assignments[2]) == 2

    def test_single_worker(self):
        """Test all epics go to single worker."""
        epics = [{"id": i} for i in range(5)]
        num_workers = 1

        assignments = [[] for _ in range(num_workers)]
        for i, epic in enumerate(epics):
            assignments[i % num_workers].append(epic)

        assert len(assignments[0]) == 5

    def test_more_workers_than_epics(self):
        """Test when workers exceed epic count -- workers capped at epic count."""
        epics = [{"id": i} for i in range(2)]
        num_workers = min(4, len(epics))  # Cap at epic count

        assignments = [[] for _ in range(num_workers)]
        for i, epic in enumerate(epics):
            assignments[i % num_workers].append(epic)

        assert num_workers == 2
        assert len(assignments[0]) == 1
        assert len(assignments[1]) == 1


# ============================================================
# is_expansion_complete Tests
# ============================================================

@pytest.mark.unit
class TestIsExpansionComplete:
    """Tests for is_expansion_complete database method."""

    @pytest.mark.asyncio
    async def test_all_expanded(self):
        """Test returns True when all epics have tasks."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=0)

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        from server.database.operations import TaskDatabase
        db = TaskDatabase.__new__(TaskDatabase)
        db._pool = MagicMock()
        db.acquire = mock_acquire

        result = await db.is_expansion_complete(uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_some_unexpanded(self):
        """Test returns False when some epics have no tasks."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=3)

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        from server.database.operations import TaskDatabase
        db = TaskDatabase.__new__(TaskDatabase)
        db._pool = MagicMock()
        db.acquire = mock_acquire

        result = await db.is_expansion_complete(uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_null_count(self):
        """Test handles None return (no epics at all)."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        from server.database.operations import TaskDatabase
        db = TaskDatabase.__new__(TaskDatabase)
        db._pool = MagicMock()
        db.acquire = mock_acquire

        result = await db.is_expansion_complete(uuid4())
        assert result is True  # No epics = "complete" (nothing to expand)


# ============================================================
# Expansion Session Numbering Tests
# ============================================================

@pytest.mark.unit
class TestExpansionSessionNumbering:
    """Tests for negative session numbering for expansion workers."""

    @pytest.mark.asyncio
    async def test_expansion_session_numbers_are_negative(self):
        """Test that expansion sessions get negative numbers."""
        mock_conn = AsyncMock()
        # Simulate: session 0 exists (initializer), MIN(session_number) = 0
        mock_conn.fetchval = AsyncMock(return_value=-1)

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        from server.database.operations import TaskDatabase
        db = TaskDatabase.__new__(TaskDatabase)
        db._pool = MagicMock()
        db.acquire = mock_acquire

        result = await db.get_next_expansion_session_number(uuid4())
        assert result == -1

    @pytest.mark.asyncio
    async def test_expansion_numbers_decrement(self):
        """Test second expansion session gets -2 when -1 exists."""
        mock_conn = AsyncMock()
        # MIN(session_number) = -1, so next is -2
        mock_conn.fetchval = AsyncMock(return_value=-2)

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        from server.database.operations import TaskDatabase
        db = TaskDatabase.__new__(TaskDatabase)
        db._pool = MagicMock()
        db.acquire = mock_acquire

        result = await db.get_next_expansion_session_number(uuid4())
        assert result == -2

    @pytest.mark.asyncio
    async def test_regular_session_numbers_skip_negative(self):
        """Test that get_next_session_number ignores negative (expansion) sessions."""
        mock_conn = AsyncMock()
        # MAX of non-negative session_numbers is 0 (initializer), so next is 1
        mock_conn.fetchval = AsyncMock(return_value=1)

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        from server.database.operations import TaskDatabase
        db = TaskDatabase.__new__(TaskDatabase)
        db._pool = MagicMock()
        db.acquire = mock_acquire

        result = await db.get_next_session_number(uuid4())
        assert result == 1  # First coding session, not affected by expansion sessions


# ============================================================
# Atomic Expansion Session Creation Tests
# ============================================================

@pytest.mark.unit
class TestAtomicExpansionSessionCreation:
    """Tests for create_expansion_session() with advisory lock to prevent race conditions."""

    def _make_mock_conn(self, mock_row):
        """Create a mock connection with transaction context manager and advisory lock."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_conn.execute = AsyncMock()  # For pg_advisory_xact_lock

        # Mock the transaction context manager
        mock_txn = AsyncMock()
        mock_txn.__aenter__ = AsyncMock(return_value=mock_txn)
        mock_txn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_txn)

        return mock_conn

    @pytest.mark.asyncio
    async def test_create_expansion_session_returns_session(self):
        """Test that create_expansion_session returns a full session record."""
        project_id = uuid4()
        session_id = uuid4()
        mock_row = {
            'id': session_id,
            'project_id': project_id,
            'session_number': -1,
            'type': 'expansion',
            'model': 'claude-3-opus',
            'status': 'pending',
        }

        mock_conn = self._make_mock_conn(mock_row)

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        from server.database.operations import TaskDatabase
        db = TaskDatabase.__new__(TaskDatabase)
        db._pool = MagicMock()
        db.acquire = mock_acquire

        result = await db.create_expansion_session(
            project_id=project_id,
            session_type='expansion',
            model='claude-3-opus',
        )

        assert result['session_number'] == -1
        assert result['type'] == 'expansion'
        assert result['status'] == 'pending'

    @pytest.mark.asyncio
    async def test_create_expansion_session_uses_advisory_lock(self):
        """Verify advisory lock is acquired before INSERT to serialize concurrent creates."""
        project_id = uuid4()
        mock_row = {'id': uuid4(), 'session_number': -1, 'type': 'expansion', 'model': 'claude-3-opus', 'status': 'pending'}

        mock_conn = self._make_mock_conn(mock_row)

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        from server.database.operations import TaskDatabase
        db = TaskDatabase.__new__(TaskDatabase)
        db._pool = MagicMock()
        db.acquire = mock_acquire

        await db.create_expansion_session(
            project_id=project_id,
            session_type='expansion',
            model='claude-3-opus',
        )

        # Verify advisory lock was called
        mock_conn.execute.assert_called_once()
        lock_sql = mock_conn.execute.call_args[0][0]
        assert 'pg_advisory_xact_lock' in lock_sql

        # Verify INSERT...SELECT with correct pattern
        insert_sql = mock_conn.fetchrow.call_args[0][0]
        assert 'INSERT INTO sessions' in insert_sql
        assert 'COALESCE(MIN(session_number), 0) - 1' in insert_sql
        assert 'RETURNING' in insert_sql

        # Verify transaction was used
        mock_conn.transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_expansion_session_passes_correct_params(self):
        """Verify correct parameters are passed to the SQL query."""
        project_id = uuid4()
        mock_row = {'id': uuid4(), 'session_number': -2, 'type': 'expansion', 'model': 'claude-sonnet', 'status': 'pending'}

        mock_conn = self._make_mock_conn(mock_row)

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        from server.database.operations import TaskDatabase
        db = TaskDatabase.__new__(TaskDatabase)
        db._pool = MagicMock()
        db.acquire = mock_acquire

        await db.create_expansion_session(
            project_id=project_id,
            session_type='expansion',
            model='claude-sonnet',
        )

        call_args = mock_conn.fetchrow.call_args
        # Parameters: project_id, session_type, model
        assert call_args[0][1] == project_id
        assert call_args[0][2] == 'expansion'
        assert call_args[0][3] == 'claude-sonnet'

        # Advisory lock should use the project_id
        lock_args = mock_conn.execute.call_args[0]
        assert str(project_id) == lock_args[1]


# ============================================================
# Orchestrator Parallel Expansion Tests
# ============================================================

@pytest.mark.unit
class TestOrchestratorParallelExpansion:
    """Tests for orchestrator parallel expansion integration."""

    def test_start_initialization_has_parallel_expansion_param(self):
        """Verify start_initialization accepts parallel_expansion parameter."""
        import inspect
        sig = inspect.signature(AgentOrchestrator.start_initialization)
        assert 'parallel_expansion' in sig.parameters
        # Default should be None (falls back to config)
        assert sig.parameters['parallel_expansion'].default is None

    def test_start_session_has_planning_only_param(self):
        """Verify start_session accepts planning_only parameter."""
        import inspect
        sig = inspect.signature(AgentOrchestrator.start_session)
        assert 'planning_only' in sig.parameters
        assert sig.parameters['planning_only'].default is False

    def test_run_parallel_expansion_method_exists(self):
        """Verify _run_parallel_expansion method exists on orchestrator."""
        assert hasattr(AgentOrchestrator, '_run_parallel_expansion')
        assert asyncio.iscoroutinefunction(AgentOrchestrator._run_parallel_expansion)

    def test_run_expansion_worker_method_exists(self):
        """Verify _run_expansion_worker method exists on orchestrator."""
        assert hasattr(AgentOrchestrator, '_run_expansion_worker')
        assert asyncio.iscoroutinefunction(AgentOrchestrator._run_expansion_worker)

    @pytest.mark.asyncio
    async def test_parallel_expansion_no_unexpanded_epics(self):
        """Test _run_parallel_expansion returns early when no unexpanded epics."""
        orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
        orchestrator.config = Config()
        orchestrator.event_callback = None
        orchestrator._expansion_tasks = {}

        # Mock DB to return empty list
        mock_db = AsyncMock()
        mock_db.get_epics_needing_expansion = AsyncMock(return_value=[])

        with patch('server.agent.orchestrator.DatabaseManager') as MockDBManager:
            MockDBManager.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            MockDBManager.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await orchestrator._run_parallel_expansion(
                project_id=uuid4(),
                project_path=Path("/tmp/test"),
                project_type="greenfield",
                project_sandbox_type="local",
                initializer_model="claude-3-opus",
                num_workers=2,
            )

            assert result["workers"] == 0
            assert result["epics_expanded"] == 0

    @pytest.mark.asyncio
    async def test_parallel_expansion_auto_scales_workers(self):
        """Test that worker count auto-scales based on epic count (~6/worker)."""
        orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
        orchestrator.config = Config()
        orchestrator.event_callback = None
        orchestrator._expansion_tasks = {}

        # 15 epics -> auto-scales to 3 workers (15/6=2.5, ceil=3), max=4
        epics = [
            {"id": uuid4(), "name": f"Epic {i}", "description": "desc", "priority": i}
            for i in range(15)
        ]

        mock_db = AsyncMock()
        mock_db.get_epics_needing_expansion = AsyncMock(side_effect=[epics, []])

        worker_calls = []

        async def mock_expansion_worker(**kwargs):
            worker_calls.append(kwargs.get('worker_id'))

        with patch('server.agent.orchestrator.DatabaseManager') as MockDBManager:
            MockDBManager.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            MockDBManager.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(orchestrator, '_run_expansion_worker', side_effect=mock_expansion_worker):
                result = await orchestrator._run_parallel_expansion(
                    project_id=uuid4(),
                    project_path=Path("/tmp/test"),
                    project_type="greenfield",
                    project_sandbox_type="local",
                    initializer_model="claude-3-opus",
                    num_workers=4,  # Max allowed
                )

                assert result["workers"] == 3  # 15 epics / 6 per worker = 3
                assert len(worker_calls) == 3

    @pytest.mark.asyncio
    async def test_parallel_expansion_small_project_one_worker(self):
        """Test that small projects (<=6 epics) use 1 worker."""
        orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
        orchestrator.config = Config()
        orchestrator.event_callback = None
        orchestrator._expansion_tasks = {}

        epics = [
            {"id": uuid4(), "name": f"Epic {i}", "description": "desc", "priority": i}
            for i in range(5)
        ]

        mock_db = AsyncMock()
        mock_db.get_epics_needing_expansion = AsyncMock(side_effect=[epics, []])

        worker_calls = []

        async def mock_expansion_worker(**kwargs):
            worker_calls.append(kwargs.get('worker_id'))

        with patch('server.agent.orchestrator.DatabaseManager') as MockDBManager:
            MockDBManager.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            MockDBManager.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(orchestrator, '_run_expansion_worker', side_effect=mock_expansion_worker):
                result = await orchestrator._run_parallel_expansion(
                    project_id=uuid4(),
                    project_path=Path("/tmp/test"),
                    project_type="greenfield",
                    project_sandbox_type="local",
                    initializer_model="claude-3-opus",
                    num_workers=4,
                )

                assert result["workers"] == 1  # 5 epics < 6 threshold
                assert len(worker_calls) == 1

    @pytest.mark.asyncio
    async def test_parallel_expansion_handles_worker_errors(self):
        """Test that expansion handles worker errors gracefully."""
        orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
        orchestrator.config = Config()
        orchestrator.event_callback = None
        orchestrator._expansion_tasks = {}

        # 14 epics -> 3 workers (14/6=2.33, ceil=3)
        epics = [
            {"id": uuid4(), "name": f"Epic {i}", "description": "desc", "priority": i}
            for i in range(14)
        ]

        mock_db = AsyncMock()
        mock_db.get_epics_needing_expansion = AsyncMock(side_effect=[epics, epics])  # Still unexpanded after errors

        async def mock_expansion_worker(**kwargs):
            raise RuntimeError(f"Worker {kwargs.get('worker_id')} failed")

        with patch('server.agent.orchestrator.DatabaseManager') as MockDBManager:
            MockDBManager.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            MockDBManager.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(orchestrator, '_run_expansion_worker', side_effect=mock_expansion_worker):
                result = await orchestrator._run_parallel_expansion(
                    project_id=uuid4(),
                    project_path=Path("/tmp/test"),
                    project_type="greenfield",
                    project_sandbox_type="local",
                    initializer_model="claude-3-opus",
                    num_workers=4,
                )

                assert result["workers"] == 3  # 14/6 = 3 workers
                assert result["epics_expanded"] == 0
                assert len(result["errors"]) == 3


# ============================================================
# Stop Session Tests for Expansion Workers
# ============================================================

@pytest.mark.unit
class TestStopExpansionSession:
    """Tests for stopping expansion worker sessions."""

    @pytest.mark.asyncio
    async def test_stop_session_finds_expansion_task(self):
        """Test that stop_session can cancel expansion worker tasks."""
        orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
        orchestrator.config = Config()
        orchestrator.event_callback = None
        orchestrator.session_managers = {}
        orchestrator._expansion_tasks = {}

        # Create a mock asyncio task
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()

        session_id = uuid4()
        orchestrator._expansion_tasks[str(session_id)] = mock_task

        mock_db = AsyncMock()
        mock_db.end_session = AsyncMock()

        with patch('server.agent.orchestrator.DatabaseManager') as MockDBManager:
            MockDBManager.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            MockDBManager.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await orchestrator.stop_session(session_id)

        assert result is True
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_session_returns_false_for_unknown(self):
        """Test stop_session returns False for unknown session IDs."""
        orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
        orchestrator.config = Config()
        orchestrator.event_callback = None
        orchestrator.session_managers = {}
        orchestrator._expansion_tasks = {}

        result = await orchestrator.stop_session(uuid4())
        assert result is False


# ============================================================
# API Parameter Tests
# ============================================================

@pytest.mark.unit
class TestAPIParallelExpansion:
    """Tests for API endpoint parallel_expansion parameter."""

    def test_initialize_endpoint_accepts_parallel_expansion(self):
        """Verify the initialize endpoint has parallel_expansion parameter."""
        from server.api.app import initialize_project
        import inspect
        sig = inspect.signature(initialize_project)
        assert 'parallel_expansion' in sig.parameters
        assert sig.parameters['parallel_expansion'].default is None
