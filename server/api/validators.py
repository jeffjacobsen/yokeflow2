"""
Input Validation Helpers for YokeFlow API
==========================================

Provides reusable validators and Pydantic models for API input validation.
Ensures consistency and security across all endpoints.
"""

import re
from typing import Optional, List
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, ConfigDict
from uuid import UUID

# Constants for validation
PROJECT_NAME_PATTERN = r'^[a-z0-9_-]+$'
MAX_PROJECT_NAME_LENGTH = 255
MIN_PROJECT_NAME_LENGTH = 1
MAX_SPEC_SIZE = 1_000_000  # 1MB max for spec files
MIN_SPEC_SIZE = 50  # Minimum reasonable spec size
RESERVED_PROJECT_NAMES = {'api', 'static', 'admin', 'health', 'docs', 'test', 'config'}


class ProjectNameValidator(BaseModel):
    """Validates project names across the system."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(
        ...,
        min_length=MIN_PROJECT_NAME_LENGTH,
        max_length=MAX_PROJECT_NAME_LENGTH,
        description="Project name - lowercase letters, numbers, hyphens, underscores only"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """
        Validate project name format and check reserved names.

        Args:
            v: The project name to validate

        Returns:
            The validated name

        Raises:
            ValueError: If name is invalid
        """
        # Check pattern
        if not re.match(PROJECT_NAME_PATTERN, v):
            raise ValueError(
                f"Project name must contain only lowercase letters, numbers, "
                f"hyphens, and underscores. Got: '{v}'"
            )

        # Check reserved names
        if v.lower() in RESERVED_PROJECT_NAMES:
            raise ValueError(f"'{v}' is a reserved name and cannot be used")

        # Check for common problematic patterns
        if v.startswith('-') or v.endswith('-'):
            raise ValueError("Project name cannot start or end with a hyphen")

        if v.startswith('_') or v.endswith('_'):
            raise ValueError("Project name cannot start or end with an underscore")

        if '--' in v or '__' in v:
            raise ValueError("Project name cannot contain consecutive hyphens or underscores")

        return v


class SpecContentValidator(BaseModel):
    """Validates specification content."""

    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(
        ...,
        min_length=MIN_SPEC_SIZE,
        max_length=MAX_SPEC_SIZE,
        description="Specification content"
    )

    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """
        Validate spec content for basic requirements.

        Args:
            v: The content to validate

        Returns:
            The validated content

        Raises:
            ValueError: If content is invalid
        """
        # Check for minimum meaningful content
        stripped = v.strip()
        if len(stripped) < MIN_SPEC_SIZE:
            raise ValueError(f"Specification must be at least {MIN_SPEC_SIZE} characters")

        # Check for obviously invalid content
        if stripped.lower() in ['test', 'testing', 'placeholder', 'todo']:
            raise ValueError("Specification appears to be placeholder text")

        # Basic structure check - should have some keywords
        keywords = ['app', 'application', 'system', 'feature', 'user', 'requirement', 'build', 'create']
        if not any(keyword in stripped.lower() for keyword in keywords):
            raise ValueError(
                "Specification doesn't appear to contain valid application requirements"
            )

        return v


class SessionConfigValidator(BaseModel):
    """Validates session configuration parameters."""

    model_config = ConfigDict(str_strip_whitespace=True)

    initializer_model: Optional[str] = Field(
        default=None,
        pattern="^(claude-opus-4-6|claude-sonnet-4-6|claude-haiku-4-5).*$",
        description="Model for initialization session"
    )

    coding_model: Optional[str] = Field(
        default=None,
        pattern="^(claude-opus-4-6|claude-sonnet-4-6|claude-haiku-4-5).*$",
        description="Model for coding sessions"
    )

    max_iterations: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Maximum number of coding sessions"
    )

    auto_continue: bool = Field(
        default=True,
        description="Whether to automatically continue after each session"
    )

    auto_continue_delay: int = Field(
        default=3,
        ge=0,
        le=300,
        description="Delay in seconds between auto-continued sessions"
    )


class FileUploadValidator:
    """Validates uploaded files."""

    @staticmethod
    def validate_spec_file(filename: str, content: bytes) -> None:
        """
        Validate an uploaded spec file.

        Args:
            filename: Name of the file
            content: File content as bytes

        Raises:
            ValueError: If file is invalid
        """
        # Check file size
        size = len(content)
        if size > MAX_SPEC_SIZE:
            raise ValueError(f"File too large: {size} bytes (max {MAX_SPEC_SIZE})")

        if size < MIN_SPEC_SIZE:
            raise ValueError(f"File too small: {size} bytes (min {MIN_SPEC_SIZE})")

        # Check file extension
        valid_extensions = {'.txt', '.md', '.yaml', '.yml', '.json'}
        file_ext = Path(filename).suffix.lower()
        if file_ext and file_ext not in valid_extensions:
            raise ValueError(
                f"Invalid file type '{file_ext}'. "
                f"Allowed types: {', '.join(valid_extensions)}"
            )

        # Try to decode as text
        try:
            text_content = content.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError("File must be a valid UTF-8 text file")

        # Basic content validation
        if not text_content.strip():
            raise ValueError("File is empty or contains only whitespace")


class UUIDValidator:
    """Validates UUID parameters."""

    @staticmethod
    def validate_project_id(project_id: str) -> UUID:
        """
        Validate and convert a project ID string to UUID.

        Args:
            project_id: String representation of UUID

        Returns:
            Valid UUID object

        Raises:
            ValueError: If not a valid UUID
        """
        try:
            return UUID(project_id)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid project ID format: {project_id}") from e

    @staticmethod
    def validate_session_id(session_id: str) -> UUID:
        """
        Validate and convert a session ID string to UUID.

        Args:
            session_id: String representation of UUID

        Returns:
            Valid UUID object

        Raises:
            ValueError: If not a valid UUID
        """
        try:
            return UUID(session_id)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid session ID format: {session_id}") from e


class ResourceLimitValidator(BaseModel):
    """Validates resource limits and constraints."""

    model_config = ConfigDict(str_strip_whitespace=True)

    max_concurrent_sessions: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent sessions allowed"
    )

    max_memory_mb: int = Field(
        default=512,
        ge=128,
        le=4096,
        description="Maximum memory per session in MB"
    )

    max_cpu_percent: int = Field(
        default=50,
        ge=10,
        le=100,
        description="Maximum CPU percentage per session"
    )

    max_disk_gb: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum disk usage per project in GB"
    )


def sanitize_path(path_str: str) -> Path:
    """
    Sanitize and validate a file path to prevent directory traversal.

    Args:
        path_str: Path string to sanitize

    Returns:
        Sanitized Path object

    Raises:
        ValueError: If path is invalid or potentially dangerous
    """
    # Remove any null bytes
    clean_path = path_str.replace('\0', '')

    # Convert to Path object and resolve
    path = Path(clean_path).resolve()

    # Check for directory traversal attempts
    if '..' in str(path):
        raise ValueError("Path cannot contain '..' (directory traversal)")

    # Check for absolute paths outside project directory
    if path.is_absolute() and not str(path).startswith('/home'):
        raise ValueError("Absolute paths outside project directory not allowed")

    return path


def validate_env_var_name(name: str) -> str:
    """
    Validate environment variable name.

    Args:
        name: Environment variable name

    Returns:
        Validated name

    Raises:
        ValueError: If name is invalid
    """
    pattern = r'^[A-Z][A-Z0-9_]*$'
    if not re.match(pattern, name):
        raise ValueError(
            f"Environment variable name must be uppercase letters, "
            f"numbers, and underscores only, starting with a letter: {name}"
        )

    # Check for reserved names
    reserved = {'PATH', 'HOME', 'USER', 'SHELL', 'PWD'}
    if name in reserved:
        raise ValueError(f"'{name}' is a reserved environment variable")

    return name