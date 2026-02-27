# Testing Guide

YokeFlow has 173 unit tests that run in ~1 second with no external dependencies.

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_errors.py

# Run with coverage report
pytest --cov=server --cov-report=html --cov-report=term-missing

# Using the helper script
python scripts/test_quick.py
python scripts/test_quick.py --coverage
python scripts/test_quick.py --verbose
```

## Test Files

| Test File | Tests | What It Tests |
|-----------|-------|---------------|
| `test_errors.py` | 36 | Error hierarchy and categorization |
| `test_validation.py` | 44 | Pydantic validation models for API, config, and specs |
| `test_code_analyzer.py` | 35 | Codebase analysis (file walking, code extraction) |
| `test_spec_parser.py` | 20 | Specification parsing for completion reviews |
| `test_structured_logging.py` | 19 | Structured logging (JSON and dev formatters) |
| `test_project_paths.py` | 17 | Project directory path resolution |
| `test_security.py` | 2 | Command extraction and blocklist validation |

## Prerequisites

No external services required. Tests run against pure Python code — no database, API server, or Docker needed.

## Writing New Tests

Test files go in `tests/` and must start with `test_`. Test functions must start with `test_`.

```bash
tests/
├── conftest.py          # Minimal pytest configuration
├── test_errors.py       # Example: pure unit tests
├── test_validation.py   # Example: Pydantic model tests
└── ...
```

## Coverage

```bash
# Generate HTML coverage report
pytest --cov=server --cov-report=html

# View report
open htmlcov/index.html
```

## Troubleshooting

**Import errors:** Ensure you're in the project root directory. The `conftest.py` adds the parent directory to `sys.path`.

**Test discovery issues:** Test files must start with `test_` and test functions must start with `test_`.
