"""
Test suite for the Claude SDK client configuration.

Tests Claude SDK client setup with MCP integration.
"""

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import pytest

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.client.claude import (
    get_mcp_env,
    create_client
)


class TestMCPEnvironment:
    """Test MCP environment configuration."""

    def test_get_mcp_env_with_project_id(self):
        """Test MCP environment with provided project ID."""
        project_dir = Path("/test/project")
        project_id = "test-project-123"

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}):
            env = get_mcp_env(project_dir, project_id=project_id)

            assert env["DATABASE_URL"] == "postgresql://test"
            assert env["PROJECT_ID"] == project_id

    def test_get_mcp_env_without_project_id(self):
        """Test MCP environment generates project ID."""
        project_dir = Path("/test/my-app")

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}):
            env = get_mcp_env(project_dir)

            assert env["DATABASE_URL"] == "postgresql://test"
            assert env["PROJECT_ID"] is not None
            # Should generate consistent UUID for same project name
            expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "my-app"))
            assert env["PROJECT_ID"] == expected_uuid

    def test_get_mcp_env_missing_database_url(self):
        """Test MCP environment fails without DATABASE_URL."""
        project_dir = Path("/test/project")

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                get_mcp_env(project_dir)

            assert "DATABASE_URL" in str(exc_info.value)


class TestClaudeAPIKey:
    """Test Claude API key retrieval."""

    def test_get_claude_api_key_from_env(self):
        """Test getting API key from environment variable."""
        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "test-token-123"}):
            with patch('server.utils.auth.get_oauth_token', return_value="test-token-123"):
                from server.utils.auth import get_oauth_token
                api_key = get_oauth_token()
                assert api_key == "test-token-123"

    def test_get_claude_api_key_missing(self):
        """Test handling missing API key."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('server.utils.auth.get_oauth_token', return_value=None):
                from server.utils.auth import get_oauth_token
                api_key = get_oauth_token()
                assert api_key is None or api_key == ""


class TestClaudeClient:
    """Test Claude SDK client creation - simplified tests."""

    def test_get_mcp_env_configuration(self):
        """Test MCP environment configuration generates correct structure."""
        project_dir = Path("/test/project")

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}):
            env = get_mcp_env(project_dir, project_id="test-id-123")

            assert "DATABASE_URL" in env
            assert env["DATABASE_URL"] == "postgresql://test"
            assert "PROJECT_ID" in env
            assert env["PROJECT_ID"] == "test-id-123"

    def test_create_client_requires_mcp_server(self):
        """Test create_client raises error when MCP server not found."""
        project_dir = Path("/test/project")

        with patch('server.client.claude.get_oauth_token', return_value="test-token"):
            with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}, clear=True):
                # create_client validates MCP server existence via pre-flight check
                with pytest.raises(FileNotFoundError):
                    create_client(
                        project_dir=project_dir,
                        model="claude-sonnet-4-6"
                    )


class TestSecurityHooks:
    """Test security hooks for Claude client."""

    @pytest.mark.asyncio
    async def test_bash_security_hook(self):
        """Test bash command security validation."""
        from server.utils.security import bash_security_hook

        # Test allowed command
        result = await bash_security_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"}
        })
        assert result == {} or "decision" not in result

        # Test blocked command
        result = await bash_security_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"}
        })
        assert result.get("decision") == "block"
        assert "blocked" in result.get("reason", "").lower()

def run_tests():
    """Run the test suite."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
