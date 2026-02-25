"""
Tests for Brownfield Validation Models
========================================

Tests for ImportProjectRequest in server/api/validation.py.
"""

import pytest
from pydantic import ValidationError

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from server.api.validation import ImportProjectRequest


@pytest.mark.unit
class TestImportProjectRequest:
    """Tests for ImportProjectRequest validation."""

    def test_valid_github_import(self):
        """Test valid GitHub import request."""
        req = ImportProjectRequest(
            name="my-brownfield-project",
            source_url="https://github.com/user/repo.git",
            branch="main",
            change_spec_content="Add dark mode support to the application",
        )
        assert req.name == "my-brownfield-project"
        assert req.source_url == "https://github.com/user/repo.git"
        assert req.branch == "main"
        assert req.source_path is None

    def test_valid_local_import(self):
        """Test valid local path import request."""
        req = ImportProjectRequest(
            name="local-project",
            source_path="/home/user/my-existing-app",
            change_spec_content="Refactor the authentication module",
        )
        assert req.source_path == "/home/user/my-existing-app"
        assert req.source_url is None

    def test_valid_ssh_url(self):
        """Test valid SSH git URL."""
        req = ImportProjectRequest(
            name="ssh-project",
            source_url="git@github.com:user/repo.git",
            change_spec_content="Some changes here",
        )
        assert req.source_url == "git@github.com:user/repo.git"

    def test_invalid_no_source(self):
        """Test that no source raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ImportProjectRequest(
                name="no-source-project",
                change_spec_content="Some changes here",
            )
        errors = exc_info.value.errors()
        assert any("source" in str(e).lower() for e in errors)

    def test_invalid_both_sources(self):
        """Test that providing both sources raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ImportProjectRequest(
                name="both-sources",
                source_url="https://github.com/user/repo.git",
                source_path="/home/user/project",
                change_spec_content="Some changes here",
            )
        errors = exc_info.value.errors()
        assert any("source" in str(e).lower() or "both" in str(e).lower() for e in errors)

    def test_invalid_url_format(self):
        """Test that invalid URL format is rejected."""
        with pytest.raises(ValidationError):
            ImportProjectRequest(
                name="bad-url",
                source_url="not-a-valid-url",
                change_spec_content="Some changes here",
            )

    def test_invalid_relative_path(self):
        """Test that relative path is rejected."""
        with pytest.raises(ValidationError):
            ImportProjectRequest(
                name="relative-path",
                source_path="relative/path/to/project",
                change_spec_content="Some changes here",
            )

    def test_invalid_project_name(self):
        """Test that invalid project name is rejected."""
        with pytest.raises(ValidationError):
            ImportProjectRequest(
                name="my project with spaces",
                source_url="https://github.com/user/repo.git",
                change_spec_content="Some changes here",
            )

    def test_defaults(self):
        """Test default values are applied correctly."""
        req = ImportProjectRequest(
            name="defaults-test",
            source_url="https://github.com/user/repo.git",
            change_spec_content="Some changes here",
        )
        assert req.branch == "main"
        assert req.initializer_model is None
        assert req.coding_model is None

    def test_custom_models(self):
        """Test custom model overrides."""
        req = ImportProjectRequest(
            name="custom-models",
            source_url="https://github.com/user/repo.git",
            change_spec_content="Some changes here",
            initializer_model="claude-opus-4-6",
            coding_model="claude-sonnet-4-6",
        )
        assert req.initializer_model == "claude-opus-4-6"
        assert req.coding_model == "claude-sonnet-4-6"

    def test_change_spec_too_short(self):
        """Test that very short change spec is rejected."""
        with pytest.raises(ValidationError):
            ImportProjectRequest(
                name="short-spec",
                source_url="https://github.com/user/repo.git",
                change_spec_content="Fix",  # Too short (min 10 chars)
            )

    def test_change_spec_optional(self):
        """Test that change spec content is optional."""
        req = ImportProjectRequest(
            name="no-spec",
            source_url="https://github.com/user/repo.git",
        )
        assert req.change_spec_content is None
