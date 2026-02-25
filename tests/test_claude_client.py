"""
Test suite for the Claude SDK Client.

Tests the Claude client configuration including:
- MCP environment setup
- Client creation with various configurations
- Security hook integration
- Authentication handling
"""

import os
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call
import pytest
import uuid
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.client.claude import create_client, get_mcp_env


class TestMCPEnvironment:
    """Test suite for MCP environment configuration."""

    def test_get_mcp_env_with_database_url(self, tmp_path):
        """Test MCP environment creation with DATABASE_URL set."""
        os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/testdb"
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        env = get_mcp_env(project_dir, project_id="test-uuid")

        assert env["DATABASE_URL"] == "postgresql://test:test@localhost:5432/testdb"
        assert env["PROJECT_ID"] == "test-uuid"
        assert "DOCKER_CONTAINER_NAME" not in env

    def test_get_mcp_env_without_database_url(self, tmp_path):
        """Test that MCP environment creation fails without DATABASE_URL."""
        # Temporarily remove DATABASE_URL
        original = os.environ.pop("DATABASE_URL", None)
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        try:
            with pytest.raises(ValueError) as excinfo:
                get_mcp_env(project_dir)
            assert "DATABASE_URL environment variable is required" in str(excinfo.value)
        finally:
            # Restore DATABASE_URL if it existed
            if original:
                os.environ["DATABASE_URL"] = original

    def test_get_mcp_env_generates_project_id(self, tmp_path):
        """Test that MCP environment generates project ID from project name."""
        os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/testdb"
        project_dir = tmp_path / "my_awesome_project"
        project_dir.mkdir()

        env = get_mcp_env(project_dir)  # No project_id provided

        # Should generate a deterministic UUID based on project name
        expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "my_awesome_project"))
        assert env["PROJECT_ID"] == expected_uuid


class TestClaudeClient:
    """Test suite for Claude SDK client creation."""

    @pytest.fixture
    def mock_oauth_token(self):
        """Mock get_oauth_token to return a test token."""
        with patch('server.client.claude.get_oauth_token') as mock:
            mock.return_value = "test-oauth-token"
            yield mock

    @pytest.fixture
    def mock_load_dotenv(self):
        """Mock load_dotenv to prevent loading actual .env files."""
        with patch('dotenv.load_dotenv') as mock:
            yield mock

    @pytest.fixture
    def mock_claude_sdk(self):
        """Mock ClaudeSDKClient to prevent actual SDK creation."""
        with patch('server.client.claude.ClaudeSDKClient') as mock:
            yield mock

    @pytest.fixture
    def setup_environment(self, tmp_path):
        """Set up test environment with necessary paths."""
        # Create project directory
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Create mock MCP server at the correct location
        mcp_server_dir = Path(__file__).parent.parent / "mcp-task-manager" / "dist"
        mcp_server_dir.mkdir(parents=True, exist_ok=True)
        mcp_server_file = mcp_server_dir / "index.js"
        mcp_server_file.write_text("// Mock MCP server")

        # Set DATABASE_URL
        os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/testdb"

        # Clean up any existing API key
        os.environ.pop("ANTHROPIC_API_KEY", None)

        return project_dir

    def test_create_client_basic(self, setup_environment, mock_oauth_token, mock_load_dotenv, mock_claude_sdk):
        """Test basic client creation."""
        project_dir = setup_environment

        client = create_client(
            project_dir=project_dir,
            model="claude-sonnet-4-6",
            project_id="test-uuid"
        )

        # Verify ClaudeSDKClient was called
        mock_claude_sdk.assert_called_once()

        # Verify options passed to ClaudeSDKClient
        call_args = mock_claude_sdk.call_args
        options = call_args.kwargs['options']

        assert options.model == "claude-sonnet-4-6"
        assert options.permission_mode == "bypassPermissions"
        assert options.max_turns == 1000
        assert options.max_buffer_size == 10485760  # 10MB
        assert str(project_dir.resolve()) in str(options.cwd)

    def test_create_client_mcp_servers(self, setup_environment, mock_oauth_token, mock_load_dotenv, mock_claude_sdk):
        """Test client creation configures MCP servers correctly."""
        project_dir = setup_environment

        client = create_client(
            project_dir=project_dir,
            model="claude-sonnet-4-6",
            project_id="test-uuid",
        )

        # Verify ClaudeSDKClient was called
        mock_claude_sdk.assert_called_once()

        # Verify MCP servers configuration
        call_args = mock_claude_sdk.call_args
        options = call_args.kwargs['options']
        mcp_servers = options.mcp_servers

        # Should have task-manager only
        assert "task-manager" in mcp_servers

    def test_create_client_removes_api_key(self, setup_environment, mock_oauth_token, mock_load_dotenv, mock_claude_sdk):
        """Test that client creation removes ANTHROPIC_API_KEY if set."""
        project_dir = setup_environment

        # Set ANTHROPIC_API_KEY (simulating leaked key from generated app)
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"

        # Should succeed and remove the key
        client = create_client(
            project_dir=project_dir,
            model="claude-sonnet-4-6",
            project_id="test-uuid"
        )

        # Verify the key was removed from environment
        assert "ANTHROPIC_API_KEY" not in os.environ

        # Verify ClaudeSDKClient was called
        mock_claude_sdk.assert_called_once()

        # Verify the SDK environment explicitly clears ANTHROPIC_API_KEY
        call_args = mock_claude_sdk.call_args
        options = call_args.kwargs['options']
        sdk_env = options.env
        assert sdk_env["ANTHROPIC_API_KEY"] == ""  # Explicitly cleared

    def test_create_client_mcp_server_not_found(self, tmp_path, mock_oauth_token, mock_load_dotenv):
        """Test that client creation fails if MCP server verification fails."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Set DATABASE_URL
        os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/testdb"

        # Mock verify_mcp_server to return failure (simulates missing/broken build)
        with patch("server.client.claude.verify_mcp_server") as mock_verify:
            mock_verify.return_value = {
                "ok": False,
                "message": "MCP server not found at /fake/path",
                "rebuilt": False,
            }
            with pytest.raises(FileNotFoundError) as excinfo:
                create_client(
                    project_dir=project_dir,
                    model="claude-sonnet-4-6",
                    project_id="test-uuid"
                )

            assert "verification failed" in str(excinfo.value)
            assert "npm install && npm run build" in str(excinfo.value)

    def test_create_client_hooks_configured(self, setup_environment, mock_oauth_token, mock_load_dotenv, mock_claude_sdk):
        """Test that security hooks are properly configured."""
        project_dir = setup_environment

        client = create_client(
            project_dir=project_dir,
            model="claude-sonnet-4-6",
            project_id="test-uuid"
        )

        # Verify hooks configuration
        call_args = mock_claude_sdk.call_args
        options = call_args.kwargs['options']
        hooks = options.hooks

        assert "PreToolUse" in hooks
        pre_tool_use_hooks = hooks["PreToolUse"]

        # Should have security hook for Bash commands
        assert len(pre_tool_use_hooks) == 1

        # Security hook (matches Bash)
        assert pre_tool_use_hooks[0].matcher == "Bash"

        # Verify the hook is the bash_security_hook
        from server.utils.security import bash_security_hook
        assert bash_security_hook in pre_tool_use_hooks[0].hooks

    def test_create_client_oauth_token_in_env(self, setup_environment, mock_oauth_token, mock_load_dotenv, mock_claude_sdk):
        """Test that OAuth token is properly set in environment."""
        project_dir = setup_environment

        client = create_client(
            project_dir=project_dir,
            model="claude-sonnet-4-6",
            project_id="test-uuid"
        )

        # Verify OAuth token was set in environment
        assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == "test-oauth-token"

        # Verify SDK environment configuration
        call_args = mock_claude_sdk.call_args
        options = call_args.kwargs['options']
        sdk_env = options.env

        assert sdk_env["CLAUDE_CODE_OAUTH_TOKEN"] == "test-oauth-token"
        assert sdk_env["ANTHROPIC_API_KEY"] == ""  # Explicitly cleared

    def test_create_client_system_prompt(self, setup_environment, mock_oauth_token, mock_load_dotenv, mock_claude_sdk):
        """Test that system prompt is properly set."""
        project_dir = setup_environment

        client = create_client(
            project_dir=project_dir,
            model="claude-sonnet-4-6",
            project_id="test-uuid"
        )

        # Verify system prompt
        call_args = mock_claude_sdk.call_args
        options = call_args.kwargs['options']

        expected_prompt = "You are an expert full-stack developer building a production-quality web application."
        assert options.system_prompt == expected_prompt


def run_tests():
    """Run the test suite."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()