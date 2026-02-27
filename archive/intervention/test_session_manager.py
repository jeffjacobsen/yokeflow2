"""
Tests for Session Manager with Intervention System
===================================================

Comprehensive tests for pause/resume functionality including:
- Database persistence
- Session state management
- Intervention tracking
- Resume prompt generation
- Auto-recovery logic
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4, UUID
from datetime import datetime

from server.agent.session_manager import PausedSessionManager, AutoRecoveryManager
from server.agent.intervention import InterventionManager


class TestPausedSessionManager:
    """Test the PausedSessionManager class."""

    @pytest.mark.asyncio
    async def test_pause_session_basic(self):
        """Test basic session pausing functionality."""
        manager = PausedSessionManager()

        session_id = str(uuid4())
        project_id = str(uuid4())

        # Mock the database
        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            paused_id = uuid4()
            mock_db.pause_session = AsyncMock(return_value=paused_id)

            # Pause session
            result = await manager.pause_session(
                session_id=session_id,
                project_id=project_id,
                reason="Test pause",
                pause_type="manual"
            )

            # Verify
            assert result == str(paused_id)
            mock_db.pause_session.assert_called_once()

            # Check call arguments
            call_args = mock_db.pause_session.call_args
            assert call_args.kwargs['session_id'] == UUID(session_id)
            assert call_args.kwargs['project_id'] == UUID(project_id)
            assert call_args.kwargs['reason'] == "Test pause"
            assert call_args.kwargs['pause_type'] == "manual"

    @pytest.mark.asyncio
    async def test_pause_session_with_intervention_manager(self):
        """Test pausing with intervention manager stats."""
        manager = PausedSessionManager()

        session_id = str(uuid4())
        project_id = str(uuid4())

        # Create intervention manager with stats
        intervention_mgr = InterventionManager()
        intervention_mgr.retry_tracker.command_counts = {"test_cmd": 5}
        intervention_mgr.blocker_detector.detected_blockers = [{
            "type": "test_blocker",
            "message": "Test error message"
        }]

        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            paused_id = uuid4()
            mock_db.pause_session = AsyncMock(return_value=paused_id)

            # Pause with intervention stats
            result = await manager.pause_session(
                session_id=session_id,
                project_id=project_id,
                reason="Retry limit exceeded",
                pause_type="retry_limit",
                intervention_manager=intervention_mgr
            )

            # Verify stats were included
            call_args = mock_db.pause_session.call_args
            assert call_args.kwargs['blocker_info'] == {
                "type": "test_blocker",
                "message": "Test error message"
            }
            assert 'retry_stats' in call_args.kwargs

    @pytest.mark.asyncio
    async def test_pause_session_with_current_task(self):
        """Test pausing with current task information."""
        manager = PausedSessionManager()

        session_id = str(uuid4())
        project_id = str(uuid4())

        current_task = {
            "id": 123,
            "name": "Implement feature X"
        }

        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            paused_id = uuid4()
            mock_db.pause_session = AsyncMock(return_value=paused_id)

            # Pause with task info
            result = await manager.pause_session(
                session_id=session_id,
                project_id=project_id,
                reason="Test pause",
                pause_type="manual",
                current_task=current_task,
                message_count=42
            )

            # Verify task info was included
            call_args = mock_db.pause_session.call_args
            assert call_args.kwargs['current_task_id'] == 123
            assert call_args.kwargs['current_task_description'] == "Implement feature X"
            assert call_args.kwargs['message_count'] == 42

    @pytest.mark.asyncio
    async def test_resume_session_success(self):
        """Test successful session resumption."""
        manager = PausedSessionManager()

        paused_session_id = str(uuid4())
        session_id = uuid4()
        project_id = uuid4()

        # Mock database responses
        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            # Mock paused session data
            paused_session_data = {
                "id": paused_session_id,
                "session_id": session_id,
                "project_id": project_id,
                "pause_reason": "Test pause",
                "pause_type": "manual",
                "current_task_id": 123,
                "current_task_description": "Test task",
                "resolved": False
            }

            project_data = {
                "id": project_id,
                "name": "Test Project",
                "local_path": "/tmp/test-project"
            }

            mock_db.get_paused_session = AsyncMock(return_value=paused_session_data)
            mock_db.get_project = AsyncMock(return_value=project_data)
            mock_db.set_pause_resume_prompt = AsyncMock()
            mock_db.resume_session = AsyncMock(return_value=True)

            # Resume session
            result = await manager.resume_session(
                paused_session_id=paused_session_id,
                resolved_by="test_user",
                resolution_notes="Fixed the issue"
            )

            # Verify result
            assert result["session_id"] == str(session_id)
            assert result["project_id"] == str(project_id)
            assert result["project_name"] == "Test Project"
            assert result["project_path"] == "/tmp/test-project"
            assert result["resolution_notes"] == "Fixed the issue"
            assert "resume_prompt" in result

            # Verify database calls
            mock_db.get_paused_session.assert_called_once()
            mock_db.get_project.assert_called_once()
            mock_db.set_pause_resume_prompt.assert_called_once()
            mock_db.resume_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_session_not_found(self):
        """Test resuming non-existent session fails."""
        manager = PausedSessionManager()

        paused_session_id = str(uuid4())

        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            mock_db.get_paused_session = AsyncMock(return_value=None)

            # Should raise ValueError
            with pytest.raises(ValueError, match="Paused session not found"):
                await manager.resume_session(paused_session_id=paused_session_id)

    @pytest.mark.asyncio
    async def test_resume_session_already_resolved(self):
        """Test resuming already resolved session fails."""
        manager = PausedSessionManager()

        paused_session_id = str(uuid4())

        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            paused_session_data = {
                "id": paused_session_id,
                "resolved": True  # Already resolved
            }

            mock_db.get_paused_session = AsyncMock(return_value=paused_session_data)

            # Should raise ValueError
            with pytest.raises(ValueError, match="Session already resolved"):
                await manager.resume_session(paused_session_id=paused_session_id)

    @pytest.mark.asyncio
    async def test_get_active_pauses_no_filter(self):
        """Test getting all active pauses."""
        manager = PausedSessionManager()

        active_pauses = [
            {"id": str(uuid4()), "project_name": "Project 1"},
            {"id": str(uuid4()), "project_name": "Project 2"}
        ]

        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            mock_db.get_active_pauses = AsyncMock(return_value=active_pauses)

            result = await manager.get_active_pauses()

            assert len(result) == 2
            assert result == active_pauses
            mock_db.get_active_pauses.assert_called_once_with(project_id=None)

    @pytest.mark.asyncio
    async def test_get_active_pauses_with_filter(self):
        """Test getting active pauses for specific project."""
        manager = PausedSessionManager()

        project_id = str(uuid4())
        active_pauses = [
            {"id": str(uuid4()), "project_id": project_id, "project_name": "Project 1"}
        ]

        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            mock_db.get_active_pauses = AsyncMock(return_value=active_pauses)

            result = await manager.get_active_pauses(project_id=project_id)

            assert len(result) == 1
            assert result[0]["project_id"] == project_id

            # Verify UUID conversion
            call_args = mock_db.get_active_pauses.call_args
            assert call_args.kwargs['project_id'] == UUID(project_id)

    @pytest.mark.asyncio
    async def test_get_intervention_history(self):
        """Test getting intervention history."""
        manager = PausedSessionManager()

        project_id = str(uuid4())
        history = [
            {"id": str(uuid4()), "resolved_at": datetime.now().isoformat()},
            {"id": str(uuid4()), "resolved_at": datetime.now().isoformat()}
        ]

        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            mock_db.get_intervention_history = AsyncMock(return_value=history)

            result = await manager.get_intervention_history(
                project_id=project_id,
                limit=10
            )

            assert len(result) == 2
            assert result == history

            call_args = mock_db.get_intervention_history.call_args
            assert call_args.kwargs['project_id'] == UUID(project_id)
            assert call_args.kwargs['limit'] == 10

    @pytest.mark.asyncio
    async def test_can_auto_resume_true(self):
        """Test can_auto_resume returns True when allowed."""
        manager = PausedSessionManager()

        paused_session_id = str(uuid4())

        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            paused_session_data = {
                "id": paused_session_id,
                "resolved": False,
                "can_auto_resume": True
            }

            mock_db.get_paused_session = AsyncMock(return_value=paused_session_data)

            result = await manager.can_auto_resume(paused_session_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_can_auto_resume_false(self):
        """Test can_auto_resume returns False when not allowed."""
        manager = PausedSessionManager()

        paused_session_id = str(uuid4())

        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            paused_session_data = {
                "id": paused_session_id,
                "resolved": False,
                "can_auto_resume": False
            }

            mock_db.get_paused_session = AsyncMock(return_value=paused_session_data)

            result = await manager.can_auto_resume(paused_session_id)

            assert result is False

    @pytest.mark.asyncio
    async def test_can_auto_resume_already_resolved(self):
        """Test can_auto_resume returns False for resolved session."""
        manager = PausedSessionManager()

        paused_session_id = str(uuid4())

        with patch('server.agent.session_manager.DatabaseManager') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value.__aenter__.return_value = mock_db

            paused_session_data = {
                "id": paused_session_id,
                "resolved": True,
                "can_auto_resume": True
            }

            mock_db.get_paused_session = AsyncMock(return_value=paused_session_data)

            result = await manager.can_auto_resume(paused_session_id)

            assert result is False

    def test_generate_resume_prompt(self):
        """Test resume prompt generation."""
        manager = PausedSessionManager()

        paused_session = {
            "pause_reason": "Retry limit exceeded",
            "current_task_description": "Implement feature X",
            "blocker_info": {
                "type": "redis_not_running"
            }
        }

        prompt = manager._generate_resume_prompt(
            paused_session,
            resolution_notes="Started Redis service"
        )

        # Verify prompt contains key information
        assert "Session Resume" in prompt
        assert "Retry limit exceeded" in prompt
        assert "Started Redis service" in prompt
        assert "Implement feature X" in prompt
        assert "redis_not_running" in prompt


class TestAutoRecoveryManager:
    """Test the AutoRecoveryManager class."""

    def test_recovery_actions_registered(self):
        """Test that recovery actions are registered."""
        manager = AutoRecoveryManager()

        expected_actions = [
            "port_conflict",
            "redis_not_running",
            "database_connection_failed",
            "module_not_found"
        ]

        for action in expected_actions:
            assert action in manager.recovery_actions

    @pytest.mark.asyncio
    async def test_attempt_recovery_no_handler(self):
        """Test recovery attempt with no handler."""
        manager = AutoRecoveryManager()

        from pathlib import Path
        project_path = Path("/tmp/test-project")

        success, message = await manager.attempt_recovery(
            blocker_type="unknown_blocker",
            project_path=project_path,
            details={}
        )

        assert success is False
        assert "No auto-recovery available" in message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
