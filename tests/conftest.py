"""
Pytest configuration and shared fixtures for YokeFlow test suite.

This module provides common test fixtures and configuration for all tests.
"""

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

# Add parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.database.operations import TaskDatabase
from server.utils.config import Config
from server.utils.observability import SessionLogger


# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config():
    """Provide test configuration."""
    config = Config()
    config.database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://agent:agent_dev_password@localhost:5432/yokeflow_test"
    )
    config.api_host = "127.0.0.1"
    config.api_port = 8001  # Use different port for tests
    return config


@pytest_asyncio.fixture
async def db(test_config):
    """
    Database fixture with automatic cleanup.

    Creates a connection to the test database and ensures proper cleanup
    after each test.
    """
    from server.database.connection import DatabaseManager

    # Create database connection
    db_conn = DatabaseManager(test_config.database_url)
    await db_conn.connect()

    # Create TaskDatabase instance
    task_db = TaskDatabase(test_config.database_url)
    task_db.pool = db_conn.pool

    # Start transaction for test isolation
    async with task_db.acquire() as conn:
        await conn.execute("BEGIN")

        # Set savepoint for rollback
        await conn.execute("SAVEPOINT test_savepoint")

    yield task_db

    # Rollback transaction to clean up test data
    async with task_db.acquire() as conn:
        await conn.execute("ROLLBACK TO SAVEPOINT test_savepoint")
        await conn.execute("COMMIT")

    # Close connection
    await db_conn.disconnect()


@pytest_asyncio.fixture
async def test_project(db) -> UUID:
    """
    Create a test project in the database.

    Returns the project UUID for use in tests.
    """
    project_id = uuid4()
    project_name = f"test-project-{project_id.hex[:8]}"

    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO projects (id, name, created_at, spec_content)
            VALUES ($1, $2, NOW(), $3)
        """, project_id, project_name, "# Test Specification\n\nTest project for automated testing.")

    yield project_id

    # Cleanup is handled by database transaction rollback


@pytest_asyncio.fixture
async def test_session(db, test_project) -> UUID:
    """
    Create a test session in the database.

    Returns the session UUID for use in tests.
    """
    session_id = uuid4()

    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO sessions (
                id, project_id, session_number, status,
                started_at, model, session_type
            )
            VALUES ($1, $2, $3, $4, NOW(), $5, $6)
        """,
        session_id, test_project, 1, "in_progress",
        "claude-sonnet-4-6", "coding"
    )

    yield session_id

    # Cleanup is handled by database transaction rollback


@pytest_asyncio.fixture
async def test_epic(db, test_project) -> int:
    """
    Create a test epic in the database.

    Returns the epic ID for use in tests.
    """
    async with db.acquire() as conn:
        epic_id = await conn.fetchval("""
            INSERT INTO epics (
                project_id, name, description, created_at
            )
            VALUES ($1, $2, $3, NOW())
            RETURNING id
        """,
        test_project, "Test Epic", "Epic for automated testing"
    )

    yield epic_id

    # Cleanup is handled by database transaction rollback


@pytest_asyncio.fixture
async def test_task(db, test_epic) -> int:
    """
    Create a test task in the database.

    Returns the task ID for use in tests.
    """
    async with db.acquire() as conn:
        task_id = await conn.fetchval("""
            INSERT INTO tasks (
                epic_id, name, description, status, created_at
            )
            VALUES ($1, $2, $3, $4, NOW())
            RETURNING id
        """,
        test_epic, "Test Task", "Task for automated testing", "pending"
    )

    yield task_id

    # Cleanup is handled by database transaction rollback


@pytest.fixture
def temp_project_dir() -> Generator[Path, None, None]:
    """
    Create a temporary directory for project files.

    Automatically cleans up after test completion.
    """
    with tempfile.TemporaryDirectory(prefix="yokeflow_test_") as tmpdir:
        project_dir = Path(tmpdir)

        # Create standard project structure under yokeflow/
        (project_dir / "yokeflow" / "logs").mkdir(parents=True)
        (project_dir / "yokeflow" / "specs").mkdir(parents=True)
        (project_dir / "yokeflow" / "screenshots").mkdir(parents=True)

        # Create basic files
        (project_dir / "yokeflow" / "specs" / "app_spec.txt").write_text("# Test Specification\n")
        (project_dir / ".env.example").write_text("TEST_VAR=example\n")

        yield project_dir


@pytest.fixture
def mock_claude_client():
    """
    Mock Claude SDK client for testing.

    Provides a mock client that simulates Claude API responses.
    """
    client = Mock()
    client.model = "claude-sonnet-4-6"

    # Mock message method
    async def mock_message(message, tools=None):
        response = Mock()
        response.content = "Mock Claude response"
        response.usage = Mock(input_tokens=100, output_tokens=50)
        return response

    client.message = AsyncMock(side_effect=mock_message)

    return client


@pytest.fixture
def session_logger(temp_project_dir) -> SessionLogger:
    """
    Create a test session logger.

    Returns a configured SessionLogger instance for testing.
    """
    logger = SessionLogger(
        project_dir=temp_project_dir,
        session_number=1,
        session_type="test",
        model="test-model"
    )
    return logger


@pytest_asyncio.fixture
async def api_client(test_config):
    """
    Create an async HTTP client for API testing.

    Provides an httpx AsyncClient configured to test the API.
    """
    # Import here to avoid circular dependencies
    from server.api.app import app

    async with AsyncClient(
        app=app,
        base_url=f"http://{test_config.api_host}:{test_config.api_port}"
    ) as client:
        # Set test authentication token
        client.headers["Authorization"] = "Bearer test-token"
        yield client


@pytest.fixture(autouse=True)
def reset_singletons():
    """
    Reset singleton instances between tests.

    Ensures clean state for each test.
    """
    # Reset any singleton instances
    from server.database.connection import DatabaseManager
    if hasattr(DatabaseManager, '_instance'):
        delattr(DatabaseManager, '_instance')

    yield

    # Cleanup after test
    if hasattr(DatabaseManager, '_instance'):
        delattr(DatabaseManager, '_instance')


@pytest.fixture
def mock_websocket():
    """
    Mock WebSocket for testing real-time features.

    Simulates WebSocket connections and messages.
    """
    ws = Mock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock(return_value={"type": "ping"})
    ws.close = AsyncMock()
    return ws


# Test data fixtures
@pytest.fixture
def sample_spec_content():
    """Sample specification content for testing."""
    return """
# Test Application Specification

## Overview
A simple test application for automated testing.

## Epic 1: Core Features
- Task 1: Basic setup
- Task 2: Main functionality

## Epic 2: Advanced Features
- Task 3: Enhanced capabilities
- Task 4: Performance optimization

## Requirements
- Python 3.9+
- PostgreSQL
"""


@pytest.fixture
def sample_project_data():
    """Sample project data for API testing."""
    return {
        "name": "test-project",
        "spec_content": "# Test Spec\n\nBasic test specification.",
        "force": False
    }


# Marker definitions
def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "api: marks tests as API tests"
    )
    config.addinivalue_line(
        "markers", "database: marks tests as database tests"
    )
    config.addinivalue_line(
        "markers", "docker: marks tests as requiring Docker (deselect with '-m \"not docker\"')"
    )
    config.addinivalue_line(
        "markers", "sandbox: marks tests as sandbox-related"
    )
    config.addinivalue_line(
        "markers", "serial: marks tests that must run serially (not in parallel)"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )