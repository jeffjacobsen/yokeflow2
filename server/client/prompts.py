"""
Prompt Loading Utilities
========================

Functions for loading prompt templates from the prompts directory.
"""

import shutil
import subprocess
from pathlib import Path


# Get project root (parent.parent.parent from this file location)
_project_root = Path(__file__).parent.parent.parent

PROMPTS_DIR = _project_root / "prompts"
SCHEMA_DIR = _project_root / "schema"
SPECS_DIR = _project_root / "specs"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.md"
    return prompt_path.read_text()


def get_initializer_prompt(project_type: str = "greenfield") -> str:
    """
    Load the initializer prompt.

    For greenfield projects, uses the standard initializer prompt.
    For brownfield projects, uses a specialized prompt that focuses on
    understanding existing code and planning modifications.

    Args:
        project_type: 'greenfield' or 'brownfield'

    Returns:
        Complete initializer prompt content as string
    """
    if project_type == "brownfield":
        return load_prompt("initializer_prompt_brownfield")
    return load_prompt("initializer_prompt")


def get_coding_prompt() -> str:
    """
    Load the coding agent prompt.

    Returns:
        Complete coding prompt content as string
    """
    return load_prompt("coding_prompt")


def get_brownfield_coding_preamble() -> str:
    """Load the brownfield coding session preamble.

    This preamble is prepended to the standard coding prompt for
    brownfield projects, adding instructions about preserving
    existing code conventions and running regression tests.

    Returns:
        Brownfield coding preamble content as string
    """
    return load_prompt("coding_preamble_brownfield")


def get_prompt_filename(session_type: str, project_type: str = "greenfield") -> str:
    """
    Get the prompt filename for logging purposes.

    Args:
        session_type: "initializer" or "coding"
        project_type: "greenfield" or "brownfield" (default: "greenfield")

    Returns:
        Prompt filename (e.g., "initializer_prompt.md")
    """
    if session_type == "initializer":
        if project_type == "brownfield":
            return "initializer_prompt_brownfield.md"
        return "initializer_prompt.md"
    else:  # coding
        return "coding_prompt.md"


def detect_primary_spec_file(spec_dir: Path) -> Path:
    """
    Auto-detect the primary specification file using heuristics.

    Priority order:
    1. Files named: main.md, spec.md, specification.md, readme.md, overview.md
    2. Smallest .md or .txt file (likely the overview that references detailed docs)
    3. First alphabetically

    Args:
        spec_dir: Directory containing spec files

    Returns:
        Path to primary file, or None if no suitable file found
    """
    # Get all text files
    text_files = list(spec_dir.glob('*.md')) + list(spec_dir.glob('*.txt'))

    if not text_files:
        return None

    # Priority 1: Check for specific names
    priority_names = ['main.md', 'main.txt', 'spec.md', 'specification.md',
                      'readme.md', 'overview.md']

    for name in priority_names:
        for file in text_files:
            if file.name.lower() == name.lower():
                return file

    # Priority 2: Smallest file (likely the overview referencing detailed docs)
    smallest_file = min(text_files, key=lambda f: f.stat().st_size)

    return smallest_file


def copy_spec_to_project(project_dir: Path, spec_source_path: Path = None) -> str:
    """
    Copy specification file(s) into the project's yokeflow/specs/ directory.

    Files are copied with their original names (no renaming).

    Supports:
    - Single file: copied as-is to yokeflow/specs/
    - Directory: all files copied to yokeflow/specs/

    Args:
        project_dir: Target project directory
        spec_source_path: Path to spec file or folder (if None, uses default from specs/)

    Returns:
        Relative path to the primary spec file (for database storage)
    """
    from server.utils.project_paths import get_specs_dir

    # Determine source
    if spec_source_path is None:
        # Use default from specs/ directory
        spec_source = SPECS_DIR / "app_spec.txt"
        if not spec_source.exists():
            spec_source = SPECS_DIR / "spec.md"
        if not spec_source.exists():
            raise FileNotFoundError(f"No default spec file found in {SPECS_DIR}")
    else:
        spec_source = Path(spec_source_path)
        if not spec_source.exists():
            raise FileNotFoundError(f"Spec source not found: {spec_source}")

    specs_dir = get_specs_dir(project_dir)
    specs_dir.mkdir(parents=True, exist_ok=True)

    # Handle spec folder (directory with multiple files)
    if spec_source.is_dir():
        copied_files = []
        for file in spec_source.glob("*"):
            if file.is_file():
                dest_file = specs_dir / file.name
                if not dest_file.exists():
                    shutil.copy(file, dest_file)
                    copied_files.append(file.name)

        primary_file = detect_primary_spec_file(specs_dir)
        primary_name = primary_file.name if primary_file else copied_files[0] if copied_files else "spec.md"

        print(f"Copied spec folder ({len(copied_files)} files) to yokeflow/specs/ (primary: {primary_name})")
        return f"yokeflow/specs/{primary_name}"

    # Handle single spec file — keep original name
    else:
        spec_dest = specs_dir / spec_source.name
        if not spec_dest.exists():
            shutil.copy(spec_source, spec_dest)
        print(f"Copied {spec_source.name} to yokeflow/specs/")
        return f"yokeflow/specs/{spec_source.name}"


