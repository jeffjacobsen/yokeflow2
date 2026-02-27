"""
Tests for Code Analyzer (Completion Review)
============================================

Tests the CodeAnalyzer class that scans project directories and builds
a structured inventory of code artifacts (functions, classes, routes,
components, models).
"""

import pytest
import tempfile
from pathlib import Path

from server.quality.code_analyzer import (
    CodeAnalyzer, CodeInventory, CodeArtifact,
    SKIP_DIRS, LANGUAGE_MAP,
)


@pytest.fixture
def analyzer():
    return CodeAnalyzer()


@pytest.fixture
def mock_project(tmp_path):
    """Create a realistic mock project directory."""
    # Python files
    server_dir = tmp_path / "server"
    server_dir.mkdir()

    (server_dir / "app.py").write_text(
        'from flask import Flask\n'
        'app = Flask(__name__)\n'
        '\n'
        'class UserService:\n'
        '    pass\n'
        '\n'
        '@app.get("/api/users")\n'
        'async def get_users():\n'
        '    pass\n'
        '\n'
        '@app.post("/api/users")\n'
        'async def create_user():\n'
        '    pass\n'
        '\n'
        '@app.route("/health")\n'
        'def health_check():\n'
        '    return "ok"\n'
    )

    (server_dir / "models.py").write_text(
        'from sqlalchemy import Base\n'
        '\n'
        'class User(Base):\n'
        '    __tablename__ = "users"\n'
        '\n'
        'class Post(Base):\n'
        '    __tablename__ = "posts"\n'
        '\n'
        'def get_user_by_id(user_id):\n'
        '    pass\n'
    )

    # TypeScript files
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    components_dir = src_dir / "components"
    components_dir.mkdir()

    (components_dir / "Header.tsx").write_text(
        'export function Header({ title }: { title: string }) {\n'
        '  return <header>{title}</header>;\n'
        '}\n'
        '\n'
        'export const Footer = () => {\n'
        '  return <footer>Footer</footer>;\n'
        '}\n'
    )

    (src_dir / "utils.ts").write_text(
        'export function formatDate(date: Date): string {\n'
        '  return date.toISOString();\n'
        '}\n'
        '\n'
        'export const calculateTotal = (items: number[]) => {\n'
        '  return items.reduce((a, b) => a + b, 0);\n'
        '}\n'
    )

    # Next.js pages
    app_dir = src_dir / "app"
    app_dir.mkdir()

    dashboard_dir = app_dir / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "page.tsx").write_text(
        'export default function DashboardPage() {\n'
        '  return <div>Dashboard</div>;\n'
        '}\n'
    )

    api_dir = app_dir / "api" / "users"
    api_dir.mkdir(parents=True)
    (api_dir / "route.ts").write_text(
        'export async function GET(request: Request) {\n'
        '  return Response.json({ users: [] });\n'
        '}\n'
    )

    # SQL file
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "schema.sql").write_text(
        'CREATE TABLE users (\n'
        '  id SERIAL PRIMARY KEY,\n'
        '  name TEXT NOT NULL\n'
        ');\n'
        '\n'
        'CREATE TABLE IF NOT EXISTS posts (\n'
        '  id SERIAL PRIMARY KEY,\n'
        '  user_id INT REFERENCES users(id)\n'
        ');\n'
    )

    # Prisma schema
    (tmp_path / "schema.prisma").write_text(
        'model User {\n'
        '  id   Int    @id @default(autoincrement())\n'
        '  name String\n'
        '}\n'
        '\n'
        'model Post {\n'
        '  id     Int  @id @default(autoincrement())\n'
        '  userId Int\n'
        '}\n'
    )

    # JS file with Express routes
    (tmp_path / "router.js").write_text(
        'const express = require("express");\n'
        'const router = express.Router();\n'
        '\n'
        'router.get("/api/items", getItems);\n'
        'router.post("/api/items", createItem);\n'
        '\n'
        'function getItems(req, res) { res.json([]); }\n'
        'function createItem(req, res) { res.json({}); }\n'
    )

    # Directories that should be skipped
    node_modules = tmp_path / "node_modules" / "some-package"
    node_modules.mkdir(parents=True)
    (node_modules / "index.js").write_text('module.exports = {};')

    git_dir = tmp_path / ".git" / "objects"
    git_dir.mkdir(parents=True)

    pycache = tmp_path / "server" / "__pycache__"
    pycache.mkdir()
    (pycache / "app.cpython-311.pyc").write_text('compiled')

    return tmp_path


class TestCodeAnalyzerFileWalking:
    """Test file discovery and exclusion patterns."""

    def test_skips_node_modules(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        paths = [f['path'] for f in inventory.files]
        assert not any('node_modules' in p for p in paths)

    def test_skips_git_directory(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        paths = [f['path'] for f in inventory.files]
        assert not any('.git' in p for p in paths)

    def test_skips_pycache(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        paths = [f['path'] for f in inventory.files]
        assert not any('__pycache__' in p for p in paths)

    def test_finds_python_files(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        py_files = [f for f in inventory.files if f['language'] == 'python']
        assert len(py_files) == 2  # app.py, models.py

    def test_finds_typescript_files(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        ts_files = [f for f in inventory.files if f['language'] == 'typescript']
        assert len(ts_files) >= 3  # Header.tsx, utils.ts, page.tsx, route.ts

    def test_finds_sql_files(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        sql_files = [f for f in inventory.files if f['language'] == 'sql']
        assert len(sql_files) == 1

    def test_finds_prisma_files(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        prisma_files = [f for f in inventory.files if f['language'] == 'prisma']
        assert len(prisma_files) == 1

    def test_counts_lines(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        for f in inventory.files:
            assert f['lines'] > 0

    def test_empty_directory(self, analyzer, tmp_path):
        inventory = analyzer.analyze(tmp_path)
        assert len(inventory.files) == 0
        assert len(inventory.artifacts) == 0

    def test_invalid_directory_raises(self, analyzer):
        with pytest.raises(ValueError, match="not a directory"):
            analyzer.analyze(Path("/nonexistent/path"))


class TestPythonExtraction:
    """Test Python artifact extraction."""

    def test_extracts_functions(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        functions = [a for a in inventory.artifacts
                     if a.artifact_type == 'function' and a.language == 'python']
        names = {a.name for a in functions}
        assert 'get_users' in names
        assert 'create_user' in names
        assert 'health_check' in names
        assert 'get_user_by_id' in names

    def test_extracts_classes(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        classes = [a for a in inventory.artifacts
                   if a.artifact_type == 'class' and a.language == 'python']
        names = {a.name for a in classes}
        assert 'UserService' in names

    def test_extracts_routes(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        routes = [a for a in inventory.artifacts
                  if a.artifact_type == 'route' and a.language == 'python']
        assert len(routes) >= 3  # GET /api/users, POST /api/users, /health
        details = {a.details for a in routes}
        assert 'GET /api/users' in details
        assert 'POST /api/users' in details
        assert 'ROUTE /health' in details

    def test_extracts_sqlalchemy_models(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        models = [a for a in inventory.artifacts
                  if a.artifact_type == 'model' and a.language == 'python']
        names = {a.name for a in models}
        assert 'User' in names
        assert 'Post' in names

    def test_async_functions(self, analyzer):
        """Test extraction of async def functions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "api.py").write_text(
                'async def fetch_data():\n'
                '    pass\n'
                '\n'
                'async def process_items(items):\n'
                '    pass\n'
            )
            inventory = analyzer.analyze(p)
            names = {a.name for a in inventory.artifacts}
            assert 'fetch_data' in names
            assert 'process_items' in names


class TestJavaScriptTypeScriptExtraction:
    """Test JS/TS artifact extraction."""

    def test_extracts_functions(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        js_ts_functions = [a for a in inventory.artifacts
                          if a.artifact_type == 'function'
                          and a.language in ('javascript', 'typescript')]
        names = {a.name for a in js_ts_functions}
        assert 'formatDate' in names
        assert 'calculateTotal' in names

    def test_extracts_react_components(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        components = [a for a in inventory.artifacts
                      if a.artifact_type == 'component']
        names = {a.name for a in components}
        assert 'Header' in names
        assert 'Footer' in names
        assert 'DashboardPage' in names

    def test_extracts_express_routes(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        js_routes = [a for a in inventory.artifacts
                     if a.artifact_type == 'route' and a.language == 'javascript']
        details = {a.details for a in js_routes}
        assert 'GET /api/items' in details
        assert 'POST /api/items' in details

    def test_nextjs_page_routes(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        page_routes = [a for a in inventory.artifacts
                       if a.artifact_type == 'route' and a.details and 'PAGE' in a.details]
        assert len(page_routes) >= 1
        assert any('/dashboard' in a.name for a in page_routes)

    def test_nextjs_api_routes(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        api_routes = [a for a in inventory.artifacts
                      if a.artifact_type == 'route' and a.details and 'API' in a.details]
        assert len(api_routes) >= 1
        assert any('/api/users' in a.name for a in api_routes)

    def test_class_declarations(self, analyzer):
        """Test class extraction from JS/TS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "service.ts").write_text(
                'export class UserService {\n'
                '  async getUser() {}\n'
                '}\n'
                '\n'
                'class InternalHelper {\n'
                '  help() {}\n'
                '}\n'
            )
            inventory = analyzer.analyze(p)
            classes = [a for a in inventory.artifacts if a.artifact_type == 'class']
            names = {a.name for a in classes}
            assert 'UserService' in names
            assert 'InternalHelper' in names


class TestSQLExtraction:
    """Test SQL artifact extraction."""

    def test_extracts_create_table(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        sql_models = [a for a in inventory.artifacts
                      if a.artifact_type == 'model' and a.language == 'sql']
        names = {a.name for a in sql_models}
        assert 'users' in names
        assert 'posts' in names

    def test_create_table_if_not_exists(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        sql_models = [a for a in inventory.artifacts
                      if a.artifact_type == 'model' and a.language == 'sql']
        assert any(a.name == 'posts' for a in sql_models)


class TestPrismaExtraction:
    """Test Prisma schema extraction."""

    def test_extracts_prisma_models(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        prisma_models = [a for a in inventory.artifacts
                         if a.artifact_type == 'model' and a.language == 'prisma']
        names = {a.name for a in prisma_models}
        assert 'User' in names
        assert 'Post' in names
        assert len(prisma_models) == 2


class TestSummary:
    """Test summary generation."""

    def test_summary_has_all_fields(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        s = inventory.summary
        assert 'total_files' in s
        assert 'total_lines' in s
        assert 'languages' in s
        assert 'function_count' in s
        assert 'class_count' in s
        assert 'route_count' in s
        assert 'component_count' in s
        assert 'model_count' in s

    def test_summary_counts_are_positive(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        s = inventory.summary
        assert s['total_files'] > 0
        assert s['total_lines'] > 0
        assert s['function_count'] > 0
        assert s['route_count'] > 0

    def test_to_summary_text(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        text = analyzer.to_summary_text(inventory)
        assert 'Files' in text
        assert 'Functions' in text
        assert 'Routes' in text
        assert 'Components' in text


class TestCodeInventoryHelpers:
    """Test CodeInventory helper methods."""

    def test_get_artifact_names(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        names = inventory.get_artifact_names()
        assert isinstance(names, list)
        assert len(names) > 0

    def test_get_artifacts_by_type(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        routes = inventory.get_artifacts_by_type('route')
        assert all(a.artifact_type == 'route' for a in routes)

    def test_get_file_paths(self, analyzer, mock_project):
        inventory = analyzer.analyze(mock_project)
        paths = inventory.get_file_paths()
        assert isinstance(paths, list)
        assert len(paths) > 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_binary_file_handling(self, analyzer, tmp_path):
        """Ensure binary files don't crash the analyzer."""
        (tmp_path / "data.py").write_bytes(b'\x00\x01\x02\x03def broken')
        # Should not raise
        inventory = analyzer.analyze(tmp_path)
        # May or may not find artifacts in binary file, but shouldn't crash

    def test_deeply_nested_files(self, analyzer, tmp_path):
        """Test deeply nested directory structure."""
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text('def deep_function():\n    pass\n')
        inventory = analyzer.analyze(tmp_path)
        names = {a.name for a in inventory.artifacts}
        assert 'deep_function' in names

    def test_unicode_content(self, analyzer, tmp_path):
        """Test files with unicode content."""
        (tmp_path / "i18n.py").write_text(
            '# -*- coding: utf-8 -*-\n'
            'def get_greeting():\n'
            '    return "Hola mundo!"\n'
        )
        inventory = analyzer.analyze(tmp_path)
        names = {a.name for a in inventory.artifacts}
        assert 'get_greeting' in names

    def test_skip_dirs_constant(self):
        """Verify all expected dirs are in SKIP_DIRS."""
        assert 'node_modules' in SKIP_DIRS
        assert '.git' in SKIP_DIRS
        assert '__pycache__' in SKIP_DIRS
        assert 'yokeflow' in SKIP_DIRS
        assert '.yokeflow' in SKIP_DIRS

    def test_language_map_extensions(self):
        """Verify all expected extensions are in LANGUAGE_MAP."""
        assert '.py' in LANGUAGE_MAP
        assert '.js' in LANGUAGE_MAP
        assert '.ts' in LANGUAGE_MAP
        assert '.tsx' in LANGUAGE_MAP
        assert '.jsx' in LANGUAGE_MAP
        assert '.sql' in LANGUAGE_MAP
        assert '.prisma' in LANGUAGE_MAP
