"""
Tests for Input Validation Framework
=====================================

Tests for server/api/validation.py covering all validation models and rules.
"""

import pytest
from pydantic import ValidationError
from server.api.validation import (
    # Request models
    ProjectCreateRequest,
    SessionStartRequest,
    ProjectRenameRequest,
    EnvConfigRequest,
    LoginRequest,
    # Config validators
    ModelConfigValidator,
    TimingConfigValidator,
    SecurityConfigValidator,
    DatabaseConfigValidator,
    ProjectConfigValidator,
    VerificationConfigValidator,
    ConfigValidator,
    # Spec validator
    SpecFileValidator,
    # Helper functions
    validate_config_dict,
    validate_spec_file_content,
    validate_project_name,
)


# =============================================================================
# Project Creation Validation Tests
# =============================================================================

class TestProjectCreateRequest:
    """Tests for ProjectCreateRequest validation."""

    def test_valid_project_create(self):
        """Test valid project creation request."""
        request = ProjectCreateRequest(
            name="my-project",
            spec_content="This is a test specification with enough content.",
            force=False
        )
        assert request.name == "my-project"
        assert request.force is False

    def test_valid_project_name_formats(self):
        """Test various valid project name formats."""
        valid_names = [
            "project",
            "my-project",
            "my_project",
            "project123",
            "my.project",
            "MY-PROJECT",
            "test_project_123"
        ]
        for name in valid_names:
            request = ProjectCreateRequest(
                name=name,
                spec_content="Valid spec content here"
            )
            assert request.name == name

    def test_invalid_project_names(self):
        """Test invalid project names are rejected."""
        invalid_names = [
            "my project",  # spaces
            "my/project",  # slashes
            "my@project",  # special chars
            "my#project",
            "",  # empty
        ]
        for name in invalid_names:
            with pytest.raises(ValidationError) as exc_info:
                ProjectCreateRequest(
                    name=name,
                    spec_content="Valid spec"
                )
            # Check that validation error mentions the name
            assert "name" in str(exc_info.value).lower()

    def test_project_name_too_long(self):
        """Test project name length limit."""
        long_name = "a" * 101  # MAX_PROJECT_NAME_LENGTH is 100
        with pytest.raises(ValidationError):
            ProjectCreateRequest(
                name=long_name,
                spec_content="Valid spec"
            )

    def test_spec_content_too_short(self):
        """Test spec content minimum length."""
        with pytest.raises(ValidationError):
            ProjectCreateRequest(
                name="test",
                spec_content="short"  # Less than 10 characters
            )

    def test_no_spec_provided(self):
        """Test that either spec_content or spec_source is required."""
        with pytest.raises(ValidationError) as exc_info:
            ProjectCreateRequest(name="test")
        assert "spec" in str(exc_info.value).lower()

    def test_spec_source_provided(self):
        """Test that spec_source is accepted."""
        request = ProjectCreateRequest(
            name="test",
            spec_source="/path/to/spec.txt"
        )
        assert request.spec_source == "/path/to/spec.txt"


# =============================================================================
# Session Start Validation Tests
# =============================================================================

class TestSessionStartRequest:
    """Tests for SessionStartRequest validation."""

    def test_valid_session_start(self):
        """Test valid session start request."""
        request = SessionStartRequest(
            initializer_model="claude-opus-4-6",
            coding_model="claude-sonnet-4-6",
            max_iterations=10,
            auto_continue=True
        )
        assert request.max_iterations == 10
        assert request.auto_continue is True

    def test_valid_model_names(self):
        """Test valid Claude model name formats."""
        valid_models = [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        ]
        for model in valid_models:
            request = SessionStartRequest(
                initializer_model=model,
                auto_continue=False
            )
            assert request.initializer_model == model

    def test_invalid_model_names(self):
        """Test invalid model names are rejected."""
        invalid_models = [
            "gpt-4",
            "claude",
            "claude-invalid",
            "claude-opus",  # Missing version
            "invalid-model-name",
        ]
        for model in invalid_models:
            with pytest.raises(ValidationError) as exc_info:
                SessionStartRequest(initializer_model=model)
            assert "model" in str(exc_info.value).lower()

    def test_max_iterations_validation(self):
        """Test max_iterations boundaries."""
        # Valid
        request = SessionStartRequest(max_iterations=1)
        assert request.max_iterations == 1

        request = SessionStartRequest(max_iterations=1000)
        assert request.max_iterations == 1000

        # Invalid - zero
        with pytest.raises(ValidationError):
            SessionStartRequest(max_iterations=0)

        # Invalid - negative
        with pytest.raises(ValidationError):
            SessionStartRequest(max_iterations=-1)

        # Invalid - too large
        with pytest.raises(ValidationError):
            SessionStartRequest(max_iterations=1001)

    def test_defaults(self):
        """Test default values."""
        request = SessionStartRequest()
        assert request.auto_continue is True
        assert request.max_iterations is None
        assert request.initializer_model is None


# =============================================================================
# Environment Configuration Tests
# =============================================================================

class TestEnvConfigRequest:
    """Tests for EnvConfigRequest validation."""

    def test_valid_env_vars(self):
        """Test valid environment variable names."""
        valid_vars = {
            "API_KEY": "value1",
            "DATABASE_URL": "value2",
            "PORT": "3000",
            "_PRIVATE": "secret",
            "VAR_123": "test"
        }
        request = EnvConfigRequest(env_vars=valid_vars)
        assert request.env_vars == valid_vars

    def test_invalid_env_var_names(self):
        """Test invalid environment variable names are rejected."""
        invalid_cases = [
            {"lowercase": "value"},  # Must be uppercase
            {"123_VAR": "value"},  # Can't start with digit
            {"VAR-NAME": "value"},  # No hyphens
            {"VAR NAME": "value"},  # No spaces
        ]
        for env_vars in invalid_cases:
            with pytest.raises(ValidationError) as exc_info:
                EnvConfigRequest(env_vars=env_vars)
            assert "invalid" in str(exc_info.value).lower()


# =============================================================================
# Configuration Validation Tests
# =============================================================================

class TestModelConfigValidator:
    """Tests for ModelConfigValidator."""

    def test_valid_model_config(self):
        """Test valid model configuration."""
        config = ModelConfigValidator(
            initializer="claude-opus-4-6",
            coding="claude-sonnet-4-6"
        )
        assert config.initializer == "claude-opus-4-6"
        assert config.coding == "claude-sonnet-4-6"

    def test_defaults(self):
        """Test default model values."""
        config = ModelConfigValidator()
        assert "claude" in config.initializer.lower()
        assert "claude" in config.coding.lower()

    def test_invalid_model_name(self):
        """Test invalid model names are rejected."""
        with pytest.raises(ValidationError):
            ModelConfigValidator(initializer="gpt-4")


class TestTimingConfigValidator:
    """Tests for TimingConfigValidator."""

    def test_valid_timing_config(self):
        """Test valid timing configuration."""
        config = TimingConfigValidator(
            auto_continue_delay=5,
            web_ui_poll_interval=10,
            web_ui_port=3001
        )
        assert config.auto_continue_delay == 5
        assert config.web_ui_poll_interval == 10
        assert config.web_ui_port == 3001

    def test_defaults(self):
        """Test default timing values."""
        config = TimingConfigValidator()
        assert config.auto_continue_delay == 3
        assert config.web_ui_poll_interval == 5
        assert config.web_ui_port == 3010

    def test_invalid_delays(self):
        """Test invalid delay values are rejected."""
        # Too small
        with pytest.raises(ValidationError):
            TimingConfigValidator(auto_continue_delay=0)

        # Too large
        with pytest.raises(ValidationError):
            TimingConfigValidator(auto_continue_delay=301)

    def test_invalid_port(self):
        """Test invalid port numbers are rejected."""
        # Too small (below 1024)
        with pytest.raises(ValidationError):
            TimingConfigValidator(web_ui_port=80)

        # Too large
        with pytest.raises(ValidationError):
            TimingConfigValidator(web_ui_port=70000)


class TestDatabaseConfigValidator:
    """Tests for DatabaseConfigValidator."""

    def test_valid_database_url(self):
        """Test valid PostgreSQL URLs."""
        valid_urls = [
            "postgresql://user:pass@localhost:5432/db",
            "postgres://user:pass@host:5432/db",
            "postgresql://localhost/db",
        ]
        for url in valid_urls:
            config = DatabaseConfigValidator(database_url=url)
            assert config.database_url == url

    def test_invalid_database_url(self):
        """Test invalid database URLs are rejected."""
        invalid_urls = [
            "mysql://user:pass@localhost:3306/db",
            "http://localhost:5432",
            "invalid_url",
        ]
        for url in invalid_urls:
            with pytest.raises(ValidationError):
                DatabaseConfigValidator(database_url=url)


class TestVerificationConfigValidator:
    """Tests for VerificationConfigValidator."""

    def test_valid_verification_config(self):
        """Test valid verification configuration."""
        config = VerificationConfigValidator(
            enabled=True,
            max_retries=5,
            test_timeout=60,
            min_test_coverage=0.9
        )
        assert config.enabled is True
        assert config.max_retries == 5
        assert config.min_test_coverage == 0.9

    def test_coverage_boundaries(self):
        """Test test coverage validation boundaries."""
        # Valid boundaries
        config = VerificationConfigValidator(min_test_coverage=0.0)
        assert config.min_test_coverage == 0.0

        config = VerificationConfigValidator(min_test_coverage=1.0)
        assert config.min_test_coverage == 1.0

        # Invalid - too high
        with pytest.raises(ValidationError):
            VerificationConfigValidator(min_test_coverage=1.1)

        # Invalid - negative
        with pytest.raises(ValidationError):
            VerificationConfigValidator(min_test_coverage=-0.1)

    def test_error_rate_threshold_boundaries(self):
        """Test error rate threshold validation."""
        # Valid
        config = VerificationConfigValidator(error_rate_threshold=0.15)
        assert config.error_rate_threshold == 0.15

        # Invalid
        with pytest.raises(ValidationError):
            VerificationConfigValidator(error_rate_threshold=1.5)

    def test_valid_webhook_url(self):
        """Test webhook URL validation."""
        valid_urls = [
            "https://example.com/webhook",
            "http://localhost:8080/hook",
        ]
        for url in valid_urls:
            config = VerificationConfigValidator(webhook_url=url)
            assert config.webhook_url == url

    def test_invalid_webhook_url(self):
        """Test invalid webhook URLs are rejected."""
        with pytest.raises(ValidationError):
            VerificationConfigValidator(webhook_url="ftp://invalid.com")


class TestConfigValidator:
    """Tests for complete configuration validation."""

    def test_valid_full_config(self):
        """Test valid complete configuration."""
        config = ConfigValidator(
            models=ModelConfigValidator(),
            timing=TimingConfigValidator(),
            database=DatabaseConfigValidator(),
        )
        assert config.models is not None
        assert config.timing is not None

    def test_defaults(self):
        """Test default configuration."""
        config = ConfigValidator()
        assert config.models.initializer is not None
        assert config.timing.auto_continue_delay == 3

    def test_partial_config(self):
        """Test partial configuration with defaults."""
        config_dict = {
            "models": {
                "coding": "claude-sonnet-4-6"
            },
            "timing": {
                "auto_continue_delay": 5
            }
        }
        config = validate_config_dict(config_dict)
        assert config.models.coding == "claude-sonnet-4-6"
        assert config.timing.auto_continue_delay == 5
        # Should still have defaults for other fields
        assert config.database.database_url is not None


# =============================================================================
# Spec File Validation Tests
# =============================================================================

class TestSpecFileValidator:
    """Tests for SpecFileValidator."""

    def test_valid_spec_file(self):
        """Test valid specification file content."""
        content = """
        Project Description
        ===================

        This is a comprehensive project specification with enough detail
        to describe the application we want to build.

        Features:
        - Feature 1
        - Feature 2
        - Feature 3
        """
        spec = SpecFileValidator(content=content)
        assert spec.content == content

    def test_spec_too_short(self):
        """Test spec file minimum length."""
        with pytest.raises(ValidationError):
            SpecFileValidator(content="Too short")

    def test_spec_too_few_lines(self):
        """Test spec file minimum line count."""
        with pytest.raises(ValidationError):
            SpecFileValidator(content="Line 1\nLine 2\n" + " " * 100)

    def test_spec_missing_description(self):
        """Test spec file requires description section."""
        content = """
        Some random content here.
        More content.
        Even more content that doesn't describe anything.
        Just filler text to meet the length requirement.
        """ * 3
        with pytest.raises(ValidationError) as exc_info:
            SpecFileValidator(content=content)
        assert "description" in str(exc_info.value).lower()

    def test_spec_with_various_description_keywords(self):
        """Test spec file accepts various description keywords."""
        keywords = ["description", "overview", "purpose", "goal", "summary"]
        for keyword in keywords:
            content = f"""
            {keyword.title()}
            {'-' * len(keyword)}

            This is a valid specification file with a proper {keyword} section.
            It contains enough content to pass validation.
            """ * 2
            spec = SpecFileValidator(content=content)
            assert spec.content == content


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestHelperFunctions:
    """Tests for validation helper functions."""

    def test_validate_project_name_valid(self):
        """Test validate_project_name with valid names."""
        valid_names = ["project", "my-project", "test_123"]
        for name in valid_names:
            result = validate_project_name(name)
            assert result == name

    def test_validate_project_name_invalid(self):
        """Test validate_project_name with invalid names."""
        with pytest.raises(ValueError):
            validate_project_name("")

        with pytest.raises(ValueError):
            validate_project_name("a" * 101)

        with pytest.raises(ValueError):
            validate_project_name("invalid name")

    def test_validate_spec_file_content_valid(self):
        """Test validate_spec_file_content with valid content."""
        content = """
        Project Overview
        ================

        This is a comprehensive specification with enough detail.
        """ * 3
        spec = validate_spec_file_content(content)
        assert spec.content == content

    def test_validate_spec_file_content_invalid(self):
        """Test validate_spec_file_content with invalid content."""
        with pytest.raises(ValidationError):
            validate_spec_file_content("Too short")

    def test_validate_config_dict(self):
        """Test validate_config_dict with valid dictionary."""
        config_dict = {
            "models": {
                "initializer": "claude-opus-4-6"
            },
            "timing": {
                "auto_continue_delay": 5
            }
        }
        config = validate_config_dict(config_dict)
        assert config.models.initializer == "claude-opus-4-6"
        assert config.timing.auto_continue_delay == 5


# =============================================================================
# Integration Tests
# =============================================================================

class TestValidationIntegration:
    """Integration tests for validation framework."""

    def test_full_project_creation_flow(self):
        """Test complete project creation validation flow."""
        # Valid project creation
        request = ProjectCreateRequest(
            name="test-project",
            spec_content="""
            Project Description
            ===================

            This is a test project with sufficient detail.
            """ * 3,
            force=False
        )
        assert request.name == "test-project"

    def test_full_session_start_flow(self):
        """Test complete session start validation flow."""
        request = SessionStartRequest(
            initializer_model="claude-opus-4-6",
            coding_model="claude-sonnet-4-6",
            max_iterations=10,
            auto_continue=True
        )
        assert request.max_iterations == 10

    def test_full_config_validation_flow(self):
        """Test complete configuration validation flow."""
        config_dict = {
            "models": {
                "initializer": "claude-opus-4-6",
                "coding": "claude-sonnet-4-6"
            },
            "timing": {
                "auto_continue_delay": 5,
                "web_ui_port": 3001
            }
        }
        config = validate_config_dict(config_dict)
        assert config.models.initializer == "claude-opus-4-6"
        assert config.timing.auto_continue_delay == 5
