"""
Tests for API Endpoints
========================

Comprehensive tests for the FastAPI REST API endpoints.
Tests all major endpoints, authentication, error handling, and WebSocket connections.
"""

import pytest
import json
import os
from uuid import uuid4, UUID
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from fastapi import status
from fastapi.testclient import TestClient
from httpx import AsyncClient
import jwt

from server.api.app import app, ProjectCreate, SessionResponse
from server.api.auth import create_access_token, SECRET_KEY, ALGORITHM
from server.agent.orchestrator import SessionStatus, SessionType


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Create an async test client for the FastAPI app."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_token():
    """Create a valid authentication token."""
    return create_access_token(
        data={"sub": "test_user"},
        expires_delta=timedelta(minutes=30)
    )


@pytest.fixture
def auth_headers(auth_token):
    """Create authentication headers."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def mock_db():
    """Create a mock database manager."""
    db = AsyncMock()
    db.pool = AsyncMock()
    return db


@pytest.fixture
def mock_orchestrator():
    """Create a mock agent orchestrator."""
    orch = AsyncMock()
    orch.get_session_status = AsyncMock()
    orch.start_session = AsyncMock()
    orch.stop_session = AsyncMock()
    return orch


class TestHealthEndpoints:
    """Test health check and info endpoints."""

    def test_health_check(self, client):
        """Test the health check endpoint."""
        with patch('server.database.connection.is_postgresql_configured', return_value=True):
            with patch('server.database.connection.get_db') as mock_get_db:
                mock_db = AsyncMock()
                mock_db.pool = AsyncMock()
                mock_db.pool.fetchval = AsyncMock(return_value=1)
                mock_get_db.return_value = mock_db

                response = client.get("/api/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] in ["healthy", "degraded", "unhealthy"]
                assert "checks" in data

    def test_info_endpoint(self, client):
        """Test the info endpoint."""
        response = client.get("/api/info")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "database_configured" in data
        assert "default_models" in data
        assert "projects_dir" in data


class TestAuthenticationEndpoints:
    """Test authentication-related endpoints."""

    def test_login_success(self, client):
        """Test successful login."""
        with patch('server.api.auth.verify_password', return_value=True):
            response = client.post(
                "/api/auth/login",
                json={"password": "correct_password"}
            )
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials."""
        # Patch where verify_password is imported/used, not where it's defined
        with patch('server.api.app.verify_password', return_value=False):
            response = client.post(
                "/api/auth/login",
                json={"password": "wrong_password"}
            )
            assert response.status_code == 401

    def test_verify_token(self, client, auth_headers):
        """Test token verification endpoint."""
        # In dev mode without UI_PASSWORD, get_current_user returns a dict
        response = client.get("/api/auth/verify", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        # In dev mode, user is a dict with dev_mode flag
        assert data["user"]["dev_mode"] is True


class TestProjectEndpoints:
    """Test project management endpoints."""

    def test_list_projects(self, client):
        """Test listing all projects."""
        with patch('server.api.app.orchestrator') as mock_orchestrator:
            mock_orchestrator.list_projects = AsyncMock(return_value=[
                {
                    'id': str(uuid4()),
                    'name': 'project1',
                    'created_at': datetime.now(),
                    'status': 'active',
                    'is_initialized': True,
                    'completed': False,
                    'total_cost_usd': 0.5,
                    'total_time_seconds': 120,
                    'progress': {'epics': 3, 'tasks': 10},
                    'metadata': json.dumps({
                        'settings': {}
                    })
                },
                {
                    'id': str(uuid4()),
                    'name': 'project2',
                    'created_at': datetime.now(),
                    'status': 'completed',
                    'is_initialized': True,
                    'completed': True,
                    'total_cost_usd': 1.2,
                    'total_time_seconds': 300,
                    'progress': {'epics': 5, 'tasks': 20},
                    'metadata': {
                        'settings': {}
                    }
                }
            ])

            response = client.get("/api/projects")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]['name'] == 'project1'
            assert data[1]['name'] == 'project2'

    def test_create_project(self, client):
        """Test creating a new project."""
        project_id = uuid4()
        with patch('server.database.connection.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.get_project_by_name = AsyncMock(return_value=None)
            mock_db.create_project = AsyncMock(return_value={
                'id': project_id,
                'name': 'test-project',
                'spec': 'Test specification',
                'created_at': datetime.now()
            })
            mock_get_db.return_value = mock_db

            # Mock file operations and orchestrator
            with patch('pathlib.Path.mkdir'):
                with patch('pathlib.Path.write_text'):
                    with patch('server.api.app.orchestrator') as mock_orch:
                        mock_orch.create_project = AsyncMock(return_value={
                            'id': str(project_id),
                            'name': 'test-project',
                            'created_at': '2024-01-01T00:00:00'
                        })

                        # Create a test file upload
                        from io import BytesIO
                        spec_file = BytesIO(b"Test specification content")

                        response = client.post(
                            "/api/projects",
                            data={
                                "name": "test-project",
                                "force": "false",
                            },
                            files={
                                "spec_files": ("spec.txt", spec_file, "text/plain")
                            }
                        )

            assert response.status_code == 200
            data = response.json()
            assert data['name'] == 'test-project'
            assert 'id' in data

    def test_create_project_duplicate_name(self, client):
        """Test creating a project with duplicate name."""
        with patch('server.api.app.orchestrator') as mock_orch:
            mock_orch.create_project = AsyncMock(side_effect=ValueError("Project with name 'existing-project' already exists"))

            from io import BytesIO
            spec_file = BytesIO(b"Test specification content")

            response = client.post(
                "/api/projects",
                data={
                    "name": "existing-project",
                    "force": "false",
                },
                files={
                    "spec_files": ("spec.txt", spec_file, "text/plain")
                }
            )
            assert response.status_code == 409

    def test_get_project(self, client):
        """Test getting a specific project."""
        project_id = uuid4()
        with patch('server.api.app.orchestrator') as mock_orch:
            mock_orch.get_project_info = AsyncMock(return_value={
                'id': project_id,
                'name': 'test-project',
                'created_at': datetime.now(),
                'updated_at': None,
                'status': 'active',
                'is_initialized': False,
                'completed_at': None,
                'total_cost_usd': 0.0,
                'total_time_seconds': 0,
                'has_env_file': False,
                'has_env_example': False,
                'needs_env_config': False,
                'env_configured': False,
                'progress': {'total_tasks': 0, 'completed_tasks': 0},
                'active_sessions': [],
                'metadata': {'settings': {}}
            })

            response = client.get(f"/api/projects/{project_id}")
            assert response.status_code == 200
            data = response.json()
            assert data['name'] == 'test-project'

    def test_get_project_not_found(self, client):
        """Test getting a non-existent project."""
        project_id = uuid4()
        with patch('server.api.app.orchestrator') as mock_orch:
            mock_orch.get_project_info = AsyncMock(side_effect=ValueError(f"Project {project_id} not found"))

            response = client.get(f"/api/projects/{project_id}")
            assert response.status_code == 404

    def test_delete_project(self, client):
        """Test deleting a project."""
        project_id = uuid4()
        with patch('server.database.connection.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.get_project = AsyncMock(return_value={'id': project_id, 'name': 'test'})
            mock_db.delete_project = AsyncMock()
            mock_get_db.return_value = mock_db

            with patch('shutil.rmtree'):  # Mock directory deletion
                response = client.delete(f"/api/projects/{project_id}")
                assert response.status_code == 200


class TestSessionEndpoints:
    """Test session management endpoints."""

    def test_start_session(self, client):
        """Test starting a coding session."""
        project_id = uuid4()
        session_id = uuid4()

        with patch('server.database.connection.get_db') as mock_get_db, \
             patch('server.api.app.get_db') as mock_app_get_db:
            mock_db = AsyncMock()
            mock_db.get_project = AsyncMock(return_value={
                'id': project_id,
                'name': 'test-project'
            })
            mock_db.create_session = AsyncMock(return_value={
                'id': session_id,
                'session_number': 1,
                'type': 'coding'
            })
            mock_db.get_next_session_number = AsyncMock(return_value=1)
            mock_get_db.return_value = mock_db
            mock_app_get_db.return_value = mock_db

            with patch('server.api.app.orchestrator') as mock_orch:
                mock_orch.start_coding_session = AsyncMock(return_value={
                    'session_id': str(session_id),
                    'status': 'running',
                    'session_number': 1,
                    'type': 'coding'
                })

                response = client.post(
                    f"/api/projects/{project_id}/sessions/start",
                    json={
                        "auto_continue": True
                    }
                )
                assert response.status_code == 200
                data = response.json()
                assert 'session_id' in data

    def test_get_sessions(self, client):
        """Test getting sessions for a project."""
        project_id = uuid4()

        with patch('server.database.connection.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.get_session_history = AsyncMock(return_value=[
                {
                    'id': str(uuid4()),
                    'session_number': 0,
                    'type': 'initialization',
                    'status': 'completed',
                    'started_at': datetime.now()
                },
                {
                    'id': str(uuid4()),
                    'session_number': 1,
                    'type': 'coding',
                    'status': 'running',
                    'started_at': datetime.now()
                }
            ])
            mock_get_db.return_value = mock_db

            response = client.get(f"/api/projects/{project_id}/sessions")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]['type'] == 'initialization'
            assert data[1]['type'] == 'coding'

    def test_stop_session(self, client):
        """Test stopping a running session."""
        project_id = uuid4()
        session_id = uuid4()

        with patch('server.database.connection.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.get_project = AsyncMock(return_value={'id': project_id})
            mock_db.end_session = AsyncMock()
            mock_get_db.return_value = mock_db

            with patch('server.agent.orchestrator.AgentOrchestrator') as MockOrch:
                mock_orch = AsyncMock()
                mock_orch.stop_session = AsyncMock()
                MockOrch.return_value = mock_orch

                response = client.post(f"/api/projects/{project_id}/sessions/{session_id}/stop")
                assert response.status_code == 200


class TestProgressEndpoints:
    """Test progress and status endpoints."""

    def test_get_project_progress(self, client):
        """Test getting project progress."""
        project_id = uuid4()

        with patch('server.database.connection.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.get_progress = AsyncMock(return_value={
                'total_epics': 5,
                'completed_epics': 2,
                'total_tasks': 20,
                'completed_tasks': 8,
                'total_tests': 100,
                'passing_tests': 75
            })
            mock_get_db.return_value = mock_db

            response = client.get(f"/api/projects/{project_id}/progress")
            assert response.status_code == 200
            data = response.json()
            assert data['total_tasks'] == 20
            assert data['completed_tasks'] == 8

    def test_get_test_coverage(self, client):
        """Test getting test coverage data."""
        project_id = uuid4()

        with patch('server.database.connection.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.get_test_coverage = AsyncMock(return_value={
                'overall_coverage': 75.5,
                'files': [
                    {'file': 'main.py', 'coverage': 85.0},
                    {'file': 'utils.py', 'coverage': 65.0}
                ]
            })
            mock_get_db.return_value = mock_db

            response = client.get(f"/api/projects/{project_id}/coverage")
            assert response.status_code == 200
            data = response.json()
            assert data['overall_coverage'] == 75.5
            assert len(data['files']) == 2


class TestQualityEndpoints:
    """Test quality and review endpoints."""

    # Removed: test_get_project_quality() - endpoint removed (session_quality_checks table deprecated)
    # Quality metrics now in sessions.metrics JSONB field. Use /deep-reviews endpoint for reviews.

    def test_get_deep_reviews(self, client):
        """Test getting deep reviews for a project."""
        project_id = uuid4()

        with patch('server.database.connection.get_db') as mock_get_db, \
             patch('server.api.app.get_db') as mock_app_get_db:
            mock_db = AsyncMock()
            mock_db.list_deep_reviews = AsyncMock(return_value=[
                {
                    'id': str(uuid4()),
                    'session_id': str(uuid4()),
                    'review_type': 'task',
                    'score': 0.90,
                    'created_at': datetime.now().isoformat()
                }
            ])
            mock_get_db.return_value = mock_db
            mock_app_get_db.return_value = mock_db

            response = client.get(f"/api/projects/{project_id}/deep-reviews")
            assert response.status_code == 200
            data = response.json()
            assert 'reviews' in data
            assert 'count' in data
            assert data['count'] == 1
            assert len(data['reviews']) == 1
            assert data['reviews'][0]['review_type'] == 'task'


class TestErrorHandling:
    """Test error handling in API."""

    def test_invalid_uuid(self, client):
        """Test handling of invalid UUID in path."""
        response = client.get("/api/projects/invalid-uuid")
        assert response.status_code == 400  # API returns 400 for invalid UUID format

    def test_rate_limiting(self, client):
        """Test rate limiting on project creation."""
        with patch('server.api.rate_limiter.RateLimiter.check_rate_limit') as mock_check:
            # Simulate rate limit exceeded
            mock_check.return_value = (False, 60)

            response = client.post(
                "/api/projects",
                json={"name": "test", "spec_content": "test"}
            )
            assert response.status_code == 429
            assert "Retry-After" in response.headers

    def test_database_error(self, client):
        """Test handling of database errors."""
        project_id = uuid4()

        with patch('server.database.connection.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.get_project = AsyncMock(side_effect=Exception("Database connection failed"))
            mock_get_db.return_value = mock_db

            response = client.get(f"/api/projects/{project_id}")
            assert response.status_code == 500


class TestEnvironmentEndpoints:
    """Test environment variable management endpoints."""

    def test_get_env_vars(self, client):
        """Test getting environment variables."""
        project_id = uuid4()
        project_path = f"/tmp/test-{project_id}"

        with patch('server.api.app.orchestrator') as mock_orch:
            mock_orch.get_project_info = AsyncMock(return_value={
                'id': project_id,
                'name': 'test-project',
                'local_path': project_path
            })

            # Mock Path.exists and Path.read_text for both files
            def mock_exists(self):
                path_str = str(self)
                return path_str.endswith('.env.example') or path_str.endswith('.env')

            def mock_read_text(self):
                path_str = str(self)
                if path_str.endswith('.env.example'):
                    return "# API Configuration\nAPI_KEY=your-api-key-here\n# Database\nDATABASE_URL=postgres://localhost/mydb"
                elif path_str.endswith('.env'):
                    return "API_KEY=secret123\nDATABASE_URL=postgres://localhost/testdb"
                return ""

            with patch('pathlib.Path.exists', mock_exists):
                with patch('pathlib.Path.read_text', mock_read_text):
                    response = client.get(f"/api/projects/{project_id}/env")
                    assert response.status_code == 200
                    data = response.json()
                    assert 'variables' in data
                    assert 'has_env_example' in data

    def test_update_env_vars(self, client):
        """Test updating environment variables."""
        project_id = uuid4()
        project_path = f"/tmp/test-{project_id}"

        with patch('server.api.app.orchestrator') as mock_orch, \
             patch('server.database.connection.get_db') as mock_get_db, \
             patch('server.api.app.get_db') as mock_app_get_db:
            mock_orch.get_project_info = AsyncMock(return_value={
                'id': project_id,
                'name': 'test-project',
                'local_path': project_path
            })
            mock_orch.mark_env_configured = AsyncMock(return_value=None)

            mock_db = AsyncMock()
            mock_db.update_project_env_configured = AsyncMock(return_value=None)
            # Context manager for database connection
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_get_db.return_value = mock_db
            mock_app_get_db.return_value = mock_db

            # Mock Path methods
            def mock_exists(self):
                return str(self) == project_path  # Project path exists

            # Mock file writing
            from unittest.mock import mock_open
            m = mock_open()

            with patch('pathlib.Path.exists', mock_exists):
                with patch('builtins.open', m):
                    response = client.post(
                        f"/api/projects/{project_id}/env",
                        json={
                            "variables": [
                                {"key": "API_KEY", "value": "secret123"},
                                {"key": "DATABASE_URL", "value": "postgres://localhost"}
                            ]
                        }
                    )
                    assert response.status_code == 200
                    # Verify file was opened for writing
                    m.assert_called_once()
                    # Check that write was called with content
                    handle = m()
                    assert handle.write.called


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])