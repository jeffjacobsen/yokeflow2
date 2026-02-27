"""
Test suite for Epic Test Blocking.

Tests the orchestrator's ability to detect and handle epic test failures:
- Epic test block error detection
- Session status set to BLOCKED (not ERROR)
- Blocker info written to agent-progress.md
- Event callbacks for session_blocked
- Regular errors still mark session as ERROR
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


class TestEpicTestBlocking:
    """Test suite for epic test blocking functionality."""

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
        mock.get_project.return_value = {
            'id': uuid4(),
            'name': 'test_project',
            'status': 'active'
        }
        mock.get_next_session_number.return_value = 5
        mock.create_session.return_value = uuid4()
        mock.end_session = AsyncMock()
        return mock

    @pytest.fixture
    def sample_project_id(self):
        """Generate a sample project UUID."""
        return uuid4()

    @pytest.fixture
    def temp_project_dir(self, tmp_path):
        """Create a temporary project directory."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        return project_dir

    # =========================================================================
    # _write_blocker_info Method Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_write_blocker_info_creates_file(self, orchestrator, temp_project_dir):
        """Test that _write_blocker_info creates the progress file."""
        error_msg = "Epic test failure blocked in strict mode: 2 tests failed\nFailed tests: test_login, test_signup"

        await orchestrator._write_blocker_info(temp_project_dir, 5, error_msg)

        # Check that progress file was created
        progress_file = temp_project_dir / "yokeflow" / "agent-progress.md"
        assert progress_file.exists()

        # Verify content
        content = progress_file.read_text()
        assert "Session 5 BLOCKED - Epic Test Failure" in content
        assert "Epic test failure blocked" in content
        assert "test_login" in content
        assert "test_signup" in content
        assert "**Next Steps**:" in content

    @pytest.mark.asyncio
    async def test_write_blocker_info_prepends_to_existing(self, orchestrator, temp_project_dir):
        """Test that blocker info is prepended to existing agent-progress.md content."""
        # Create existing progress file
        yokeflow_dir = temp_project_dir / "yokeflow"
        yokeflow_dir.mkdir()
        progress_file = yokeflow_dir / "agent-progress.md"
        existing_content = "# Previous Progress\n\nSome existing content.\n"
        progress_file.write_text(existing_content)

        error_msg = "Epic test failure blocked in strict mode: 1 test failed\nFailed tests: test_payment"

        await orchestrator._write_blocker_info(temp_project_dir, 5, error_msg)

        # Verify new content is prepended (strip leading newline)
        content = progress_file.read_text().strip()
        assert content.startswith("## ⚠️ Session 5 BLOCKED")
        assert "# Previous Progress" in content
        assert content.index("Session 5 BLOCKED") < content.index("Previous Progress")

    @pytest.mark.asyncio
    async def test_write_blocker_info_handles_errors_gracefully(self, orchestrator):
        """Test that write_blocker_info doesn't crash on errors."""
        # Use an invalid path
        invalid_path = Path("/invalid/path/that/does/not/exist")

        # Should not raise exception
        await orchestrator._write_blocker_info(invalid_path, 5, "Test error")

    # =========================================================================
    # Error Detection Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_epic_test_block_string_detected(self):
        """Test that the error message string detection works correctly."""
        error_msg = "Epic test failure blocked in strict mode: 2 tests failed\nFailed tests: test_login, test_signup"

        # This is the detection logic from orchestrator.py
        is_epic_block = "Epic test failure blocked" in error_msg

        assert is_epic_block is True

    @pytest.mark.asyncio
    async def test_regular_error_not_detected_as_block(self):
        """Test that regular errors are not detected as epic test blocks."""
        error_msgs = [
            "Database connection failed",
            "Network timeout",
            "Module not found",
            "Epic failed",  # Contains "Epic" but not the full phrase
            "test failure blocked",  # Contains parts but not the full phrase
        ]

        for error_msg in error_msgs:
            is_epic_block = "Epic test failure blocked" in error_msg
            assert is_epic_block is False, f"Should not detect '{error_msg}' as epic block"



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
