"""
Test suite for the Agent Session Logic.

Tests the core agent interaction functions including:
- SessionManager for graceful shutdown
- run_agent_session for agent execution
- Signal handling and interruption
- Progress callbacks and intervention
- Error handling and recovery
"""

import asyncio
import signal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call
import pytest
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.agent.agent import (
    SessionManager,
    run_agent_session,
    AUTO_CONTINUE_DELAY_SECONDS
)
from server.utils.errors import (
    SessionError,
    ToolExecutionError,
    ClaudeAPIError
)


class TestSessionManager:
    """Test suite for SessionManager signal handling."""

    @pytest.fixture
    def session_manager(self):
        """Create a SessionManager instance."""
        return SessionManager()

    def test_session_manager_init(self, session_manager):
        """Test SessionManager initialization."""
        assert session_manager.interrupted == False
        assert session_manager.current_logger is None
        assert session_manager._original_sigint is None
        assert session_manager._original_sigterm is None

    def test_setup_handlers(self, session_manager):
        """Test setting up signal handlers."""
        with patch('signal.signal') as mock_signal:
            session_manager.setup_handlers()

            # Should register both SIGINT and SIGTERM
            calls = mock_signal.call_args_list
            assert len(calls) == 2
            assert calls[0][0][0] == signal.SIGINT
            assert calls[1][0][0] == signal.SIGTERM

    def test_restore_handlers(self, session_manager):
        """Test restoring original signal handlers."""
        original_sigint = Mock()
        original_sigterm = Mock()
        session_manager._original_sigint = original_sigint
        session_manager._original_sigterm = original_sigterm

        with patch('signal.signal') as mock_signal:
            session_manager.restore_handlers()

            # Should restore both handlers
            calls = mock_signal.call_args_list
            assert len(calls) == 2
            assert calls[0] == call(signal.SIGINT, original_sigint)
            assert calls[1] == call(signal.SIGTERM, original_sigterm)

    def test_handle_interrupt_first_time(self, session_manager):
        """Test handling first interrupt signal."""
        mock_logger = Mock()
        mock_logger.finalize = Mock()
        session_manager.current_logger = mock_logger

        with pytest.raises(KeyboardInterrupt) as excinfo:
            session_manager._handle_interrupt(signal.SIGINT, None)

        assert session_manager.interrupted == True
        assert "Session interrupted" in str(excinfo.value)
        mock_logger.finalize.assert_called_once_with("interrupted", "Session interrupted by user")

    def test_handle_interrupt_second_time(self, session_manager):
        """Test handling second interrupt signal (force exit)."""
        session_manager.interrupted = True  # Already interrupted once

        with pytest.raises(KeyboardInterrupt) as excinfo:
            session_manager._handle_interrupt(signal.SIGINT, None)

        assert "Force interrupt" in str(excinfo.value)

    def test_handle_interrupt_no_logger(self, session_manager):
        """Test handling interrupt without active logger."""
        session_manager.current_logger = None

        with pytest.raises(KeyboardInterrupt) as excinfo:
            session_manager._handle_interrupt(signal.SIGINT, None)

        assert session_manager.interrupted == True
        assert "Session interrupted" in str(excinfo.value)

    def test_handle_interrupt_logger_error(self, session_manager):
        """Test handling interrupt when logger finalize fails."""
        mock_logger = Mock()
        mock_logger.finalize = Mock(side_effect=Exception("Logger error"))
        session_manager.current_logger = mock_logger

        with pytest.raises(KeyboardInterrupt) as excinfo:
            session_manager._handle_interrupt(signal.SIGINT, None)

        # Should still raise KeyboardInterrupt even if logger fails
        assert "Session interrupted" in str(excinfo.value)

    def test_set_current_logger(self, session_manager):
        """Test setting the current active logger."""
        mock_logger = Mock()
        session_manager.set_current_logger(mock_logger)
        assert session_manager.current_logger == mock_logger

        session_manager.set_current_logger(None)
        assert session_manager.current_logger is None


class TestRunAgentSession:
    """Test suite for run_agent_session function."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Claude SDK client."""
        client = AsyncMock()
        client.query = AsyncMock()
        # Don't make receive_response an AsyncMock - we'll override it in each test
        client.receive_response = Mock()
        return client

    @pytest.fixture
    def mock_logger(self):
        """Create a mock session logger."""
        logger = Mock()
        logger.session_id = "test-session-id"
        logger.project_id = "test-project-id"
        logger.log_prompt = Mock()
        logger.log_assistant_text = Mock()
        logger.log_tool_use = Mock()
        logger.log_error = Mock()
        logger.log_result_message = Mock()
        logger.finalize = Mock()
        return logger

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a test project directory."""
        project = tmp_path / "test_project"
        project.mkdir()
        return project

    @pytest.mark.asyncio
    async def test_run_agent_session_basic(self, mock_client, mock_logger, project_dir):
        """Test basic agent session execution."""
        # Setup mock response
        text_block = Mock()
        text_block.text = "Task completed successfully"

        assistant_msg = Mock()
        assistant_msg.content = [text_block]
        type(assistant_msg).__name__ = "AssistantMessage"
        type(text_block).__name__ = "TextBlock"

        result_msg = Mock()
        result_msg.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0
        }
        result_msg.total_cost_usd = 0.01
        type(result_msg).__name__ = "ResultMessage"

        # Create an async generator function
        async def async_response_generator():
            yield assistant_msg
            yield result_msg

        # Mock receive_response to return the async generator
        mock_client.receive_response.return_value = async_response_generator()

        status, response, session_summary = await run_agent_session(
            client=mock_client,
            message="Test prompt",
            project_dir=project_dir,
            logger=mock_logger,
            verbose=False
        )

        assert response == "Task completed successfully"
        assert status == "continue"
        mock_client.query.assert_called_once_with("Test prompt")
        mock_logger.log_prompt.assert_called_once_with("Test prompt")
        mock_logger.log_assistant_text.assert_called_once_with("Task completed successfully")

    @pytest.mark.asyncio
    async def test_run_agent_session_with_tool_use(self, mock_client, mock_logger, project_dir):
        """Test agent session with tool use."""
        # Setup mock tool use block
        tool_block = Mock()
        tool_block.name = "mcp__task-manager__get_next_task"
        tool_block.id = "tool-123"
        tool_block.input = {"project_id": "test-project"}
        type(tool_block).__name__ = "ToolUseBlock"

        assistant_msg = Mock()
        assistant_msg.content = [tool_block]
        type(assistant_msg).__name__ = "AssistantMessage"

        # Create an async generator function
        async def async_response_generator():
            yield assistant_msg

        # Mock receive_response to return the async generator
        mock_client.receive_response.return_value = async_response_generator()

        status, response, session_summary = await run_agent_session(
            client=mock_client,
            message="Get next task",
            project_dir=project_dir,
            logger=mock_logger,
            verbose=False
        )

        mock_logger.log_tool_use.assert_called_once_with(
            "mcp__task-manager__get_next_task",
            "tool-123",
            {"project_id": "test-project"}
        )

    @pytest.mark.asyncio
    async def test_run_agent_session_with_interruption(self, mock_client, mock_logger, project_dir):
        """Test agent session handling interruption."""
        session_manager = SessionManager()
        session_manager.interrupted = True  # Simulate interruption

        # Create a generator that yields messages
        async def mock_response():
            # This should trigger interruption check
            yield Mock()  # Dummy message

        mock_client.receive_response.return_value = mock_response()

        with pytest.raises(KeyboardInterrupt) as excinfo:
            await run_agent_session(
                client=mock_client,
                message="Test prompt",
                project_dir=project_dir,
                logger=mock_logger,
                verbose=False,
                session_manager=session_manager
            )

        assert "Session stopped by user" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_run_agent_session_with_credit_error(self, mock_client, mock_logger, project_dir):
        """Test handling credit balance error."""
        text_block = Mock()
        text_block.text = "Credit balance is too low to use this model"

        assistant_msg = Mock()
        assistant_msg.content = [text_block]
        type(assistant_msg).__name__ = "AssistantMessage"
        type(text_block).__name__ = "TextBlock"

        # Create an async generator function
        async def async_response_generator():
            yield assistant_msg

        # Mock receive_response to return the async generator
        mock_client.receive_response.return_value = async_response_generator()

        with pytest.raises(RuntimeError) as excinfo:
            await run_agent_session(
                client=mock_client,
                message="Test prompt",
                project_dir=project_dir,
                logger=mock_logger,
                verbose=False
            )

        assert "Credit balance is too low" in str(excinfo.value)
        mock_logger.log_error.assert_called()

    @pytest.mark.asyncio
    async def test_run_agent_session_with_progress_callback(self, mock_client, mock_logger, project_dir):
        """Test agent session with progress callback."""
        progress_events = []

        async def progress_callback(event):
            progress_events.append(event)

        text_block = Mock()
        text_block.text = "Working on task"

        assistant_msg = Mock()
        assistant_msg.content = [text_block]
        type(assistant_msg).__name__ = "AssistantMessage"
        type(text_block).__name__ = "TextBlock"

        # Create an async generator function
        async def async_response_generator():
            yield assistant_msg

        # Mock receive_response to return the async generator
        mock_client.receive_response.return_value = async_response_generator()

        status, response, session_summary = await run_agent_session(
            client=mock_client,
            message="Test prompt",
            project_dir=project_dir,
            logger=mock_logger,
            verbose=False,
            progress_callback=progress_callback
        )

        # Progress callback would be called for real events
        # In this test, we're mainly verifying it doesn't break

    @pytest.mark.asyncio
    async def test_run_agent_session_verbose_mode(self, mock_client, mock_logger, project_dir, capsys):
        """Test agent session in verbose mode."""
        text_block = Mock()
        text_block.text = "Verbose output message"

        assistant_msg = Mock()
        assistant_msg.content = [text_block]
        type(assistant_msg).__name__ = "AssistantMessage"
        type(text_block).__name__ = "TextBlock"

        result_msg = Mock()
        result_msg.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0
        }
        result_msg.total_cost_usd = 0.01
        type(result_msg).__name__ = "ResultMessage"

        # Create an async generator function
        async def async_response_generator():
            yield assistant_msg
            yield result_msg

        # Mock receive_response to return the async generator
        mock_client.receive_response.return_value = async_response_generator()

        status, response, session_summary = await run_agent_session(
            client=mock_client,
            message="Test prompt",
            project_dir=project_dir,
            logger=mock_logger,
            verbose=True
        )

        # Check that verbose output was printed
        captured = capsys.readouterr()
        assert "Sending prompt to Claude Agent SDK" in captured.out
        assert "Verbose output message" in captured.out
        assert "[Usage]" in captured.out
        assert "[Cost]" in captured.out

    # REMOVED: test_run_agent_session_task_verification
    # This test was for the old server.verification module which has been removed in v2.1

    @pytest.mark.asyncio
    async def test_run_agent_session_exception_handling(self, mock_client, mock_logger, project_dir):
        """Test agent session handling unexpected exceptions."""
        mock_client.query.side_effect = Exception("Unexpected error")

        # Generic exceptions are caught and returned as error status
        status, response, session_summary = await run_agent_session(
            client=mock_client,
            message="Test prompt",
            project_dir=project_dir,
            logger=mock_logger,
            verbose=False
        )

        assert status == "error"
        assert "Unexpected error" in response
        mock_logger.log_error.assert_called_once()


class TestAutoContDelay:
    """Test auto-continue delay configuration."""

    def test_auto_continue_delay_constant(self):
        """Test that auto-continue delay constant is defined."""
        assert AUTO_CONTINUE_DELAY_SECONDS == 3
        assert isinstance(AUTO_CONTINUE_DELAY_SECONDS, int)


def run_tests():
    """Run the test suite."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()