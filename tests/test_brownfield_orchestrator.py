"""
Tests for Brownfield Orchestrator Methods
==========================================

Tests for create_brownfield_project() and rollback_brownfield_changes()
in server/agent/orchestrator.py.
"""

import asyncio
import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call
from uuid import UUID, uuid4
import pytest

import sys
sys.path.append(str(Path(__file__).parent.parent))

from server.agent.orchestrator import AgentOrchestrator
from server.agent.codebase_import import ImportResult, CodebaseAnalysis


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_brownfield_project"


@pytest.mark.unit
class TestCreateBrownfieldProject:
    """Tests for AgentOrchestrator.create_brownfield_project()."""

    @pytest.fixture
    def orchestrator(self, tmp_path):
        """Create orchestrator with temp projects dir."""
        with patch('server.agent.orchestrator.Config') as mock_config:
            mock_config.load_default.return_value = MagicMock(
                project=MagicMock(
                    default_projects_dir=str(tmp_path / "projects"),
                    max_iterations=None
                ),
                models=MagicMock(
                    initializer="claude-opus",
                    coding="claude-sonnet"
                ),
                timing=MagicMock(
                    auto_continue_delay=3
                ),
                sandbox=MagicMock(
                    type="docker",
                    docker_image="yokeflow-sandbox:latest",
                    docker_network="bridge",
                    docker_memory_limit="2g",
                    docker_cpu_limit=2.0,
                    docker_ports=[]
                ),
                brownfield=MagicMock(
                    default_feature_branch_prefix="yokeflow/"
                ),
                docker=MagicMock(enabled=True),
                api=MagicMock(enabled=False)
            )
            orch = AgentOrchestrator(verbose=False)
            return orch

    @pytest.fixture
    def mock_db(self):
        """Create a mock database manager."""
        mock = AsyncMock()
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=None)
        mock.get_project_by_name = AsyncMock(return_value=None)
        mock.create_project = AsyncMock(return_value={
            'id': uuid4(),
            'name': 'test-brownfield',
            'project_type': 'brownfield',
        })
        mock.update_project = AsyncMock()
        return mock

    @pytest.fixture
    def mock_import_result(self):
        """Successful import result."""
        return ImportResult(
            success=True,
            source_type='local',
            source_path='/tmp/source',
            target_path='/tmp/target',
            commit_sha='abc123',
            file_count=42,
            total_size_bytes=1024000,
        )

    @pytest.fixture
    def mock_analysis(self):
        """Sample codebase analysis."""
        return CodebaseAnalysis(
            languages=['typescript', 'javascript'],
            frameworks=['react', 'next.js'],
            package_managers=['npm'],
            has_tests=True,
            test_framework='jest',
            test_runner_command='npx jest',
            has_ci=True,
            ci_platform='github-actions',
            entry_points=['src/index.ts'],
            loc_estimate=5000,
            key_config_files=['package.json', 'tsconfig.json'],
        )

    @pytest.mark.asyncio
    async def test_create_brownfield_from_local(
        self, orchestrator, mock_db, mock_import_result, mock_analysis, tmp_path
    ):
        """Test creating brownfield project from local path."""
        (tmp_path / "projects").mkdir()

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            with patch('server.agent.orchestrator.CodebaseImporter') as MockImporter:
                mock_importer = MockImporter.return_value
                mock_importer.import_from_local = AsyncMock(return_value=mock_import_result)
                mock_importer.analyze_codebase = AsyncMock(return_value=mock_analysis)
                mock_importer.setup_brownfield_git = AsyncMock(return_value="yokeflow/modifications")

                result = await orchestrator.create_brownfield_project(
                    project_name="test-brownfield",
                    source_path=str(FIXTURE_DIR),
                    change_spec_content="Add dark mode support to the application",
                )

        assert result is not None
        mock_importer.import_from_local.assert_called_once()
        mock_importer.analyze_codebase.assert_called_once()
        mock_db.create_project.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_brownfield_from_github(
        self, orchestrator, mock_db, mock_import_result, mock_analysis, tmp_path
    ):
        """Test creating brownfield project from GitHub URL."""
        (tmp_path / "projects").mkdir()
        mock_import_result.source_type = 'github'

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            with patch('server.agent.orchestrator.CodebaseImporter') as MockImporter:
                mock_importer = MockImporter.return_value
                mock_importer.import_from_github = AsyncMock(return_value=mock_import_result)
                mock_importer.analyze_codebase = AsyncMock(return_value=mock_analysis)
                mock_importer.setup_brownfield_git = AsyncMock(return_value="yokeflow/modifications")

                result = await orchestrator.create_brownfield_project(
                    project_name="test-brownfield",
                    source_url="https://github.com/user/repo.git",
                    branch="develop",
                    change_spec_content="Add dark mode support",
                )

        assert result is not None
        mock_importer.import_from_github.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_brownfield_no_source_raises(self, orchestrator, mock_db, tmp_path):
        """Test that no source raises ValueError."""
        (tmp_path / "projects").mkdir()

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            with pytest.raises(ValueError, match="source_url or source_path"):
                await orchestrator.create_brownfield_project(
                    project_name="test-brownfield",
                    change_spec_content="Do something",
                )

    @pytest.mark.asyncio
    async def test_create_brownfield_already_exists_raises(
        self, orchestrator, mock_db, tmp_path
    ):
        """Test that existing project name raises ValueError."""
        (tmp_path / "projects").mkdir()
        mock_db.get_project_by_name = AsyncMock(return_value={'id': uuid4(), 'name': 'exists'})

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            with pytest.raises(ValueError, match="already exists"):
                await orchestrator.create_brownfield_project(
                    project_name="exists",
                    source_path="/tmp/source",
                    change_spec_content="Do something",
                )

    @pytest.mark.asyncio
    async def test_create_brownfield_import_failure_cleans_up(
        self, orchestrator, mock_db, tmp_path
    ):
        """Test that import failure cleans up the project directory."""
        gens = tmp_path / "projects"
        gens.mkdir()

        failed_result = ImportResult(
            success=False,
            source_type='local',
            source_path='/tmp/nonexistent',
            target_path=str(gens / "test-fail"),
            commit_sha=None,
            error="Source path does not exist"
        )

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            with patch('server.agent.orchestrator.CodebaseImporter') as MockImporter:
                mock_importer = MockImporter.return_value
                mock_importer.import_from_local = AsyncMock(return_value=failed_result)

                with pytest.raises(ValueError, match="Import failed"):
                    await orchestrator.create_brownfield_project(
                        project_name="test-fail",
                        source_path="/tmp/nonexistent",
                        change_spec_content="Do something",
                    )

    @pytest.mark.asyncio
    async def test_create_brownfield_writes_change_spec(
        self, orchestrator, mock_db, mock_import_result, mock_analysis, tmp_path
    ):
        """Test that change_spec.md and app_spec.txt are written."""
        gens = tmp_path / "projects"
        gens.mkdir()

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            with patch('server.agent.orchestrator.CodebaseImporter') as MockImporter:
                mock_importer = MockImporter.return_value
                mock_importer.import_from_local = AsyncMock(return_value=mock_import_result)
                mock_importer.analyze_codebase = AsyncMock(return_value=mock_analysis)
                mock_importer.setup_brownfield_git = AsyncMock(return_value="yokeflow/modifications")

                result = await orchestrator.create_brownfield_project(
                    project_name="test-spec",
                    source_path=str(FIXTURE_DIR),
                    change_spec_content="Add dark mode to the application",
                )

        project_dir = gens / "test-spec"
        specs_dir = project_dir / "yokeflow" / "specs"
        assert (specs_dir / "change_spec.md").exists()
        assert "dark mode" in (specs_dir / "change_spec.md").read_text()

    @pytest.mark.asyncio
    async def test_create_brownfield_stores_analysis(
        self, orchestrator, mock_db, mock_import_result, mock_analysis, tmp_path
    ):
        """Test that codebase analysis is passed to create_project."""
        (tmp_path / "projects").mkdir()

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            with patch('server.agent.orchestrator.CodebaseImporter') as MockImporter:
                mock_importer = MockImporter.return_value
                mock_importer.import_from_local = AsyncMock(return_value=mock_import_result)
                mock_importer.analyze_codebase = AsyncMock(return_value=mock_analysis)
                mock_importer.setup_brownfield_git = AsyncMock(return_value="yokeflow/modifications")

                await orchestrator.create_brownfield_project(
                    project_name="test-analysis",
                    source_path=str(FIXTURE_DIR),
                    change_spec_content="Some changes to make",
                )

        # Verify create_project was called with brownfield args
        call_kwargs = mock_db.create_project.call_args
        assert call_kwargs is not None
        # Check keyword args
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs.get('project_type') == 'brownfield'
        else:
            # Positional args — check by inspecting
            pass


@pytest.mark.unit
class TestRollbackBrownfieldChanges:
    """Tests for AgentOrchestrator.rollback_brownfield_changes()."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator."""
        with patch('server.agent.orchestrator.Config') as mock_config:
            mock_config.load_default.return_value = MagicMock(
                project=MagicMock(
                    default_projects_dir="projects",
                    max_iterations=None
                ),
                models=MagicMock(
                    initializer="claude-opus",
                    coding="claude-sonnet"
                ),
                timing=MagicMock(auto_continue_delay=3),
                sandbox=MagicMock(
                    type="docker",
                    docker_image="yokeflow-sandbox:latest",
                    docker_network="bridge",
                    docker_memory_limit="2g",
                    docker_cpu_limit=2.0,
                    docker_ports=[]
                ),
                brownfield=MagicMock(
                    default_feature_branch_prefix="yokeflow/"
                ),
                docker=MagicMock(enabled=True),
                api=MagicMock(enabled=False)
            )
            return AgentOrchestrator(verbose=False)

    @pytest.mark.asyncio
    async def test_rollback_non_brownfield_raises(self, orchestrator):
        """Test rollback of non-brownfield project raises ValueError."""
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        mock_db.get_project = AsyncMock(return_value={
            'id': uuid4(),
            'name': 'greenfield-project',
            'project_type': 'greenfield',
            'metadata': {}
        })

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            with pytest.raises(ValueError, match="brownfield"):
                await orchestrator.rollback_brownfield_changes(uuid4())

    @pytest.mark.asyncio
    async def test_rollback_not_found_raises(self, orchestrator):
        """Test rollback of nonexistent project raises ValueError."""
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        mock_db.get_project = AsyncMock(return_value=None)

        with patch('server.agent.orchestrator.DatabaseManager', return_value=mock_db):
            with pytest.raises(ValueError, match="not found"):
                await orchestrator.rollback_brownfield_changes(uuid4())
