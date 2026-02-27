"""
Tests for Specification Parser
Created: February 2, 2026
"""

import pytest
from pathlib import Path
from server.quality.spec_parser import SpecificationParser, Requirement


@pytest.fixture
def parser():
    """Create a spec parser instance."""
    return SpecificationParser()


@pytest.fixture
def sample_spec_content():
    """Sample specification content."""
    return """# My Application Specification

This is a web application for managing tasks.

## Frontend

- User dashboard with task list
- Task creation form with title and description
- Nice to have: Dark mode toggle
- Filter tasks by status (completed/pending)

## Backend

- RESTful API with CRUD operations
- User authentication required
- Database: PostgreSQL must be used
- Optional: Email notifications for task updates

## Additional Features

- Export tasks to CSV format
- Mobile responsive design
"""


@pytest.fixture
def sample_spec_file(tmp_path, sample_spec_content):
    """Create a temporary spec file."""
    spec_file = tmp_path / "app_spec.txt"
    spec_file.write_text(sample_spec_content)
    return spec_file


def test_parse_basic_spec(parser, sample_spec_file):
    """Test parsing a basic specification."""
    parsed = parser.parse_spec(sample_spec_file)

    assert parsed.spec_path == str(sample_spec_file)
    assert len(parsed.spec_hash) == 64  # SHA256 hash
    assert len(parsed.requirements) > 0
    assert len(parsed.sections) > 0


def test_extract_sections(parser, sample_spec_file):
    """Test section extraction."""
    parsed = parser.parse_spec(sample_spec_file)

    assert "Frontend" in parsed.sections
    assert "Backend" in parsed.sections
    assert "Additional Features" in parsed.sections


def test_extract_requirements(parser, sample_spec_file):
    """Test requirement extraction."""
    parsed = parser.parse_spec(sample_spec_file)

    # Should find all bullet points
    assert len(parsed.requirements) >= 9  # At least 9 requirements in sample

    # Check requirement structure
    req = parsed.requirements[0]
    assert req.id.startswith("req_")
    assert req.section in parsed.sections
    assert len(req.text) > 0
    assert isinstance(req.keywords, list)


def test_keyword_extraction(parser, sample_spec_file):
    """Test keyword extraction from requirements."""
    parsed = parser.parse_spec(sample_spec_file)

    # Find a requirement about dashboard
    dashboard_req = next(
        (r for r in parsed.requirements if "dashboard" in r.text.lower()),
        None
    )

    assert dashboard_req is not None
    assert "dashboard" in dashboard_req.keywords or "task" in dashboard_req.keywords


def test_priority_inference_high(parser):
    """Test high priority inference."""
    # Test with "must" keyword
    priority = parser._infer_priority("PostgreSQL must be used")
    assert priority == "high"

    # Test with "required" keyword
    priority = parser._infer_priority("User authentication required")
    assert priority == "high"


def test_priority_inference_low(parser):
    """Test low priority inference."""
    # Test with "nice to have"
    priority = parser._infer_priority("Nice to have: Dark mode toggle")
    assert priority == "low"

    # Test with "optional"
    priority = parser._infer_priority("Optional: Email notifications")
    assert priority == "low"


def test_priority_inference_medium(parser):
    """Test medium (default) priority."""
    priority = parser._infer_priority("User dashboard with task list")
    assert priority == "medium"


def test_parse_nested_requirements(parser, tmp_path):
    """Test parsing nested bullet points."""
    spec_content = """## Features

- Parent feature
  - Nested sub-feature
  - Another sub-feature
"""
    spec_file = tmp_path / "nested_spec.txt"
    spec_file.write_text(spec_content)

    parsed = parser.parse_spec(spec_file)

    # Should extract all requirements including nested ones
    assert len(parsed.requirements) == 3

    # Check if nesting is detected
    nested_reqs = [r for r in parsed.requirements if r.is_nested]
    assert len(nested_reqs) == 2


def test_parse_numbered_list(parser, tmp_path):
    """Test parsing numbered lists."""
    spec_content = """## Requirements

1. First requirement
2. Second requirement
3. Third requirement
"""
    spec_file = tmp_path / "numbered_spec.txt"
    spec_file.write_text(spec_content)

    parsed = parser.parse_spec(spec_file)

    assert len(parsed.requirements) == 3


def test_handle_code_blocks(parser, tmp_path):
    """Test that code blocks are not parsed as requirements."""
    spec_content = """## Backend

- API endpoint for users

```python
def get_users():
    return User.query.all()
```

- Database schema
"""
    spec_file = tmp_path / "code_spec.txt"
    spec_file.write_text(spec_content)

    parsed = parser.parse_spec(spec_file)

    # Should only have 2 requirements (not code lines)
    assert len(parsed.requirements) == 2


def test_handle_empty_spec(parser, tmp_path):
    """Test handling empty specification."""
    spec_file = tmp_path / "empty_spec.txt"
    spec_file.write_text("")

    parsed = parser.parse_spec(spec_file)

    assert len(parsed.requirements) == 0
    assert len(parsed.sections) == 0


def test_spec_without_sections(parser, tmp_path):
    """Test parsing spec without section headers."""
    spec_content = """# App

- Feature one
- Feature two
- Feature three
"""
    spec_file = tmp_path / "no_sections.txt"
    spec_file.write_text(spec_content)

    parsed = parser.parse_spec(spec_file)

    # Should create "General" section
    assert "General" in parsed.sections
    assert len(parsed.requirements) == 3


def test_get_requirements_by_section(parser, sample_spec_file):
    """Test grouping requirements by section."""
    parsed = parser.parse_spec(sample_spec_file)
    by_section = parser.get_requirements_by_section(parsed)

    assert "Frontend" in by_section
    assert "Backend" in by_section
    assert len(by_section["Frontend"]) > 0
    assert len(by_section["Backend"]) > 0


def test_get_requirements_by_priority(parser, sample_spec_file):
    """Test grouping requirements by priority."""
    parsed = parser.parse_spec(sample_spec_file)
    by_priority = parser.get_requirements_by_priority(parsed)

    assert "high" in by_priority
    assert "medium" in by_priority
    assert "low" in by_priority

    # Should have at least one high priority (PostgreSQL must be used)
    assert len(by_priority["high"]) > 0

    # Should have at least one low priority (nice to have)
    assert len(by_priority["low"]) > 0


def test_to_dict_serialization(parser, sample_spec_file):
    """Test conversion to dictionary for JSON serialization."""
    parsed = parser.parse_spec(sample_spec_file)
    data = parser.to_dict(parsed)

    assert "overview" in data
    assert "spec_hash" in data
    assert "sections" in data
    assert "total_requirements" in data
    assert "requirements_by_priority" in data

    # Check structure
    assert data["total_requirements"] == len(parsed.requirements)
    assert len(data["sections"]) == len(parsed.sections)


def test_spec_hash_consistency(parser, tmp_path):
    """Test that spec hash is consistent for same content."""
    content = "# Test\n- Feature one"

    file1 = tmp_path / "spec1.txt"
    file1.write_text(content)

    file2 = tmp_path / "spec2.txt"
    file2.write_text(content)

    parsed1 = parser.parse_spec(file1)
    parsed2 = parser.parse_spec(file2)

    assert parsed1.spec_hash == parsed2.spec_hash


def test_spec_hash_changes(parser, tmp_path):
    """Test that spec hash changes when content changes."""
    file = tmp_path / "spec.txt"

    file.write_text("# Test\n- Feature one")
    parsed1 = parser.parse_spec(file)

    file.write_text("# Test\n- Feature two")
    parsed2 = parser.parse_spec(file)

    assert parsed1.spec_hash != parsed2.spec_hash


def test_file_not_found(parser, tmp_path):
    """Test error handling when file doesn't exist."""
    non_existent = tmp_path / "does_not_exist.txt"

    with pytest.raises(FileNotFoundError):
        parser.parse_spec(non_existent)


def test_overview_extraction(parser, sample_spec_file):
    """Test extraction of overview text before first section."""
    parsed = parser.parse_spec(sample_spec_file)

    assert "web application" in parsed.overview.lower()
    assert "managing tasks" in parsed.overview.lower()


def test_requirement_line_numbers(parser, sample_spec_file):
    """Test that line numbers are tracked."""
    parsed = parser.parse_spec(sample_spec_file)

    # All requirements should have line numbers > 0
    for req in parsed.requirements:
        assert req.line_number > 0
