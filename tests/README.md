# YokeFlow Test Suite

**173 tests**, all passing, ~1 second runtime.

All tests are pure unit tests with no mocks or external dependencies.

## Test Files

| Test File | Tests | What It Tests |
|-----------|-------|---------------|
| `test_errors.py` | 36 | Error hierarchy and categorization (30+ error types) |
| `test_validation.py` | 44 | Pydantic validation models for API, config, and specs |
| `test_code_analyzer.py` | 35 | Codebase analysis (file walking, Python/JS/SQL extraction) |
| `test_spec_parser.py` | 20 | Specification parsing for completion reviews |
| `test_structured_logging.py` | 19 | Structured logging with JSON and dev formatters |
| `test_project_paths.py` | 17 | Project directory path resolution and legacy fallbacks |
| `test_security.py` | 2 | Command extraction and blocklist validation (64 assertions) |

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_errors.py

# Run with coverage
pytest --cov=server --cov-report=term-missing

# Using the helper script
python scripts/test_quick.py
python scripts/test_quick.py --coverage
python scripts/test_quick.py test_errors
```

## Prerequisites

No external services required. All tests run against pure Python code with no database, API, or network dependencies.
