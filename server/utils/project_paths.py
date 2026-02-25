"""
Project Path Resolution

Centralized path resolution for project-internal directories.
All YokeFlow metadata (specs, session logs, screenshots, progress)
lives under <project>/yokeflow/ to keep a clean separation from
generated application code.

Provides backward-compatible resolution: checks new paths first,
falls back to legacy paths for existing projects.
"""

from pathlib import Path


def get_specs_dir(project_path: Path) -> Path:
    """Return the specs directory: <project>/yokeflow/specs/"""
    return project_path / "yokeflow" / "specs"


def get_logs_dir(project_path: Path) -> Path:
    """Return the session logs directory: <project>/yokeflow/logs/"""
    return project_path / "yokeflow" / "logs"


def resolve_specs_dir(project_path: Path) -> Path:
    """Resolve specs dir with backward-compatible fallback.

    New: <project>/yokeflow/specs/
    Legacy: <project>/ (spec files at project root) or <project>/spec/

    Returns the new path if it exists OR if neither exists (for new projects).
    Returns the legacy path only if legacy files exist but new path doesn't.
    """
    new_dir = get_specs_dir(project_path)
    if new_dir.exists():
        return new_dir

    # Check for legacy spec directory
    legacy_spec_dir = project_path / "spec"
    if legacy_spec_dir.is_dir():
        return legacy_spec_dir

    # Check for legacy spec files at project root
    legacy_spec = project_path / "app_spec.txt"
    if legacy_spec.exists():
        return project_path

    return new_dir


def resolve_logs_dir(project_path: Path) -> Path:
    """Resolve session logs dir with backward-compatible fallback.

    New: <project>/yokeflow/logs/
    Legacy: <project>/logs/

    Returns the new path if it exists OR if neither exists (for new projects).
    Returns the legacy path only if legacy session logs exist but new path doesn't.
    """
    new_dir = get_logs_dir(project_path)
    if new_dir.exists():
        return new_dir

    legacy_dir = project_path / "logs"
    if legacy_dir.exists() and any(legacy_dir.glob("session_*")):
        return legacy_dir

    return new_dir


def resolve_spec_file(project_path: Path, relative_path: str) -> Path:
    """Resolve a spec file path from the database.

    Handles both:
    - New relative paths: "yokeflow/specs/my-spec.md"
    - Legacy absolute paths: "/full/path/to/spec.txt"
    - Legacy relative paths: "change_spec.md" or "app_spec.txt"

    Args:
        project_path: The project's local directory
        relative_path: The spec_file_path from the database

    Returns:
        Resolved absolute path to the spec file
    """
    spec_path = Path(relative_path)

    # Legacy: absolute path stored in DB
    if spec_path.is_absolute():
        if spec_path.exists():
            return spec_path
        # Try resolving the filename in new location
        return get_specs_dir(project_path) / spec_path.name

    # Relative path: resolve against project directory
    resolved = project_path / relative_path
    if resolved.exists():
        return resolved

    # Try new location with just the filename
    new_path = get_specs_dir(project_path) / spec_path.name
    if new_path.exists():
        return new_path

    # Try legacy root location
    legacy_path = project_path / spec_path.name
    if legacy_path.exists():
        return legacy_path

    # Default to new-style path (for error reporting)
    return resolved
