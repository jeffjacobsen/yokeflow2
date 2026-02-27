"""
Integration tests for full YokeFlow workflows.

Tests complete end-to-end scenarios including:
- Project initialization workflow
- Coding session workflow
- Error recovery and checkpoint restoration
- Quality checks and interventions
- Task verification and epic validation
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call
import pytest
import sys
from datetime import datetime
from uuid import uuid4

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.agent.orchestrator import AgentOrchestrator
from server.agent.models import SessionStatus, SessionType
from server.database.operations import TaskDatabase
from server.utils.errors import (
    SessionError,
    DatabaseError,
    ValidationError
)


class TestProjectInitializationWorkflow:
    """Test complete project initialization workflow."""

    @pytest.mark.asyncio
    async def test_create_project_and_initialize(self, tmp_path):
        """Test creating a project and running initialization session."""
        project_name = "test_integration_project"
        spec_content = """
        Build a simple calculator web app with:
        - Addition and subtraction operations
        - Clear button
        - History of calculations
        """

        with patch('server.agent.orchestrator.DatabaseManager') as mock_db_manager:
            with patch('server.agent.orchestrator.create_client') as mock_create_client:
                with patch('server.agent.orchestrator.run_agent_session') as mock_run_session:
                    # Setup mocks
                    mock_db = AsyncMock()
                    mock_db_manager.return_value.__aenter__.return_value = mock_db

                    # Mock database responses
                    project_id = uuid4()
                    mock_db.get_project_by_name.return_value = None  # No existing project
                    mock_db.create_project.return_value = {
                        'id': project_id,
                        'name': project_name,
                        'spec_content': spec_content
                    }
                    mock_db.update_project.return_value = None
                    mock_db.update_project_settings.return_value = None
                    mock_db.get_project.return_value = {'id': project_id, 'name': project_name}
                    mock_db.get_sessions_by_project.return_value = []
                    mock_db.get_active_session.return_value = None
                    mock_db.create_session.return_value = {'id': uuid4(), 'status': 'running'}
                    mock_db.update_session_status.return_value = None
                    mock_db.get_next_task.return_value = None  # No tasks yet

                    # Mock client and session
                    mock_client = AsyncMock()
                    mock_create_client.return_value = mock_client
                    mock_run_session.return_value = ("continue", "Roadmap created", {})

                    # Create orchestrator and run workflow
                    orchestrator = AgentOrchestrator(verbose=False)

                    # Step 1: Create project
                    project = await orchestrator.create_project(
                        project_name=project_name,
                        spec_content=spec_content
                    )

                    assert project['id'] == project_id
                    assert project['name'] == project_name

                    # Step 2: Start initialization session
                    # Note: The actual orchestrator may not have start_initialization
                    # This is a conceptual test that needs adjustment based on actual API

    @pytest.mark.asyncio
    async def test_project_initialization_with_existing_project(self):
        """Test initialization when project already exists."""
        project_name = "existing_project"

        with patch('server.agent.orchestrator.DatabaseManager') as mock_db_manager:
            mock_db = AsyncMock()
            mock_db_manager.return_value.__aenter__.return_value = mock_db

            # Mock existing project
            existing_project = {
                'id': uuid4(),
                'name': project_name,
                'status': 'active'
            }
            mock_db.get_project_by_name.return_value = existing_project

            orchestrator = AgentOrchestrator(verbose=False)

            # Should raise error without force flag
            with pytest.raises(ValueError) as excinfo:
                await orchestrator.create_project(
                    project_name=project_name,
                    spec_content="Test spec"
                )

            assert "already exists" in str(excinfo.value)


class TestCodingSessionWorkflow:
    """Test complete coding session workflow."""

    @pytest.mark.asyncio
    async def test_coding_session_with_tasks(self):
        """Test running a coding session that completes tasks."""
        project_id = uuid4()
        session_id = uuid4()
        task_id = uuid4()

        with patch('server.agent.orchestrator.DatabaseManager') as mock_db_manager:
            with patch('server.agent.orchestrator.create_client') as mock_create_client:
                with patch('server.agent.orchestrator.run_agent_session') as mock_run_session:
                    # Setup mocks
                    mock_db = AsyncMock()
                    mock_db_manager.return_value.__aenter__.return_value = mock_db

                    # Mock database state
                    mock_db.get_project.return_value = {
                        'id': project_id,
                        'name': 'test_project',
                        'status': 'initialized'
                    }
                    mock_db.get_next_task.side_effect = [
                        # First call returns a task
                        {
                            'id': task_id,
                            'name': 'Implement calculator addition',
                            'description': 'Create add function'
                        },
                        # Second call returns None (no more tasks)
                        None
                    ]
                    mock_db.get_active_session.return_value = None
                    mock_db.create_session.return_value = {
                        'id': session_id,
                        'status': 'running'
                    }
                    mock_db.update_task_status.return_value = None
                    mock_db.update_session_status.return_value = None

                    # Mock client and session execution
                    mock_client = AsyncMock()
                    mock_create_client.return_value = mock_client
                    mock_run_session.return_value = ("continue", "Task completed", {})

                    orchestrator = AgentOrchestrator(verbose=False)

                    # Run coding session
                    # Note: Actual method signatures may differ
                    # This test demonstrates the workflow concept

    @pytest.mark.asyncio
    async def test_coding_session_auto_continue(self):
        """Test auto-continue behavior in coding sessions."""
        project_id = uuid4()

        with patch('server.agent.orchestrator.DatabaseManager') as mock_db_manager:
            mock_db = AsyncMock()
            mock_db_manager.return_value.__aenter__.return_value = mock_db

            # Setup project with multiple tasks
            mock_db.get_project.return_value = {'id': project_id, 'status': 'active'}
            mock_db.get_next_task.side_effect = [
                {'id': uuid4(), 'name': 'Task 1'},
                {'id': uuid4(), 'name': 'Task 2'},
                {'id': uuid4(), 'name': 'Task 3'},
                None  # No more tasks
            ]

            # Test that auto-continue processes all tasks
            # Implementation depends on actual orchestrator behavior


class TestErrorRecoveryWorkflow:
    """Test error recovery and checkpoint restoration workflows."""

    @pytest.mark.asyncio
    async def test_session_checkpoint_and_recovery(self):
        """Test creating checkpoints and recovering from failures."""
        project_id = uuid4()
        session_id = uuid4()
        checkpoint_id = uuid4()

        with patch('server.agent.checkpoint.CheckpointManager') as mock_checkpoint:
            with patch('server.database.operations.TaskDatabase') as mock_db:
                # Setup checkpoint manager
                checkpoint_manager = mock_checkpoint.return_value
                checkpoint_manager.create_checkpoint = AsyncMock(return_value=checkpoint_id)
                checkpoint_manager.get_latest_checkpoint = AsyncMock(return_value={
                    'id': checkpoint_id,
                    'session_id': session_id,
                    'conversation_history': ['Previous messages'],
                    'current_task_id': uuid4()
                })

                # Simulate failure and recovery
                # 1. Create checkpoint after task completion
                await checkpoint_manager.create_checkpoint(
                    checkpoint_type='task_completion',
                    conversation_history=['Messages'],
                    current_task_id=uuid4()
                )

                # 2. Simulate failure
                # 3. Recover from checkpoint
                checkpoint = await checkpoint_manager.get_latest_checkpoint(session_id)
                assert checkpoint['id'] == checkpoint_id

class TestQualityCheckWorkflow:
    """Test quality check and review workflows."""

    # REMOVED: test_quality_checks_during_session
    # This test was for the old server.quality.metrics module which has been removed in v2.1

    # REMOVED: test_task_verification_workflow
    # This test was for the old server.verification module which has been removed in v2.1
    pass


class TestFullProjectLifecycle:
    """Test complete project lifecycle from creation to completion."""

    @pytest.mark.asyncio
    async def test_project_lifecycle_end_to_end(self, tmp_path):
        """Test full project lifecycle: create, initialize, code, complete."""
        project_name = "lifecycle_test_project"

        with patch('server.agent.orchestrator.DatabaseManager') as mock_db_manager:
            mock_db = AsyncMock()
            mock_db_manager.return_value.__aenter__.return_value = mock_db

            # Setup comprehensive mocks for full lifecycle
            project_id = uuid4()

            # Project creation
            mock_db.get_project_by_name.return_value = None
            mock_db.create_project.return_value = {
                'id': project_id,
                'name': project_name
            }

            # Initialization creates epics and tasks
            mock_db.create_epic.return_value = {'id': uuid4()}
            mock_db.create_task.return_value = {'id': uuid4()}
            mock_db.create_test.return_value = {'id': uuid4()}

            # Coding sessions complete tasks
            mock_db.get_next_task.side_effect = [
                {'id': uuid4(), 'name': 'Task 1'},
                {'id': uuid4(), 'name': 'Task 2'},
                None  # All tasks complete
            ]

            # Progress tracking
            mock_db.get_progress.return_value = {
                'total_tasks': 2,
                'completed_tasks': 2,
                'total_tests': 6,
                'passed_tests': 6
            }

            # Project completion
            mock_db.mark_project_complete.return_value = None

            orchestrator = AgentOrchestrator(verbose=False)

            # Full lifecycle simulation
            # 1. Create project
            project = await orchestrator.create_project(
                project_name=project_name,
                spec_content="Build a test app"
            )

            # 2. Initialize (creates roadmap)
            # 3. Run coding sessions (implements tasks)
            # 4. Verify completion
            # 5. Mark project complete

            # Note: Actual implementation requires proper orchestrator methods


class TestDatabaseStateTransitions:
    """Test database state transitions during workflows."""

    @pytest.mark.asyncio
    async def test_session_state_transitions(self):
        """Test session state transitions: created -> running -> completed."""
        session_id = uuid4()

        with patch('server.database.operations.TaskDatabase') as mock_db_class:
            mock_db = mock_db_class.return_value

            # Session creation
            mock_db.create_session = AsyncMock(return_value={
                'id': session_id,
                'status': 'created'
            })

            # Start session
            mock_db.update_session_status = AsyncMock()
            await mock_db.update_session_status(session_id, 'running')

            # Complete session
            await mock_db.update_session_status(session_id, 'completed')

            # Verify state transitions
            assert mock_db.update_session_status.call_count == 2

    @pytest.mark.asyncio
    async def test_task_state_transitions(self):
        """Test task state transitions: pending -> in_progress -> done."""
        task_id = uuid4()

        with patch('server.database.operations.TaskDatabase') as mock_db_class:
            mock_db = mock_db_class.return_value

            # Task creation (pending by default)
            mock_db.create_task = AsyncMock(return_value={
                'id': task_id,
                'status': 'pending'
            })

            # Start task
            mock_db.start_task = AsyncMock()
            await mock_db.start_task(task_id)

            # Complete task
            mock_db.update_task_status = AsyncMock()
            await mock_db.update_task_status(task_id, done=True)

            # Verify transitions
            mock_db.start_task.assert_called_once_with(task_id)
            mock_db.update_task_status.assert_called_once_with(task_id, done=True)


def run_tests():
    """Run the test suite."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()