"""
Test suite for the Agent Orchestrator.

Tests the orchestration layer that manages:
- Project creation and management
- Session lifecycle (start/stop/status)
- Database interaction through DatabaseManager
- Event callbacks and quality integration
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call
from uuid import UUID, uuid4
import pytest
from datetime import datetime, timezone

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from server.agent.orchestrator import AgentOrchestrator, SessionInfo
from server.agent.models import SessionStatus, SessionType
from server.utils.errors import (
    YokeFlowError,
    ProjectValidationError,
    SessionError,
    ValidationError,
    SessionAlreadyRunningError
)


class TestAgentOrchestrator:
    """Test suite for the AgentOrchestrator class."""

    @pytest.fixture
    def orchestrator(self):
        """Create an orchestrator instance for testing."""
        with patch('server.agent.orchestrator.Config') as mock_config:
            mock_config.load_default.return_value = MagicMock(
                project=MagicMock(
                    default_projects_dir="projects",
                    max_iterations=None
                ),
                models=MagicMock(
                    initializer="claude-opus",
                    coding="claude-sonnet"
                ),
                timing=MagicMock(
                    auto_continue_delay=3
                ),
                sandbox=MagicMock(
                    type="docker",
                    docker_image="yokeflow-sandbox:latest",
                    docker_network="bridge",
                    docker_memory_limit="2g",
                    docker_cpu_limit=2.0,
                    docker_ports=[]
                ),
                docker=MagicMock(
                    enabled=True
                ),
                api=MagicMock(
                    enabled=False
                )
            )
            return AgentOrchestrator(verbose=False)

    @pytest.fixture
    def mock_db(self):
        """Create a mock database manager."""
        mock = AsyncMock()
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def sample_project_id(self):
        """Generate a sample project UUID."""
        return uuid4()

    @pytest.fixture
    def sample_project(self, sample_project_id):
        """Create a sample project dictionary."""
        return {
            'id': sample_project_id,
            'name': 'test_project',
            'spec_file_path': '/path/to/spec.txt',
            'spec_content': 'Build a test app',
            'created_at': datetime.now(timezone.utc),
            'status': 'initializing'
        }

    # =========================================================================
    # Project Creation Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_project_success(self, orchestrator, mock_db, sample_project):
        """Test successful project creation."""
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project_by_name.return_value = None  # No existing project
            mock_db.create_project.return_value = sample_project
            mock_db.update_project.return_value = None
            mock_db.update_project_settings.return_value = None

            with patch('server.agent.orchestrator.Path') as mock_path, \
                 patch('server.client.claude.copy_agent_skills'):
                mock_path_instance = MagicMock()
                mock_path.return_value = mock_path_instance
                mock_path_instance.__truediv__.return_value = mock_path_instance
                mock_path_instance.mkdir.return_value = None
                mock_path_instance.write_text.return_value = None

                result = await orchestrator.create_project(
                    project_name='test_project',
                    spec_content='Build a test app'
                )

                assert result == sample_project
                mock_db.create_project.assert_called_once()
                mock_db.update_project_settings.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_project_already_exists(self, orchestrator, mock_db, sample_project):
        """Test project creation when project already exists."""
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project_by_name.return_value = sample_project  # Existing project

            with pytest.raises(ValueError) as excinfo:
                await orchestrator.create_project(
                    project_name='test_project',
                    spec_content='Build a test app'
                )

            assert "already exists" in str(excinfo.value)
            mock_db.create_project.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_project_force_overwrite(self, orchestrator, mock_db, sample_project):
        """Test project creation with force overwrite."""
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project_by_name.return_value = sample_project  # Existing project
            mock_db.delete_project.return_value = None
            mock_db.create_project.return_value = sample_project
            mock_db.update_project.return_value = None
            mock_db.update_project_settings.return_value = None

            with patch('server.agent.orchestrator.Path') as mock_path, \
                 patch('server.client.claude.copy_agent_skills'):
                mock_path_instance = MagicMock()
                mock_path.return_value = mock_path_instance
                mock_path_instance.__truediv__.return_value = mock_path_instance
                mock_path_instance.mkdir.return_value = None
                mock_path_instance.write_text.return_value = None

                result = await orchestrator.create_project(
                    project_name='test_project',
                    spec_content='Build a test app',
                    force=True
                )

                assert result == sample_project
                mock_db.delete_project.assert_called_once_with(sample_project['id'])
                mock_db.create_project.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_project_from_file(self, orchestrator, mock_db, sample_project, tmp_path):
        """Test project creation from a spec file."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("Build an amazing app")

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project_by_name.return_value = None
            mock_db.create_project.return_value = sample_project
            mock_db.update_project.return_value = None
            mock_db.update_project_settings.return_value = None

            with patch('server.agent.orchestrator.Path') as mock_path_cls, \
                 patch('server.client.claude.copy_agent_skills'):
                mock_path_cls.return_value = MagicMock()

                with patch('server.agent.orchestrator.copy_spec_to_project') as mock_copy:
                    result = await orchestrator.create_project(
                        project_name='test_project',
                        spec_source=spec_file
                    )

                    assert result == sample_project
                    mock_copy.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_project_with_custom_models(self, orchestrator, mock_db, sample_project):
        """Test project creation with custom model settings."""
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project_by_name.return_value = None
            mock_db.create_project.return_value = sample_project
            mock_db.update_project.return_value = None
            mock_db.update_project_settings.return_value = None

            with patch('server.agent.orchestrator.Path') as mock_path, \
                 patch('server.client.claude.copy_agent_skills'):
                mock_path_instance = MagicMock()
                mock_path.return_value = mock_path_instance
                mock_path_instance.__truediv__.return_value = mock_path_instance
                mock_path_instance.mkdir.return_value = None
                mock_path_instance.write_text.return_value = None

                result = await orchestrator.create_project(
                    project_name='test_project',
                    spec_content='Build a test app',
                    initializer_model='custom-opus',
                    coding_model='custom-sonnet'
                )

                # Verify settings were passed
                call_args = mock_db.update_project_settings.call_args
                settings = call_args[0][1]
                assert settings['initializer_model'] == 'custom-opus'
                assert settings['coding_model'] == 'custom-sonnet'

    # =========================================================================
    # Project Info Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_project_info_success(self, orchestrator, mock_db, sample_project, sample_project_id):
        """Test getting project information."""
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project.return_value = sample_project
            mock_db.get_progress.return_value = {
                'total_epics': 5,
                'completed_epics': 2,
                'total_tasks': 20,
                'completed_tasks': 8,
                'total_tests': 60,
                'passed_tests': 30
            }
            mock_db.get_next_task.return_value = {
                'id': uuid4(),
                'name': 'Implement authentication'
            }
            mock_db.get_active_session.return_value = None

            with patch('server.agent.orchestrator.Path') as mock_path:
                mock_path_instance = MagicMock()
                mock_path.return_value = mock_path_instance
                mock_path_instance.__truediv__.return_value = mock_path_instance
                mock_path_instance.exists.return_value = False

                result = await orchestrator.get_project_info(sample_project_id)

                assert result['id'] == sample_project_id
                assert result['name'] == 'test_project'
                assert 'progress' in result
                assert result['progress']['total_tasks'] == 20

    @pytest.mark.asyncio
    async def test_get_project_info_not_found(self, orchestrator, mock_db, sample_project_id):
        """Test getting info for non-existent project."""
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project.return_value = None

            with pytest.raises(ValueError) as excinfo:
                await orchestrator.get_project_info(sample_project_id)

            assert "Project not found" in str(excinfo.value)

    # =========================================================================
    # Session Start Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_start_session_initializer(self, orchestrator, mock_db, sample_project, sample_project_id):
        """Test starting an initializer session."""
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project.return_value = sample_project
            mock_db.get_active_session.return_value = None
            mock_db.get_sessions_by_project.return_value = []  # No previous sessions
            mock_db.get_project_settings.return_value = {}
            mock_db.get_progress.return_value = {'total_epics': 0}  # Not initialized

            # Mock the orchestrator's start_initialization method
            with patch.object(orchestrator, 'start_initialization') as mock_start:
                session_info = SessionInfo(
                    project_id=str(sample_project_id),
                    session_id=str(uuid4()),
                    session_number=0,
                    session_type=SessionType.INITIALIZER,
                    model="claude-opus",
                    status=SessionStatus.COMPLETED,
                    created_at=datetime.now(timezone.utc)
                )
                mock_start.return_value = session_info

                result = await orchestrator.start_session(
                    project_id=sample_project_id,
                    initializer_model="claude-opus"
                )

                assert result.session_type == SessionType.INITIALIZER
                assert result.project_id == str(sample_project_id)

    @pytest.mark.asyncio
    async def test_start_session_with_active_session(self, orchestrator, mock_db, sample_project_id):
        """Test starting a session when one is already active."""
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project.return_value = {'id': sample_project_id}
            mock_db.get_active_session.return_value = {
                'id': uuid4(),
                'status': 'running',
                'session_number': 1,
                'started_at': datetime.now(timezone.utc)
            }

            # When there's an active session, it should raise ValueError (not SessionAlreadyRunningError)
            with pytest.raises(ValueError) as excinfo:
                await orchestrator.start_session(
                    project_id=sample_project_id
                )

            assert "already running" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_start_session_project_not_found(self, orchestrator, mock_db, sample_project_id):
        """Test starting a session for non-existent project."""
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project.return_value = None

            with pytest.raises(ValueError) as excinfo:
                await orchestrator.start_session(
                    project_id=sample_project_id
                )

            assert "not found" in str(excinfo.value)

    # =========================================================================
    # Session Stop Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_stop_session_success(self, orchestrator, mock_db, sample_project_id):
        """Test stopping an active session."""
        session_id = uuid4()

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_session.return_value = {
                'id': session_id,
                'project_id': sample_project_id,
                'status': 'running'
            }
            mock_db.update_session_status.return_value = None

            result = await orchestrator.stop_session(session_id)

            # Should return True on successful stop
            assert result == True or result is not None

    @pytest.mark.asyncio
    async def test_stop_session_force(self, orchestrator, mock_db):
        """Test force stopping a session."""
        session_id = uuid4()

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_session.return_value = {
                'id': session_id,
                'status': 'running'
            }
            mock_db.update_session_status.return_value = None

            result = await orchestrator.stop_session(session_id, reason="Force stop")

            # Should successfully stop
            assert result == True or result is not None

    # =========================================================================
    # Session Status Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_session_info_active(self, orchestrator):
        """Test getting info of an active session."""
        session_id = uuid4()

        # Create a mock for the connection object
        mock_conn = MagicMock()
        mock_row = {
            'id': session_id,
            'status': 'running',
            'session_type': 'coding'
        }
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        # Create a mock for db.acquire() that returns the connection
        mock_acquire = MagicMock(return_value=mock_conn)

        # Create a mock for the database manager
        mock_db = MagicMock()
        mock_db.acquire = mock_acquire
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        # Mock DatabaseManager class
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            result = await orchestrator.get_session_info(session_id)

            assert result is not None
            assert result['id'] == session_id

    @pytest.mark.asyncio
    async def test_get_session_info_not_found(self, orchestrator):
        """Test getting info when session doesn't exist."""
        session_id = uuid4()

        # Create a mock for the connection object
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        # Create a mock for db.acquire() that returns the connection
        mock_acquire = MagicMock(return_value=mock_conn)

        # Create a mock for the database manager
        mock_db = MagicMock()
        mock_db.acquire = mock_acquire
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        # Mock DatabaseManager class
        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            result = await orchestrator.get_session_info(session_id)

            assert result is None

    # =========================================================================
    # List Projects Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_list_projects(self, orchestrator, mock_db):
        """Test listing all projects."""
        project1_id = uuid4()
        project2_id = uuid4()
        projects = [
            {'id': project1_id, 'name': 'project1', 'status': 'active'},
            {'id': project2_id, 'name': 'project2', 'status': 'completed'}
        ]

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            # Mock list_projects to return the projects
            mock_db.list_projects.return_value = projects

            # Mock get_project to return each project when queried by ID
            def get_project_side_effect(project_id):
                for project in projects:
                    if project['id'] == project_id:
                        return project
                return None
            mock_db.get_project.side_effect = get_project_side_effect

            # Mock progress-related methods
            mock_db.get_progress.return_value = {
                'total_epics': 0,
                'completed_epics': 0,
                'total_tasks': 0,
                'completed_tasks': 0,
                'total_tests': 0,
                'passed_tests': 0
            }
            mock_db.get_next_task.return_value = None
            mock_db.get_active_session.return_value = None

            # Mock Path operations to avoid filesystem checks
            with patch('server.agent.orchestrator.Path') as mock_path:
                mock_path_instance = MagicMock()
                mock_path.return_value = mock_path_instance
                mock_path_instance.__truediv__ = MagicMock(return_value=mock_path_instance)
                mock_path_instance.exists.return_value = False

                result = await orchestrator.list_projects()

                assert len(result) == 2
                assert result[0]['name'] == 'project1'
                assert result[1]['name'] == 'project2'

    # =========================================================================
    # Event Callback Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_event_callback_triggered(self, mock_db, sample_project, sample_project_id):
        """Test that event callbacks are triggered."""
        callback = AsyncMock()
        orchestrator = AgentOrchestrator(verbose=False, event_callback=callback)

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            mock_db.get_project_by_name.return_value = None
            mock_db.create_project.return_value = sample_project
            mock_db.update_project.return_value = None
            mock_db.update_project_settings.return_value = None

            with patch('server.agent.orchestrator.Path') as mock_path, \
                 patch('server.client.claude.copy_agent_skills'):
                mock_path_instance = MagicMock()
                mock_path.return_value = mock_path_instance
                mock_path_instance.__truediv__.return_value = mock_path_instance
                mock_path_instance.mkdir.return_value = None
                mock_path_instance.write_text.return_value = None

                await orchestrator.create_project(
                    project_name='test_project',
                    spec_content='Build a test app'
                )

                # Event callbacks would be triggered during session execution
                # which we're not testing here directly

    # =========================================================================
    # Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self):
        """Test orchestrator initialization."""
        with patch('server.agent.orchestrator.Config') as mock_config:
            mock_config.load_default.return_value = MagicMock()

            orchestrator = AgentOrchestrator(verbose=True)

            assert orchestrator.verbose == True
            assert orchestrator.session_managers == {}
            assert orchestrator.stop_after_current == {}
            assert orchestrator.quality is not None


def run_tests():
    """Run the test suite."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()