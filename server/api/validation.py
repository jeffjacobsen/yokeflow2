"""
Input Validation Framework
===========================

Pydantic models and validators for all API inputs, configuration files,
and specification files. Provides comprehensive validation with clear
error messages and sensible defaults.

Design Principles:
- Fail fast with clear error messages
- Provide sensible defaults where appropriate
- Type safety for all inputs
- Support for custom validators
- Integration with FastAPI automatic validation
"""

from typing import Optional, List, Dict, Any
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.types import PositiveInt, NonNegativeFloat
from enum import Enum
import re


# =============================================================================
# Enums and Constants
# =============================================================================

class SessionType(str, Enum):
    """Session types."""
    INITIALIZATION = "initialization"
    CODING = "coding"


class SessionStatus(str, Enum):
    """Session status values."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    """Task status values."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


# Model name patterns (Claude model names)
# Matches: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5, claude-opus-4-6-20260101
VALID_MODEL_PATTERN = re.compile(
    r"^claude-(opus|sonnet|haiku)-\d+-\d+(-\d{8})?$"
)

# Project name constraints
MAX_PROJECT_NAME_LENGTH = 100
VALID_PROJECT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


# =============================================================================
# API Request Models
# =============================================================================

class ProjectCreateRequest(BaseModel):
    """Request model for creating a new project with validation."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROJECT_NAME_LENGTH,
        description="Unique project name (alphanumeric, hyphens, underscores, dots)"
    )
    spec_content: Optional[str] = Field(
        None,
        min_length=10,
        description="Specification content (at least 10 characters)"
    )
    spec_source: Optional[str] = Field(
        None,
        description="Path to spec file (if uploading)"
    )
    force: bool = Field(
        False,
        description="Overwrite existing project if it exists"
    )

    @field_validator('name')
    @classmethod
    def validate_project_name(cls, v: str) -> str:
        """Validate project name format."""
        if not VALID_PROJECT_NAME_PATTERN.match(v):
            raise ValueError(
                f"Project name must contain only alphanumeric characters, "
                f"hyphens, underscores, and dots. Got: {v}"
            )
        return v

    @model_validator(mode='after')
    def validate_spec_provided(self):
        """Ensure either spec_content or spec_source is provided."""
        if not self.spec_content and not self.spec_source:
            raise ValueError(
                "Either 'spec_content' or 'spec_source' must be provided"
            )
        return self


class ImportProjectRequest(BaseModel):
    """Request model for importing an existing codebase (brownfield project)."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROJECT_NAME_LENGTH,
        description="Unique project name (alphanumeric, hyphens, underscores, dots)"
    )
    source_url: Optional[str] = Field(
        None,
        description="Git repository URL (HTTPS or SSH)"
    )
    source_path: Optional[str] = Field(
        None,
        description="Local filesystem path to existing codebase"
    )
    branch: str = Field(
        "main",
        description="Git branch to import from"
    )
    change_spec_content: Optional[str] = Field(
        None,
        min_length=10,
        description="Description of changes to make (at least 10 characters)"
    )
    initializer_model: Optional[str] = None
    coding_model: Optional[str] = None

    @field_validator('name')
    @classmethod
    def validate_project_name(cls, v: str) -> str:
        """Validate project name format."""
        if not VALID_PROJECT_NAME_PATTERN.match(v):
            raise ValueError(
                f"Project name must contain only alphanumeric characters, "
                f"hyphens, underscores, and dots. Got: {v}"
            )
        return v

    @field_validator('source_url')
    @classmethod
    def validate_source_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate git repository URL format."""
        if v is None:
            return v
        if not (v.startswith('https://') or v.startswith('git@') or v.startswith('ssh://')):
            raise ValueError(
                "Source URL must be a valid git URL (https://, git@, or ssh://)"
            )
        return v

    @field_validator('source_path')
    @classmethod
    def validate_source_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate source path is absolute."""
        if v is None:
            return v
        if not Path(v).is_absolute():
            raise ValueError("Source path must be an absolute path")
        return v

    @model_validator(mode='after')
    def validate_exactly_one_source(self):
        """Ensure exactly one of source_url or source_path is provided."""
        has_url = self.source_url is not None
        has_path = self.source_path is not None
        if not has_url and not has_path:
            raise ValueError(
                "Either 'source_url' or 'source_path' must be provided"
            )
        if has_url and has_path:
            raise ValueError(
                "Provide only one of 'source_url' or 'source_path', not both"
            )
        return self


class SessionStartRequest(BaseModel):
    """Request model for starting a session with validation."""
    initializer_model: Optional[str] = Field(
        None,
        description="Model for initialization session (must be Claude model)"
    )
    coding_model: Optional[str] = Field(
        None,
        description="Model for coding sessions (must be Claude model)"
    )
    max_iterations: Optional[PositiveInt] = Field(
        None,
        description="Maximum sessions to run (None = unlimited if auto_continue enabled)",
        le=1000  # Reasonable upper limit
    )
    auto_continue: bool = Field(
        True,
        description="Auto-continue to next session after completion"
    )

    @field_validator('initializer_model', 'coding_model')
    @classmethod
    def validate_model_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate Claude model name format."""
        if v is None:
            return v

        if not VALID_MODEL_PATTERN.match(v):
            raise ValueError(
                f"Invalid Claude model name: {v}. "
                f"Expected format: claude-(opus|sonnet|haiku)-X-X-YYYYMMDD "
                f"or claude-(opus|sonnet|haiku)-X-X"
            )
        return v


class ParallelCodingRequest(BaseModel):
    """Request model for starting parallel coding sessions."""
    num_workers: int = Field(
        2,
        ge=1,
        le=4,
        description="Number of concurrent agent workers (1-4)"
    )
    coding_model: Optional[str] = Field(
        None,
        description="Model for coding sessions (must be Claude model)"
    )
    max_tasks_per_worker: Optional[int] = Field(
        None,
        ge=1,
        le=100,
        description="Maximum tasks per worker (None = unlimited)"
    )

    @field_validator('coding_model')
    @classmethod
    def validate_model_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate Claude model name format."""
        if v is None:
            return v
        if not VALID_MODEL_PATTERN.match(v):
            raise ValueError(
                f"Invalid Claude model name: {v}. "
                f"Expected format: claude-(opus|sonnet|haiku)-X-X-YYYYMMDD "
                f"or claude-(opus|sonnet|haiku)-X-X"
            )
        return v


class ProjectRenameRequest(BaseModel):
    """Request model for renaming a project."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROJECT_NAME_LENGTH,
        description="New project name"
    )

    @field_validator('name')
    @classmethod
    def validate_project_name(cls, v: str) -> str:
        """Validate project name format."""
        if not VALID_PROJECT_NAME_PATTERN.match(v):
            raise ValueError(
                f"Project name must contain only alphanumeric characters, "
                f"hyphens, underscores, and dots. Got: {v}"
            )
        return v


class EnvConfigRequest(BaseModel):
    """Request model for environment configuration."""
    env_vars: Dict[str, str] = Field(
        ...,
        description="Environment variables as key-value pairs"
    )

    @field_validator('env_vars')
    @classmethod
    def validate_env_vars(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Validate environment variable names."""
        invalid_keys = []
        for key in v.keys():
            # Check for valid env var name format
            if not re.match(r'^[A-Z_][A-Z0-9_]*$', key):
                invalid_keys.append(key)

        if invalid_keys:
            raise ValueError(
                f"Invalid environment variable names: {', '.join(invalid_keys)}. "
                f"Names must start with uppercase letter or underscore, "
                f"and contain only uppercase letters, digits, and underscores."
            )
        return v


class LoginRequest(BaseModel):
    """Request model for user login."""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=100)


class TokenResponse(BaseModel):
    """Response model for authentication token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# =============================================================================
# Configuration Validation Models
# =============================================================================

class ModelConfigValidator(BaseModel):
    """Validation model for model configuration."""
    initializer: str = Field(
        default="claude-opus-4-6",
        description="Model for initialization sessions"
    )
    coding: str = Field(
        default="claude-sonnet-4-6",
        description="Model for coding sessions"
    )

    @field_validator('initializer', 'coding')
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """Validate Claude model name format."""
        if not VALID_MODEL_PATTERN.match(v):
            raise ValueError(
                f"Invalid Claude model name: {v}. "
                f"Expected format: claude-(opus|sonnet|haiku)-X-X-YYYYMMDD"
            )
        return v


class TimingConfigValidator(BaseModel):
    """Validation model for timing configuration."""
    auto_continue_delay: PositiveInt = Field(
        default=3,
        ge=1,
        le=300,
        description="Seconds between sessions (1-300)"
    )
    web_ui_poll_interval: PositiveInt = Field(
        default=5,
        ge=1,
        le=60,
        description="Seconds for UI refresh (1-60)"
    )
    web_ui_port: PositiveInt = Field(
        default=3010,
        ge=1024,
        le=65535,
        description="Web UI port number (1024-65535)"
    )


class SecurityConfigValidator(BaseModel):
    """Validation model for security configuration."""
    additional_blocked_commands: List[str] = Field(
        default_factory=list,
        description="Additional commands to block"
    )

    @field_validator('additional_blocked_commands')
    @classmethod
    def validate_commands(cls, v: List[str]) -> List[str]:
        """Validate command format."""
        invalid_commands = []
        for cmd in v:
            # Basic validation - commands should not be empty
            if not cmd.strip():
                invalid_commands.append(cmd)

        if invalid_commands:
            raise ValueError(
                f"Invalid blocked commands: empty strings are not allowed"
            )
        return v


class DatabaseConfigValidator(BaseModel):
    """Validation model for database configuration."""
    database_url: str = Field(
        default="postgresql://agent:agent_dev_password@localhost:5432/yokeflow",
        description="PostgreSQL connection URL"
    )

    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate PostgreSQL URL format."""
        if not v.startswith(('postgresql://', 'postgres://')):
            raise ValueError(
                f"Invalid database URL: must start with 'postgresql://' or 'postgres://'"
            )
        return v


class ProjectConfigValidator(BaseModel):
    """Validation model for project configuration."""
    default_projects_dir: str = Field(
        default="projects",
        min_length=1,
        description="Directory for projects"
    )
    max_iterations: Optional[PositiveInt] = Field(
        None,
        le=10000,
        description="Maximum session count (None = unlimited)"
    )


class InterventionConfigValidator(BaseModel):
    """Validation model for intervention configuration."""
    enabled: bool = Field(
        default=False,
        description="Enable/disable intervention system"
    )
    max_retries: PositiveInt = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts before blocking (1-10)"
    )


class VerificationConfigValidator(BaseModel):
    """Validation model for verification configuration."""
    enabled: bool = Field(
        default=True,
        description="Enable/disable task verification"
    )
    auto_retry: bool = Field(
        default=True,
        description="Automatically retry failed tests"
    )
    max_retries: PositiveInt = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts for failed tests (1-10)"
    )
    test_timeout: PositiveInt = Field(
        default=30,
        ge=5,
        le=600,
        description="Timeout for individual tests in seconds (5-600)"
    )
    require_all_tests_pass: bool = Field(
        default=True,
        description="Whether all tests must pass"
    )
    min_test_coverage: NonNegativeFloat = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum required test coverage (0.0 to 1.0)"
    )

    # Test generation settings
    generate_unit_tests: bool = Field(default=True)
    generate_api_tests: bool = Field(default=True)
    generate_browser_tests: bool = Field(default=True)
    generate_integration_tests: bool = Field(default=False)

    # File tracking
    track_file_modifications: bool = Field(default=True)

    # Notification settings
    webhook_url: Optional[str] = Field(None, description="Webhook URL for notifications")

    # Auto-pause conditions
    error_rate_threshold: NonNegativeFloat = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Pause if error rate exceeds this (0.0 to 1.0)"
    )
    session_duration_limit: PositiveInt = Field(
        default=600,
        ge=60,
        le=3600,
        description="Pause after N seconds on same task (60-3600)"
    )
    detect_infrastructure_errors: bool = Field(default=True)

    @field_validator('webhook_url')
    @classmethod
    def validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate webhook URL format."""
        if v is None:
            return v

        if not v.startswith(('http://', 'https://')):
            raise ValueError(
                f"Invalid webhook URL: must start with 'http://' or 'https://'"
            )
        return v


class ConfigValidator(BaseModel):
    """Main configuration validation model."""
    models: ModelConfigValidator = Field(default_factory=ModelConfigValidator)
    timing: TimingConfigValidator = Field(default_factory=TimingConfigValidator)
    security: SecurityConfigValidator = Field(default_factory=SecurityConfigValidator)
    database: DatabaseConfigValidator = Field(default_factory=DatabaseConfigValidator)
    project: ProjectConfigValidator = Field(default_factory=ProjectConfigValidator)
    intervention: InterventionConfigValidator = Field(default_factory=InterventionConfigValidator)
    verification: VerificationConfigValidator = Field(default_factory=VerificationConfigValidator)


# =============================================================================
# Spec File Validation
# =============================================================================

class SpecFileValidator(BaseModel):
    """Validation model for specification files."""
    content: str = Field(
        ...,
        min_length=100,
        description="Specification content (at least 100 characters)"
    )

    @field_validator('content')
    @classmethod
    def validate_spec_content(cls, v: str) -> str:
        """Validate specification file content."""
        # Check for minimum meaningful content
        lines = [line.strip() for line in v.split('\n') if line.strip()]

        if len(lines) < 3:
            raise ValueError(
                "Specification must contain at least 3 non-empty lines"
            )

        # Check for common required sections (flexible)
        content_lower = v.lower()
        has_description = any(keyword in content_lower for keyword in [
            'description', 'overview', 'purpose', 'goal', 'summary'
        ])

        if not has_description:
            raise ValueError(
                "Specification should include a description or overview section. "
                "Please provide context about what the application should do."
            )

        return v


# =============================================================================
# Helper Functions
# =============================================================================

def validate_config_dict(config_dict: Dict[str, Any]) -> ConfigValidator:
    """
    Validate a configuration dictionary.

    Args:
        config_dict: Dictionary containing configuration values

    Returns:
        Validated ConfigValidator instance

    Raises:
        ValidationError: If validation fails
    """
    return ConfigValidator(**config_dict)


def validate_spec_file_content(content: str) -> SpecFileValidator:
    """
    Validate specification file content.

    Args:
        content: Specification file content

    Returns:
        Validated SpecFileValidator instance

    Raises:
        ValidationError: If validation fails
    """
    return SpecFileValidator(content=content)


def validate_project_name(name: str) -> str:
    """
    Validate a project name.

    Args:
        name: Project name to validate

    Returns:
        Validated project name

    Raises:
        ValueError: If name is invalid
    """
    if not name or len(name) > MAX_PROJECT_NAME_LENGTH:
        raise ValueError(
            f"Project name must be between 1 and {MAX_PROJECT_NAME_LENGTH} characters"
        )

    if not VALID_PROJECT_NAME_PATTERN.match(name):
        raise ValueError(
            f"Project name must contain only alphanumeric characters, "
            f"hyphens, underscores, and dots"
        )

    return name
