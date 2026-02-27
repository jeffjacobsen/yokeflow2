"""
Implementation Reviewer for Completion Review

After all coding sessions complete, verifies that the actual generated code
implements what was requested in the specification.

Orchestrates: SpecParser + CodeAnalyzer + TestResultCollector + Claude review.

Output shape matches what store_completion_review() expects so all downstream
code (DB, API, UI) works unchanged.
"""

import re
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from uuid import UUID

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

from server.quality.spec_parser import SpecificationParser, Requirement, ParsedSpecification
from server.quality.code_analyzer import CodeAnalyzer, CodeInventory
from server.quality.test_result_collector import TestResultCollector, TestEvidence
from server.client.prompts import load_prompt

if TYPE_CHECKING:
    from server.database.operations import TaskDatabase

logger = logging.getLogger(__name__)


@dataclass
class RequirementMatch:
    """
    A match between a spec requirement and code/test evidence.

    Attribute names must match what store_completion_review() accesses:
    match.requirement.id, match.status, match.matched_epic_ids, etc.
    """
    requirement: Requirement
    status: str = "missing"          # met, partial, missing
    matched_epic_ids: List[int] = field(default_factory=list)
    matched_task_ids: List[int] = field(default_factory=list)
    match_confidence: float = 0.0    # 0.0-1.0
    implementation_notes: str = ""   # code evidence details


class ImplementationReviewer:
    """
    Orchestrates the completion review: spec parsing, code analysis,
    test evidence collection, matching, Claude review, and scoring.
    """

    def __init__(self, review_model: str = "claude-sonnet-4-6"):
        self.review_model = review_model
        self.parser = SpecificationParser()
        self.code_analyzer = CodeAnalyzer()
        self.test_collector = TestResultCollector()

    async def review_implementation(
        self,
        project_id: UUID,
        db: "TaskDatabase"
    ) -> Dict[str, Any]:
        """
        Run a full implementation review for a completed project.

        Args:
            project_id: Project UUID
            db: Database connection

        Returns:
            Review data dict compatible with store_completion_review()
        """
        # 1. Get project info
        project = await db.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        project_path = Path(project.get('local_path', ''))
        if not project_path.is_dir():
            raise ValueError(f"Project directory not found: {project_path}")

        # 2. Parse spec
        spec_file_path = project.get('spec_file_path', '')
        spec_path = project_path / spec_file_path if spec_file_path else None

        if spec_path and spec_path.exists():
            parsed_spec = self.parser.parse_spec(spec_path)
        else:
            # Fall back to spec_content from DB
            spec_content = project.get('spec_content', '')
            if not spec_content:
                raise ValueError("No spec file or content found for project")
            parsed_spec = self._parse_spec_from_content(spec_content, str(project_path))

        # 3. Analyze code
        code_inventory = self.code_analyzer.analyze(project_path)

        # 4. Collect test evidence
        test_evidence = await self.test_collector.collect(project_id, db)

        # 5. Match requirements to code + tests
        matches = self._match_requirements(
            parsed_spec, code_inventory, test_evidence
        )

        # 6. Calculate metrics
        metrics = self._calculate_metrics(matches, test_evidence)

        # 7. Generate Claude review
        review_text, executive_summary = await self._generate_claude_review(
            project, parsed_spec, code_inventory, test_evidence, matches, metrics
        )

        # 8. Calculate final score
        overall_score = self._calculate_score(metrics, test_evidence)
        recommendation = self._determine_recommendation(overall_score, metrics)

        # Build output dict matching store_completion_review() expectations
        return {
            'project_id': str(project_id),
            'spec_file_path': spec_file_path or 'spec_content',
            'spec_hash': parsed_spec.spec_hash,
            'spec_parsed_at': datetime.now(timezone.utc).isoformat(),
            'requirements_total': len(parsed_spec.requirements),
            'requirements_met': metrics['met'],
            'requirements_missing': metrics['missing'],
            'requirements_extra': 0,  # not applicable for implementation review
            'coverage_percentage': metrics['coverage_pct'],
            'overall_score': overall_score,
            'recommendation': recommendation,
            'executive_summary': executive_summary,
            'review_text': review_text,
            'review_model': self.review_model,
            'matches': matches,
        }

    def _parse_spec_from_content(
        self, content: str, project_path: str
    ) -> ParsedSpecification:
        """Parse spec from DB content string when no file exists."""
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.md', delete=False
        ) as f:
            f.write(content)
            f.flush()
            return self.parser.parse_spec(Path(f.name))

    def _match_requirements(
        self,
        spec: ParsedSpecification,
        code: CodeInventory,
        tests: TestEvidence,
    ) -> List[RequirementMatch]:
        """
        Match each spec requirement against code artifacts and test results.

        Uses keyword matching on artifact names, file paths, and route paths.
        """
        # Build searchable text from code artifacts
        artifact_names = {a.name.lower() for a in code.artifacts}
        artifact_details = {a.details.lower() for a in code.artifacts if a.details}
        file_paths = {f['path'].lower() for f in code.files}

        # Build a combined searchable text per file
        file_keywords: Dict[str, set] = {}
        for a in code.artifacts:
            fp = a.file_path.lower()
            if fp not in file_keywords:
                file_keywords[fp] = set()
            file_keywords[fp].add(a.name.lower())
            if a.details:
                file_keywords[fp].update(a.details.lower().split())

        matches = []
        for req in spec.requirements:
            match = self._match_single_requirement(
                req, code, artifact_names, artifact_details,
                file_paths, file_keywords, tests
            )
            matches.append(match)

        return matches

    def _match_single_requirement(
        self,
        req: Requirement,
        code: CodeInventory,
        artifact_names: set,
        artifact_details: set,
        file_paths: set,
        file_keywords: Dict[str, set],
        tests: TestEvidence,
    ) -> RequirementMatch:
        """Match a single requirement against code and test evidence."""
        keywords = [kw.lower() for kw in req.keywords]
        if not keywords:
            return RequirementMatch(requirement=req)

        # Score: how many keywords appear in code artifacts/files
        matched_artifacts = []
        matched_files = set()

        for artifact in code.artifacts:
            name_lower = artifact.name.lower()
            details_lower = (artifact.details or '').lower()
            file_lower = artifact.file_path.lower()

            # Check keyword overlap
            hits = sum(
                1 for kw in keywords
                if kw in name_lower or kw in details_lower or kw in file_lower
            )
            if hits > 0:
                matched_artifacts.append(artifact)
                matched_files.add(artifact.file_path)

        # Also check file paths directly
        for f in code.files:
            fp = f['path'].lower()
            hits = sum(1 for kw in keywords if kw in fp)
            if hits > 0:
                matched_files.add(f['path'])

        # Calculate confidence from code matches
        if not keywords:
            code_confidence = 0.0
        else:
            # Proportion of keywords that appeared somewhere in code
            keywords_found = set()
            for kw in keywords:
                for a in matched_artifacts:
                    if kw in a.name.lower() or kw in (a.details or '').lower():
                        keywords_found.add(kw)
                        break
                else:
                    for fp in matched_files:
                        if kw in fp.lower():
                            keywords_found.add(kw)
                            break
            code_confidence = len(keywords_found) / len(keywords)

        # Check test evidence for related tasks
        test_boost = 0.0
        related_tasks = []
        for te in tests.by_task:
            task_lower = te.task_name.lower()
            overlap = sum(1 for kw in keywords if kw in task_lower)
            if overlap > 0:
                related_tasks.append(te)
                if te.tests_passed > 0 and te.tests_failed == 0:
                    test_boost = max(test_boost, 0.2)  # Passing tests boost
                elif te.tests_failed > 0:
                    test_boost = min(test_boost, -0.1)  # Failed tests penalize

        # Combined confidence
        confidence = min(1.0, max(0.0, code_confidence + test_boost))

        # Determine status
        if confidence >= 0.5:
            status = "met"
        elif confidence >= 0.25:
            status = "partial"
        else:
            status = "missing"

        # Build implementation notes
        notes_parts = []
        if matched_files:
            notes_parts.append(f"Files: {', '.join(sorted(matched_files)[:5])}")
        if matched_artifacts:
            artifact_descs = []
            for a in matched_artifacts[:5]:
                desc = f"{a.artifact_type}: {a.name}"
                if a.details:
                    desc += f" ({a.details})"
                artifact_descs.append(desc)
            notes_parts.append(f"Artifacts: {'; '.join(artifact_descs)}")
        if related_tasks:
            for te in related_tasks[:3]:
                notes_parts.append(f"Task '{te.task_name}': {te.summary}")

        return RequirementMatch(
            requirement=req,
            status=status,
            matched_epic_ids=[te.epic_id for te in related_tasks[:5]],
            matched_task_ids=[te.task_id for te in related_tasks[:5]],
            match_confidence=round(confidence, 2),
            implementation_notes='; '.join(notes_parts) if notes_parts else 'No matching code found',
        )

    def _calculate_metrics(
        self,
        matches: List[RequirementMatch],
        tests: TestEvidence,
    ) -> Dict[str, Any]:
        """Calculate aggregate metrics from matches."""
        met = sum(1 for m in matches if m.status == 'met')
        partial = sum(1 for m in matches if m.status == 'partial')
        missing = sum(1 for m in matches if m.status == 'missing')
        total = len(matches)

        # Coverage: met counts full, partial counts half
        coverage_pct = ((met + 0.5 * partial) / total * 100) if total > 0 else 0.0

        return {
            'met': met,
            'partial': partial,
            'missing': missing,
            'total': total,
            'coverage_pct': round(coverage_pct, 1),
            'test_pass_rate': tests.pass_rate,
        }

    def _calculate_score(
        self, metrics: Dict, tests: TestEvidence
    ) -> int:
        """
        Calculate overall score (1-100).

        Weights:
        - 40% code presence (coverage_pct)
        - 30% test pass rate
        - 30% structural completeness (met / total)
        """
        coverage_score = metrics['coverage_pct']  # 0-100
        test_score = tests.pass_rate * 100         # 0-100
        met_ratio = (metrics['met'] / metrics['total'] * 100) if metrics['total'] > 0 else 0

        raw = (0.4 * coverage_score) + (0.3 * test_score) + (0.3 * met_ratio)

        # Penalty for high-priority missing requirements
        # (spec_parser marks "must"/"required" as high priority)
        high_missing = 0
        # We don't have direct access to matches here, so this is done in the score
        # The coverage_pct already accounts for missing requirements

        return max(1, min(100, round(raw)))

    def _determine_recommendation(self, score: int, metrics: Dict) -> str:
        """Determine recommendation based on score and metrics."""
        if score >= 75 and metrics['missing'] == 0:
            return 'complete'
        elif score >= 50:
            return 'needs_work'
        else:
            return 'failed'

    async def _generate_claude_review(
        self,
        project: Dict,
        spec: ParsedSpecification,
        code: CodeInventory,
        tests: TestEvidence,
        matches: List[RequirementMatch],
        metrics: Dict,
    ) -> tuple:
        """Generate Claude-powered review. Returns (review_text, executive_summary)."""
        # Load and fill prompt template
        prompt_template = load_prompt('completion_review_prompt')

        # Build spec text (truncated)
        spec_content = project.get('spec_content', '')
        if not spec_content:
            spec_path = Path(project.get('local_path', '')) / project.get('spec_file_path', '')
            if spec_path.exists():
                spec_content = spec_path.read_text()[:5000]
        spec_text = spec_content[:5000] if spec_content else "(spec not available)"

        # Build requirements table
        req_table = self._build_requirements_table(matches)

        # Fill template
        prompt = prompt_template.format(
            spec_text=spec_text,
            code_inventory=self.code_analyzer.to_summary_text(code),
            test_results=tests.to_summary_text(),
            requirements_table=req_table,
        )

        # Call Claude via Agent SDK (same pattern as reviews.py)
        client = ClaudeSDKClient(options=ClaudeAgentOptions(
            model=self.review_model,
            system_prompt=(
                "You are a software implementation reviewer. "
                "ALL necessary data is provided in the user message. "
                "Provide your analysis as pure Markdown text. "
                "DO NOT attempt to read files, run commands, or use any tools."
            ),
            permission_mode="bypassPermissions",
            mcp_servers={},
            max_turns=1,
        ))

        review_text = ""
        async with client:
            await client.query(prompt)
            async for msg in client.receive_response():
                if type(msg).__name__ == "AssistantMessage" and hasattr(msg, "content"):
                    for block in msg.content:
                        if type(block).__name__ == "TextBlock" and hasattr(block, "text"):
                            review_text += block.text

        executive_summary = self._extract_executive_summary(review_text)
        return review_text, executive_summary

    def _build_requirements_table(self, matches: List[RequirementMatch]) -> str:
        """Build a markdown table of requirements and their code matches."""
        lines = [
            "| # | Requirement | Status | Confidence | Evidence |",
            "|---|-----------|--------|-----------|---------|",
        ]
        for m in matches:
            status_icon = {'met': 'MET', 'partial': 'PARTIAL', 'missing': 'MISSING'}.get(m.status, '?')
            text = m.requirement.text[:60] + ('...' if len(m.requirement.text) > 60 else '')
            notes = m.implementation_notes[:80] + ('...' if len(m.implementation_notes) > 80 else '')
            lines.append(
                f"| {m.requirement.id} | {text} | {status_icon} | "
                f"{m.match_confidence:.0%} | {notes} |"
            )
        return '\n'.join(lines)

    def _extract_executive_summary(self, review_text: str) -> str:
        """Extract the Executive Summary section from Claude's response."""
        # Look for content between "Executive Summary" and the next "###"
        m = re.search(
            r'###?\s*\d*\.?\s*Executive\s+Summary\s*\n+(.*?)(?=\n###|\Z)',
            review_text, re.DOTALL | re.IGNORECASE
        )
        if m:
            return m.group(1).strip()[:500]
        # Fallback: first paragraph
        paragraphs = review_text.strip().split('\n\n')
        return paragraphs[0][:500] if paragraphs else "Review completed."

