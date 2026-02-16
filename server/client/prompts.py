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


def get_initializer_prompt(project_type: str = "greenfield", planning_only: bool = False) -> str:
    """
    Load the initializer prompt.

    For greenfield projects, uses the standard initializer prompt.
    For brownfield projects, uses a specialized prompt that focuses on
    understanding existing code and planning modifications.

    When planning_only=True, loads a stripped-down prompt that only creates
    epics (skipping task/test expansion). Used for parallel initialization
    where expansion workers handle tasks and tests.

    Args:
        project_type: 'greenfield' or 'brownfield'
        planning_only: If True, load planning-only prompt (no task/test creation)

    Returns:
        Complete initializer prompt content as string
    """
    if planning_only:
        if project_type == "brownfield":
            return load_prompt("initializer_prompt_brownfield_planning")
        return load_prompt("initializer_prompt_planning")
    if project_type == "brownfield":
        return load_prompt("initializer_prompt_brownfield")
    return load_prompt("initializer_prompt")


def get_coding_prompt(sandbox_type: str = "local") -> str:
    """
    Load the coding agent prompt for the specified sandbox type.

    Prompts are now split by sandbox type into separate files:
    - local: prompts/coding_prompt_local.md
    - docker: prompts/coding_prompt_docker.md

    Args:
        sandbox_type: "docker" or "local" (default: "local")

    Returns:
        Complete coding prompt content as string
    """
    if sandbox_type == "docker":
        prompt_name = "coding_prompt_docker"
    else:
        prompt_name = "coding_prompt_local"

    return load_prompt(prompt_name)


def get_expansion_prompt() -> str:
    """Load the epic expansion worker prompt.

    Used by parallel expansion workers to expand assigned epics
    into detailed tasks and test requirements.

    Returns:
        Expansion prompt content as string
    """
    return load_prompt("expansion_prompt")


def get_brownfield_coding_preamble() -> str:
    """Load the brownfield coding session preamble.

    This preamble is prepended to the standard coding prompt for
    brownfield projects, adding instructions about preserving
    existing code conventions and running regression tests.

    Returns:
        Brownfield coding preamble content as string
    """
    return load_prompt("coding_preamble_brownfield")


def get_prompt_filename(session_type: str, sandbox_type: str = "local", project_type: str = "greenfield") -> str:
    """
    Get the prompt filename for logging purposes.

    Args:
        session_type: "initializer" or "coding"
        sandbox_type: "docker" or "local" (default: "local")
        project_type: "greenfield" or "brownfield" (default: "greenfield")

    Returns:
        Prompt filename (e.g., "initializer_prompt_local.md")
    """
    if session_type == "initializer":
        if project_type == "brownfield":
            return "initializer_prompt_brownfield.md"
        if sandbox_type == "docker":
            return "initializer_prompt_docker.md"
        else:
            return "initializer_prompt_local.md"
    else:  # coding
        if sandbox_type == "docker":
            return "coding_prompt_docker.md"
        else:
            return "coding_prompt_local.md"


def detect_primary_spec_file(spec_dir: Path) -> Path:
    """
    Auto-detect the primary specification file using heuristics.

    Priority order:
    1. Files named: main.md, spec.md, specification.md, readme.md, overview.md
    2. Largest .md or .txt file (likely most comprehensive)
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

    # Priority 2: Largest file
    largest_file = max(text_files, key=lambda f: f.stat().st_size)

    return largest_file


def copy_spec_to_project(project_dir: Path, spec_source_path: Path = None) -> None:
    """
    Copy specification file(s) into the project directory for the agent to read.

    Supports multiple formats:
    - Single file: spec.txt, spec.md, README.md, etc.
    - Spec folder: directory with multiple documentation files

    Args:
        project_dir: Target project directory
        spec_source_path: Path to spec file or folder (if None, uses default from specs/)
    """
    # Determine source
    if spec_source_path is None:
        # Use default from specs/ directory
        spec_source = SPECS_DIR / "app_spec.txt"
        if not spec_source.exists():
            # Try spec.md as fallback
            spec_source = SPECS_DIR / "spec.md"
        if not spec_source.exists():
            raise FileNotFoundError(f"No default spec file found in {SPECS_DIR}")
    else:
        spec_source = Path(spec_source_path)
        if not spec_source.exists():
            raise FileNotFoundError(f"Spec source not found: {spec_source}")

    # Handle spec folder (directory with multiple files)
    if spec_source.is_dir():
        # Create spec/ subdirectory in project
        spec_dest_dir = project_dir / "spec"
        spec_dest_dir.mkdir(exist_ok=True)

        # Copy all files from spec folder
        copied_files = []
        for file in spec_source.glob("*"):
            if file.is_file():
                dest_file = spec_dest_dir / file.name
                if not dest_file.exists():
                    shutil.copy(file, dest_file)
                    copied_files.append(file.name)

        # Detect primary file
        primary_file = detect_primary_spec_file(spec_dest_dir)
        primary_name = primary_file.name if primary_file else "main.md or spec.md"

        # Enhanced main spec with lazy-loading instructions
        main_spec = project_dir / "app_spec.txt"
        if not main_spec.exists():
            # Get file sizes for the list
            file_list = []
            for f in sorted(spec_dest_dir.glob('*')):
                if f.is_file():
                    size_kb = f.stat().st_size / 1024
                    file_list.append(f"- `spec/{f.name}` ({size_kb:.1f} KB)")

            main_spec.write_text(
                f"# Project Specification\n\n"
                f"This project's specification is located in the `spec/` directory.\n\n"
                f"## Instructions\n\n"
                f"1. **Start with the primary file:** `spec/{primary_name}`\n"
                f"2. **Follow references:** The main spec will reference other files as needed\n"
                f"3. **Lazy load:** Only read additional files when you need specific details\n"
                f"4. **Search when needed:** Use `grep -r \"search term\" spec/` to find information\n\n"
                f"## Available Files\n\n"
                + "\n".join(file_list)
                + "\n\n**Remember:** Don't read all files upfront. Read the primary file first, "
                + "then lazy-load referenced files only when needed for your current task.\n"
            )

        print(f"Copied spec folder ({len(copied_files)} files) to project directory (primary: {primary_name})")

    # Handle single spec file
    else:
        # Determine destination filename
        spec_dest = project_dir / "app_spec.txt"

        # If source is not app_spec.txt, preserve original name and create pointer
        if spec_source.name != "app_spec.txt":
            # Copy with original name
            original_dest = project_dir / spec_source.name
            if not original_dest.exists():
                shutil.copy(spec_source, original_dest)

            # Create app_spec.txt as a pointer if needed
            if not spec_dest.exists():
                spec_dest.write_text(
                    f"# Project Specification\n\n"
                    f"The specification for this project is in: `{spec_source.name}`\n\n"
                    f"**Please read {spec_source.name} for the complete requirements.**\n"
                )
            print(f"Copied {spec_source.name} to project directory (app_spec.txt points to it)")
        else:
            # Direct copy for app_spec.txt
            if not spec_dest.exists():
                shutil.copy(spec_source, spec_dest)
                print("Copied app_spec.txt to project directory")


