"""
Tests for YokeFlow error hierarchy.

Tests error creation, categorization, recoverability, and error context.
"""

import pytest
from uuid import uuid4

from server.utils.errors import (
    ErrorCategory,
    YokeFlowError,
    DatabaseError,
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseTransactionError,
    DatabasePoolExhaustedError,
    NetworkError,
    ClaudeAPIError,
    ClaudeRateLimitError,
    ClaudeAuthenticationError,
    SandboxError,
    SandboxStartError,
    SandboxStopError,
    SandboxCommandError,
    ValidationError,
    ProjectValidationError,
    SpecValidationError,
    TaskValidationError,
    ToolExecutionError,
    SecurityBlockedError,
    SessionError,
    SessionNotFoundError,
    SessionAlreadyRunningError,
    CheckpointNotFoundError,
    CheckpointInvalidError,
    InterventionError,
    PausedSessionNotFoundError,
    SessionAlreadyResolvedError,
    ResourceError,
    ResourceExhaustedError,
    PortAllocationError,
    ConfigurationError,
    MissingConfigError,
    InvalidConfigError
)


class TestBaseError:
    """Test base YokeFlowError class"""

    def test_error_creation(self):
        """Test creating a basic error"""
        error = YokeFlowError("Test error message")
        assert str(error) == "Test error message"
        assert error.recoverable is False
        assert error.error_code == "UNKNOWN"
        assert error.category == ErrorCategory.VALIDATION

    def test_error_with_recoverable(self):
        """Test error with recoverable flag"""
        error = YokeFlowError("Test error", recoverable=True)
        assert error.recoverable is True

    def test_error_with_context(self):
        """Test error with context dict"""
        context = {"key1": "value1", "key2": 42}
        error = YokeFlowError("Test error", context=context)
        assert error.context == context

    def test_error_to_dict(self):
        """Test error serialization to dict"""
        error = YokeFlowError(
            "Test error",
            recoverable=True,
            context={"detail": "test"}
        )
        error_dict = error.to_dict()

        assert error_dict["error_code"] == "UNKNOWN"
        assert error_dict["category"] == ErrorCategory.VALIDATION.value
        assert error_dict["message"] == "Test error"
        assert error_dict["recoverable"] is True
        assert error_dict["context"]["detail"] == "test"


class TestDatabaseErrors:
    """Test database error hierarchy"""

    def test_database_connection_error(self):
        """Test database connection error"""
        error = DatabaseConnectionError("Connection failed", retry_count=3)
        assert error.category == ErrorCategory.DATABASE
        assert error.error_code == "DB_CONNECTION"
        assert error.recoverable is True
        assert error.context["retry_count"] == 3

    def test_database_query_error(self):
        """Test database query error"""
        query = "SELECT * FROM invalid_table"
        error = DatabaseQueryError("Query failed", query=query)
        assert error.error_code == "DB_QUERY"
        assert error.recoverable is False
        assert error.context["query"] == query

    def test_database_transaction_error(self):
        """Test database transaction error"""
        error = DatabaseTransactionError("Transaction rollback")
        assert error.error_code == "DB_TRANSACTION"
        assert error.recoverable is True

    def test_database_pool_exhausted_error(self):
        """Test connection pool exhausted error"""
        error = DatabasePoolExhaustedError()
        assert error.error_code == "DB_POOL_EXHAUSTED"
        assert "exhausted" in str(error).lower()
        assert error.recoverable is True


class TestNetworkErrors:
    """Test network and Claude API errors"""

    def test_claude_api_error(self):
        """Test Claude API error"""
        error = ClaudeAPIError("API request failed", status_code=500)
        assert error.category == ErrorCategory.CLAUDE_API
        assert error.error_code == "CLAUDE_API"
        assert error.recoverable is True
        assert error.context["status_code"] == 500

    def test_claude_rate_limit_error(self):
        """Test Claude rate limit error"""
        error = ClaudeRateLimitError("Rate limit exceeded", retry_after=60)
        assert error.error_code == "CLAUDE_RATE_LIMIT"
        assert error.context["retry_after"] == 60

    def test_claude_authentication_error(self):
        """Test Claude authentication error"""
        error = ClaudeAuthenticationError()
        assert error.error_code == "CLAUDE_AUTH"
        assert error.recoverable is False
        assert "API key" in str(error)


class TestSandboxErrors:
    """Test sandbox error hierarchy"""

    def test_sandbox_start_error(self):
        """Test sandbox start error"""
        container_id = "abc123"
        error = SandboxStartError("Failed to start", container_id=container_id)
        assert error.category == ErrorCategory.SANDBOX
        assert error.error_code == "SANDBOX_START"
        assert error.recoverable is True
        assert error.context["container_id"] == container_id

    def test_sandbox_stop_error(self):
        """Test sandbox stop error"""
        error = SandboxStopError("Failed to stop container")
        assert error.error_code == "SANDBOX_STOP"
        assert error.recoverable is True

    def test_sandbox_command_error(self):
        """Test sandbox command execution error"""
        error = SandboxCommandError(
            "Command failed",
            command="npm install",
            exit_code=1
        )
        assert error.error_code == "SANDBOX_COMMAND"
        assert error.recoverable is False
        assert error.context["command"] == "npm install"
        assert error.context["exit_code"] == 1


class TestValidationErrors:
    """Test validation error hierarchy"""

    def test_validation_error(self):
        """Test base validation error"""
        error = ValidationError("Invalid input", field="username")
        assert error.category == ErrorCategory.VALIDATION
        assert error.error_code == "VALIDATION_ERROR"
        assert error.recoverable is False
        assert error.context["field"] == "username"

    def test_project_validation_error(self):
        """Test project validation error"""
        error = ProjectValidationError("Invalid project name")
        assert error.error_code == "PROJECT_VALIDATION"

    def test_spec_validation_error(self):
        """Test spec validation error"""
        error = SpecValidationError("Spec missing required sections")
        assert error.error_code == "SPEC_VALIDATION"

    def test_task_validation_error(self):
        """Test task validation error"""
        error = TaskValidationError("Invalid task", task_id=42)
        assert error.error_code == "TASK_VALIDATION"
        assert error.context["task_id"] == 42


class TestToolExecutionErrors:
    """Test tool execution error hierarchy"""

    def test_tool_execution_error(self):
        """Test tool execution error"""
        error = ToolExecutionError(
            "Bash",
            "Command timeout",
            recoverable=True
        )
        assert error.category == ErrorCategory.TOOL_EXECUTION
        assert error.error_code == "TOOL_ERROR"
        assert error.tool_name == "Bash"
        assert "Bash: Command timeout" in str(error)
        assert error.recoverable is True

    def test_security_blocked_error(self):
        """Test security blocked error"""
        command = "rm -rf /"
        error = SecurityBlockedError("Bash", command)
        assert error.error_code == "SECURITY_BLOCKED"
        assert error.recoverable is False
        assert error.context["blocked_command"] == command
        assert "security policy" in str(error).lower()


class TestSessionErrors:
    """Test session error hierarchy"""

    def test_session_not_found_error(self):
        """Test session not found error"""
        session_id = str(uuid4())
        error = SessionNotFoundError(session_id)
        assert error.category == ErrorCategory.SESSION
        assert error.error_code == "SESSION_NOT_FOUND"
        assert error.context["session_id"] == session_id
        assert session_id in str(error)

    def test_session_already_running_error(self):
        """Test session already running error"""
        session_id = str(uuid4())
        error = SessionAlreadyRunningError(session_id)
        assert error.error_code == "SESSION_RUNNING"
        assert error.context["session_id"] == session_id

    def test_checkpoint_not_found_error(self):
        """Test checkpoint not found error"""
        checkpoint_id = str(uuid4())
        error = CheckpointNotFoundError(checkpoint_id)
        assert error.error_code == "CHECKPOINT_NOT_FOUND"
        assert error.context["checkpoint_id"] == checkpoint_id

    def test_checkpoint_invalid_error(self):
        """Test checkpoint invalid error"""
        checkpoint_id = str(uuid4())
        reason = "State corruption detected"
        error = CheckpointInvalidError(checkpoint_id, reason)
        assert error.error_code == "CHECKPOINT_INVALID"
        assert error.context["checkpoint_id"] == checkpoint_id
        assert error.context["reason"] == reason


class TestInterventionErrors:
    """Test intervention error hierarchy"""

    def test_paused_session_not_found_error(self):
        """Test paused session not found error"""
        session_id = str(uuid4())
        error = PausedSessionNotFoundError(session_id)
        assert error.category == ErrorCategory.INTERVENTION
        assert error.error_code == "PAUSED_SESSION_NOT_FOUND"
        assert error.context["session_id"] == session_id

    def test_session_already_resolved_error(self):
        """Test session already resolved error"""
        session_id = str(uuid4())
        error = SessionAlreadyResolvedError(session_id)
        assert error.error_code == "SESSION_ALREADY_RESOLVED"
        assert error.context["session_id"] == session_id


class TestResourceErrors:
    """Test resource error hierarchy"""

    def test_resource_exhausted_error(self):
        """Test resource exhausted error"""
        error = ResourceExhaustedError("memory")
        assert error.category == ErrorCategory.RESOURCE
        assert error.error_code == "RESOURCE_EXHAUSTED"
        assert error.recoverable is True
        assert error.context["resource_type"] == "memory"

    def test_port_allocation_error(self):
        """Test port allocation error"""
        error = PortAllocationError("No ports available")
        assert error.error_code == "PORT_ALLOCATION"
        assert error.recoverable is True


class TestConfigurationErrors:
    """Test configuration error hierarchy"""

    def test_missing_config_error(self):
        """Test missing configuration error"""
        error = MissingConfigError("DATABASE_URL")
        assert error.category == ErrorCategory.CONFIGURATION
        assert error.error_code == "CONFIG_MISSING"
        assert error.recoverable is False
        assert error.context["config_key"] == "DATABASE_URL"
        assert "DATABASE_URL" in str(error)

    def test_invalid_config_error(self):
        """Test invalid configuration error"""
        error = InvalidConfigError(
            "max_retries",
            -1,
            "Must be positive"
        )
        assert error.error_code == "CONFIG_INVALID"
        assert error.recoverable is False
        assert error.context["config_key"] == "max_retries"
        assert error.context["value"] == "-1"
        assert error.context["reason"] == "Must be positive"


class TestErrorCategoryEnum:
    """Test ErrorCategory enum"""

    def test_all_categories_defined(self):
        """Test all expected categories are defined"""
        expected_categories = {
            "database",
            "network",
            "sandbox",
            "validation",
            "tool_execution",
            "session",
            "resource",
            "configuration",
            "claude_api",
            "intervention"
        }

        actual_categories = {cat.value for cat in ErrorCategory}
        assert actual_categories == expected_categories

    def test_category_string_values(self):
        """Test category enum string values"""
        assert ErrorCategory.DATABASE.value == "database"
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.SANDBOX.value == "sandbox"


class TestErrorInheritance:
    """Test error class inheritance"""

    def test_all_errors_inherit_from_base(self):
        """Test all custom errors inherit from YokeFlowError"""
        test_cases = [
            (DatabaseError, ("Test",)),
            (NetworkError, ("Test",)),
            (SandboxError, ("Test",)),
            (ValidationError, ("Test",)),
            (ToolExecutionError, ("tool_name", "Test")),
            (SessionError, ("Test",)),
            (InterventionError, ("Test",)),
            (ResourceError, ("Test",)),
            (ConfigurationError, ("Test",))
        ]

        for error_class, args in test_cases:
            error = error_class(*args)
            assert isinstance(error, YokeFlowError)
            assert isinstance(error, Exception)

    def test_specific_errors_inherit_from_base_category(self):
        """Test specific errors inherit from their category base"""
        # Database errors
        assert issubclass(DatabaseConnectionError, DatabaseError)
        assert issubclass(DatabaseQueryError, DatabaseError)

        # Claude API errors
        assert issubclass(ClaudeRateLimitError, ClaudeAPIError)
        assert issubclass(ClaudeAuthenticationError, ClaudeAPIError)

        # Sandbox errors
        assert issubclass(SandboxStartError, SandboxError)
        assert issubclass(SandboxCommandError, SandboxError)

        # Session errors
        assert issubclass(CheckpointNotFoundError, SessionError)
        assert issubclass(SessionNotFoundError, SessionError)


class TestErrorRecoverability:
    """Test error recoverability patterns"""

    def test_recoverable_errors(self):
        """Test errors that should be recoverable"""
        recoverable_errors = [
            DatabaseConnectionError("test", retry_count=1),
            DatabaseTransactionError("test"),
            ClaudeAPIError("test", status_code=500),
            SandboxStartError("test"),
            ToolExecutionError("tool", "message", recoverable=True),
            ResourceExhaustedError("memory")
        ]

        for error in recoverable_errors:
            assert error.recoverable is True, f"{type(error).__name__} should be recoverable"

    def test_non_recoverable_errors(self):
        """Test errors that should not be recoverable"""
        non_recoverable_errors = [
            DatabaseQueryError("test"),
            ClaudeAuthenticationError(),
            ValidationError("test"),
            SecurityBlockedError("tool", "command"),
            ConfigurationError("test")
        ]

        for error in non_recoverable_errors:
            assert error.recoverable is False, f"{type(error).__name__} should not be recoverable"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
