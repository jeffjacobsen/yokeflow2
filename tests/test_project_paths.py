"""
Tests for server/utils/project_paths.py

Verifies path resolution with backward-compatible fallback logic:
- New projects use yokeflow/specs/ and yokeflow/logs/
- Legacy projects with old-style paths still work
"""

import pytest
from pathlib import Path

from server.utils.project_paths import (
    get_specs_dir,
    get_logs_dir,
    resolve_specs_dir,
    resolve_logs_dir,
    resolve_spec_file,
)


class TestGetters:
    """Test the simple path getters."""

    def test_get_specs_dir(self, tmp_path):
        assert get_specs_dir(tmp_path) == tmp_path / "yokeflow" / "specs"

    def test_get_logs_dir(self, tmp_path):
        assert get_logs_dir(tmp_path) == tmp_path / "yokeflow" / "logs"


class TestResolveSpecsDir:
    """Test specs directory resolution with fallback."""

    def test_new_project_returns_new_path(self, tmp_path):
        """No specs anywhere → returns new-style path."""
        result = resolve_specs_dir(tmp_path)
        assert result == tmp_path / "yokeflow" / "specs"

    def test_new_path_exists_returns_new(self, tmp_path):
        """New-style path exists → returns it."""
        new_dir = tmp_path / "yokeflow" / "specs"
        new_dir.mkdir(parents=True)
        (new_dir / "my-app.md").write_text("spec content")

        assert resolve_specs_dir(tmp_path) == new_dir

    def test_legacy_spec_dir_fallback(self, tmp_path):
        """Legacy spec/ directory exists → returns it."""
        legacy_dir = tmp_path / "spec"
        legacy_dir.mkdir()
        (legacy_dir / "main.md").write_text("spec content")

        assert resolve_specs_dir(tmp_path) == legacy_dir

    def test_legacy_app_spec_fallback(self, tmp_path):
        """Legacy app_spec.txt at root → returns project root."""
        (tmp_path / "app_spec.txt").write_text("spec content")

        assert resolve_specs_dir(tmp_path) == tmp_path

    def test_new_path_takes_priority(self, tmp_path):
        """Both new and legacy exist → new wins."""
        new_dir = tmp_path / "yokeflow" / "specs"
        new_dir.mkdir(parents=True)
        (new_dir / "spec.md").write_text("new spec")
        (tmp_path / "app_spec.txt").write_text("legacy spec")

        assert resolve_specs_dir(tmp_path) == new_dir


class TestResolveLogsDir:
    """Test logs directory resolution with fallback."""

    def test_new_project_returns_new_path(self, tmp_path):
        """No logs anywhere → returns new-style path."""
        result = resolve_logs_dir(tmp_path)
        assert result == tmp_path / "yokeflow" / "logs"

    def test_new_path_exists_returns_new(self, tmp_path):
        """New-style path exists → returns it."""
        new_dir = tmp_path / "yokeflow" / "logs"
        new_dir.mkdir(parents=True)

        assert resolve_logs_dir(tmp_path) == new_dir

    def test_legacy_logs_with_sessions_fallback(self, tmp_path):
        """Legacy logs/ with session files → returns it."""
        legacy_dir = tmp_path / "logs"
        legacy_dir.mkdir()
        (legacy_dir / "session_001_20260101.jsonl").write_text("{}")

        assert resolve_logs_dir(tmp_path) == legacy_dir

    def test_legacy_logs_without_sessions_ignored(self, tmp_path):
        """Legacy logs/ without session files → returns new path (not a session log dir)."""
        legacy_dir = tmp_path / "logs"
        legacy_dir.mkdir()
        (legacy_dir / "other.log").write_text("not a session log")

        assert resolve_logs_dir(tmp_path) == tmp_path / "yokeflow" / "logs"

    def test_new_path_takes_priority(self, tmp_path):
        """Both new and legacy exist → new wins."""
        new_dir = tmp_path / "yokeflow" / "logs"
        new_dir.mkdir(parents=True)

        legacy_dir = tmp_path / "logs"
        legacy_dir.mkdir()
        (legacy_dir / "session_001_20260101.jsonl").write_text("{}")

        assert resolve_logs_dir(tmp_path) == new_dir


class TestResolveSpecFile:
    """Test individual spec file resolution."""

    def test_new_relative_path(self, tmp_path):
        """New-style relative path resolves correctly."""
        specs_dir = tmp_path / "yokeflow" / "specs"
        specs_dir.mkdir(parents=True)
        spec_file = specs_dir / "my-app.md"
        spec_file.write_text("spec content")

        result = resolve_spec_file(tmp_path, "yokeflow/specs/my-app.md")
        assert result == spec_file

    def test_legacy_absolute_path(self, tmp_path):
        """Legacy absolute path still works."""
        spec_file = tmp_path / "app_spec.txt"
        spec_file.write_text("spec content")

        result = resolve_spec_file(tmp_path, str(spec_file))
        assert result == spec_file

    def test_legacy_relative_path(self, tmp_path):
        """Legacy relative path (just filename) falls back to root."""
        spec_file = tmp_path / "change_spec.md"
        spec_file.write_text("spec content")

        result = resolve_spec_file(tmp_path, "change_spec.md")
        assert result == spec_file

    def test_legacy_absolute_not_found_tries_new(self, tmp_path):
        """Legacy absolute path doesn't exist → tries new location."""
        specs_dir = tmp_path / "yokeflow" / "specs"
        specs_dir.mkdir(parents=True)
        new_file = specs_dir / "old_spec.txt"
        new_file.write_text("migrated spec")

        result = resolve_spec_file(tmp_path, "/nonexistent/old_spec.txt")
        assert result == new_file

    def test_missing_file_returns_resolved_path(self, tmp_path):
        """File doesn't exist anywhere → returns resolved new-style path for error reporting."""
        result = resolve_spec_file(tmp_path, "yokeflow/specs/missing.md")
        assert result == tmp_path / "yokeflow" / "specs" / "missing.md"
