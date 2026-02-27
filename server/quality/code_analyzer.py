"""
Code Analyzer for Completion Review

Scans a generated project directory to build a structured inventory of
what was actually built: files, functions, classes, routes, components,
database models, etc.

Uses regex-based extraction (not AST) for cross-language support.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Directories to skip when scanning
SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', '.next', '.cache',
    'yokeflow', '.yokeflow', 'dist', 'build', '.venv', 'venv',
    'env', '.env', 'coverage', '.nyc_output', '.pytest_cache',
}

# Source file extensions and their language mapping
LANGUAGE_MAP = {
    '.py': 'python',
    '.js': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.jsx': 'javascript',
    '.sql': 'sql',
    '.html': 'html',
    '.css': 'css',
    '.scss': 'css',
    '.prisma': 'prisma',
}


@dataclass
class CodeArtifact:
    """A single detected code artifact (function, class, route, etc.)."""
    name: str
    artifact_type: str  # function, class, route, component, model
    file_path: str      # relative to project root
    line_number: int
    language: str
    details: str = ""   # e.g. "GET /api/users/:id" for routes


@dataclass
class CodeInventory:
    """Complete inventory of a scanned project."""
    project_path: str
    files: List[Dict] = field(default_factory=list)       # {path, language, lines}
    artifacts: List[CodeArtifact] = field(default_factory=list)
    summary: Dict = field(default_factory=dict)

    def get_artifact_names(self) -> List[str]:
        """Get all artifact names for keyword matching."""
        return [a.name for a in self.artifacts]

    def get_artifacts_by_type(self, artifact_type: str) -> List[CodeArtifact]:
        """Get artifacts filtered by type."""
        return [a for a in self.artifacts if a.artifact_type == artifact_type]

    def get_file_paths(self) -> List[str]:
        """Get all source file paths."""
        return [f['path'] for f in self.files]


class CodeAnalyzer:
    """
    Scans a project directory and builds a CodeInventory.

    Detects functions, classes, routes, React components, and DB models
    across Python, JavaScript, TypeScript, and SQL files.
    """

    def analyze(self, project_path: Path) -> CodeInventory:
        """
        Scan project directory and return a CodeInventory.

        Args:
            project_path: Root directory of the generated project

        Returns:
            CodeInventory with all detected files and artifacts
        """
        if not project_path.is_dir():
            raise ValueError(f"Project path is not a directory: {project_path}")

        inventory = CodeInventory(project_path=str(project_path))

        # Walk directory and collect source files
        for file_path in self._walk_source_files(project_path):
            rel_path = str(file_path.relative_to(project_path))
            ext = file_path.suffix.lower()
            language = LANGUAGE_MAP.get(ext, 'unknown')

            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                line_count = content.count('\n') + 1
            except Exception:
                continue

            inventory.files.append({
                'path': rel_path,
                'language': language,
                'lines': line_count,
            })

            # Extract artifacts from file content
            artifacts = self._extract_artifacts(content, rel_path, language)
            inventory.artifacts.extend(artifacts)

        # Build summary
        inventory.summary = self._build_summary(inventory)

        logger.info(
            f"Code analysis: {inventory.summary['total_files']} files, "
            f"{inventory.summary['total_lines']} lines, "
            f"{len(inventory.artifacts)} artifacts"
        )

        return inventory

    def _walk_source_files(self, project_path: Path):
        """Yield source files, skipping excluded directories."""
        for item in sorted(project_path.rglob('*')):
            if not item.is_file():
                continue

            # Skip files in excluded directories
            if any(part in SKIP_DIRS for part in item.relative_to(project_path).parts):
                continue

            # Only include known source extensions
            if item.suffix.lower() in LANGUAGE_MAP:
                yield item

    def _extract_artifacts(
        self, content: str, file_path: str, language: str
    ) -> List[CodeArtifact]:
        """Extract all code artifacts from a single file."""
        artifacts = []

        if language == 'python':
            artifacts.extend(self._extract_python(content, file_path))
        elif language in ('javascript', 'typescript'):
            artifacts.extend(self._extract_js_ts(content, file_path, language))
        elif language == 'sql':
            artifacts.extend(self._extract_sql(content, file_path))
        elif language == 'prisma':
            artifacts.extend(self._extract_prisma(content, file_path))

        return artifacts

    def _extract_python(self, content: str, file_path: str) -> List[CodeArtifact]:
        """Extract artifacts from Python files."""
        artifacts = []
        lines = content.split('\n')

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Functions
            m = re.match(r'^def\s+(\w+)\s*\(', stripped)
            if m:
                artifacts.append(CodeArtifact(
                    name=m.group(1), artifact_type='function',
                    file_path=file_path, line_number=i, language='python',
                ))
                continue

            # Async functions
            m = re.match(r'^async\s+def\s+(\w+)\s*\(', stripped)
            if m:
                artifacts.append(CodeArtifact(
                    name=m.group(1), artifact_type='function',
                    file_path=file_path, line_number=i, language='python',
                ))
                continue

            # SQLAlchemy models (check before generic class to tag correctly)
            m = re.match(r'^class\s+(\w+)\s*\(.*(?:Base|Model|db\.Model)', stripped)
            if m:
                artifacts.append(CodeArtifact(
                    name=m.group(1), artifact_type='model',
                    file_path=file_path, line_number=i, language='python',
                ))
                continue

            # Classes
            m = re.match(r'^class\s+(\w+)', stripped)
            if m:
                artifacts.append(CodeArtifact(
                    name=m.group(1), artifact_type='class',
                    file_path=file_path, line_number=i, language='python',
                ))
                continue

            # Flask/FastAPI routes
            m = re.match(r'^@app\.(get|post|put|delete|patch)\s*\(\s*[\'"](.+?)[\'"]', stripped)
            if m:
                method = m.group(1).upper()
                path = m.group(2)
                artifacts.append(CodeArtifact(
                    name=path, artifact_type='route',
                    file_path=file_path, line_number=i, language='python',
                    details=f"{method} {path}",
                ))
                continue

            # Flask @app.route
            m = re.match(r'^@app\.route\s*\(\s*[\'"](.+?)[\'"]', stripped)
            if m:
                path = m.group(1)
                artifacts.append(CodeArtifact(
                    name=path, artifact_type='route',
                    file_path=file_path, line_number=i, language='python',
                    details=f"ROUTE {path}",
                ))

        return artifacts

    def _extract_js_ts(
        self, content: str, file_path: str, language: str
    ) -> List[CodeArtifact]:
        """Extract artifacts from JavaScript/TypeScript files."""
        artifacts = []
        lines = content.split('\n')

        has_default_export = 'export default' in content
        file_stem = Path(file_path).stem

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Named function declarations
            m = re.match(r'^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(', stripped)
            if m:
                name = m.group(1)
                # React component detection: PascalCase + returns JSX
                is_component = (
                    name[0].isupper()
                    and (file_path.endswith('.tsx') or file_path.endswith('.jsx'))
                )
                atype = 'component' if is_component else 'function'
                artifacts.append(CodeArtifact(
                    name=name, artifact_type=atype,
                    file_path=file_path, line_number=i, language=language,
                ))
                continue

            # Arrow function / const assignments (top-level only)
            m = re.match(r'^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(', stripped)
            if m:
                name = m.group(1)
                is_component = (
                    name[0].isupper()
                    and (file_path.endswith('.tsx') or file_path.endswith('.jsx'))
                )
                atype = 'component' if is_component else 'function'
                artifacts.append(CodeArtifact(
                    name=name, artifact_type=atype,
                    file_path=file_path, line_number=i, language=language,
                ))
                continue

            # Class declarations
            m = re.match(r'^(?:export\s+)?class\s+(\w+)', stripped)
            if m:
                artifacts.append(CodeArtifact(
                    name=m.group(1), artifact_type='class',
                    file_path=file_path, line_number=i, language=language,
                ))
                continue

            # Express/Hono routes: app.get('/path', ...) or router.post('/path', ...)
            m = re.match(
                r'^(?:app|router|server)\.(get|post|put|delete|patch|all)\s*\(\s*[\'"`](.+?)[\'"`]',
                stripped
            )
            if m:
                method = m.group(1).upper()
                path = m.group(2)
                artifacts.append(CodeArtifact(
                    name=path, artifact_type='route',
                    file_path=file_path, line_number=i, language=language,
                    details=f"{method} {path}",
                ))
                continue

        # Next.js page detection: files in app/ directory
        if '/app/' in file_path and file_path.endswith('page.tsx'):
            route_path = self._nextjs_route_from_path(file_path)
            if route_path:
                artifacts.append(CodeArtifact(
                    name=route_path, artifact_type='route',
                    file_path=file_path, line_number=1, language=language,
                    details=f"PAGE {route_path}",
                ))

        # Next.js API route detection
        if '/app/' in file_path and file_path.endswith('route.ts'):
            route_path = self._nextjs_route_from_path(file_path)
            if route_path:
                artifacts.append(CodeArtifact(
                    name=route_path, artifact_type='route',
                    file_path=file_path, line_number=1, language=language,
                    details=f"API {route_path}",
                ))

        return artifacts

    def _nextjs_route_from_path(self, file_path: str) -> Optional[str]:
        """Convert Next.js file path to route path."""
        # src/app/dashboard/page.tsx -> /dashboard
        # app/api/users/route.ts -> /api/users
        m = re.search(r'(?:src/)?app(/.*?)(?:/page\.tsx|/route\.ts)$', file_path)
        if m:
            return m.group(1) or '/'
        return None

    def _extract_sql(self, content: str, file_path: str) -> List[CodeArtifact]:
        """Extract artifacts from SQL files."""
        artifacts = []
        lines = content.split('\n')

        for i, line in enumerate(lines, start=1):
            # CREATE TABLE
            m = re.match(r'^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)', line, re.IGNORECASE)
            if m:
                artifacts.append(CodeArtifact(
                    name=m.group(1), artifact_type='model',
                    file_path=file_path, line_number=i, language='sql',
                    details=f"TABLE {m.group(1)}",
                ))

        return artifacts

    def _extract_prisma(self, content: str, file_path: str) -> List[CodeArtifact]:
        """Extract artifacts from Prisma schema files."""
        artifacts = []
        lines = content.split('\n')

        for i, line in enumerate(lines, start=1):
            m = re.match(r'^\s*model\s+(\w+)\s*\{', line)
            if m:
                artifacts.append(CodeArtifact(
                    name=m.group(1), artifact_type='model',
                    file_path=file_path, line_number=i, language='prisma',
                    details=f"MODEL {m.group(1)}",
                ))

        return artifacts

    def _build_summary(self, inventory: CodeInventory) -> Dict:
        """Build summary statistics from inventory."""
        languages: Dict[str, int] = {}
        total_lines = 0

        for f in inventory.files:
            lang = f['language']
            languages[lang] = languages.get(lang, 0) + 1
            total_lines += f['lines']

        type_counts: Dict[str, int] = {}
        for a in inventory.artifacts:
            type_counts[a.artifact_type] = type_counts.get(a.artifact_type, 0) + 1

        return {
            'total_files': len(inventory.files),
            'total_lines': total_lines,
            'languages': languages,
            'function_count': type_counts.get('function', 0),
            'class_count': type_counts.get('class', 0),
            'route_count': type_counts.get('route', 0),
            'component_count': type_counts.get('component', 0),
            'model_count': type_counts.get('model', 0),
        }

    def to_summary_text(self, inventory: CodeInventory) -> str:
        """Generate a human-readable summary for Claude prompt."""
        s = inventory.summary
        lines = [
            f"**Project**: {inventory.project_path}",
            f"**Files**: {s['total_files']} source files, {s['total_lines']} total lines",
            f"**Languages**: {', '.join(f'{lang} ({count})' for lang, count in sorted(s['languages'].items()))}",
            f"**Functions**: {s['function_count']}",
            f"**Classes**: {s['class_count']}",
            f"**Routes/Endpoints**: {s['route_count']}",
            f"**Components**: {s['component_count']}",
            f"**DB Models/Tables**: {s['model_count']}",
        ]

        # List routes
        routes = inventory.get_artifacts_by_type('route')
        if routes:
            lines.append("")
            lines.append("**Routes:**")
            for r in routes[:30]:  # Cap at 30
                lines.append(f"- {r.details or r.name} ({r.file_path})")

        # List components
        components = inventory.get_artifacts_by_type('component')
        if components:
            lines.append("")
            lines.append("**Components:**")
            for c in components[:30]:
                lines.append(f"- {c.name} ({c.file_path})")

        # List models
        models = inventory.get_artifacts_by_type('model')
        if models:
            lines.append("")
            lines.append("**Database Models/Tables:**")
            for m in models[:20]:
                lines.append(f"- {m.details or m.name} ({m.file_path})")

        return '\n'.join(lines)
