"""
Tests for Implementation Reviewer (Completion Review)
======================================================

Tests the ImplementationReviewer orchestration: spec parsing, code analysis,
test evidence collection, requirement matching, scoring, and review generation.
"""

import pytest
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from dataclasses import dataclass, field
from typing import List, Dict

from server.quality.implementation_reviewer import (
    ImplementationReviewer,
    RequirementMatch,
)
from server.quality.spec_parser import Requirement, ParsedSpecification
from server.quality.code_analyzer import CodeAnalyzer, CodeInventory, CodeArtifact
from server.quality.test_result_collector import (
    TestResultCollector, TestEvidence, TaskTestEvidence,
)


# ---- Fixtures ----

@pytest.fixture
def reviewer():
    return ImplementationReviewer(review_model="claude-sonnet-4-6")


@pytest.fixture
def sample_spec():
    """A parsed specification with test requirements."""
    return ParsedSpecification(
        overview="Test application with auth, dashboard, API, database, and notifications",
        spec_hash="abc123",
        requirements=[
            Requirement(
                id="REQ-1",
                section="Authentication",
                text="User login with email and password",
                keywords=["login", "email", "password", "auth"],
                priority="high",
            ),
            Requirement(
                id="REQ-2",
                section="Dashboard",
                text="Display user dashboard with stats",
                keywords=["dashboard", "stats", "display"],
                priority="medium",
            ),
            Requirement(
                id="REQ-3",
                section="API",
                text="REST API for user management",
                keywords=["api", "user", "rest", "endpoint"],
                priority="high",
            ),
            Requirement(
                id="REQ-4",
                section="Database",
                text="PostgreSQL database with user table",
                keywords=["database", "postgresql", "user", "table"],
                priority="high",
            ),
            Requirement(
                id="REQ-5",
                section="Notifications",
                text="Email notification system",
                keywords=["email", "notification", "send"],
                priority="low",
            ),
        ],
    )


@pytest.fixture
def sample_code_inventory():
    """A code inventory matching some requirements."""
    return CodeInventory(
        project_path="/tmp/test-project",
        files=[
            {"path": "server/auth.py", "language": "python", "lines": 100},
            {"path": "server/api/users.py", "language": "python", "lines": 80},
            {"path": "src/components/Dashboard.tsx", "language": "typescript", "lines": 150},
            {"path": "schema/schema.sql", "language": "sql", "lines": 30},
        ],
        artifacts=[
            CodeArtifact(
                name="login", artifact_type="function",
                file_path="server/auth.py", line_number=10,
                language="python", details="",
            ),
            CodeArtifact(
                name="verify_password", artifact_type="function",
                file_path="server/auth.py", line_number=25,
                language="python", details="",
            ),
            CodeArtifact(
                name="/api/users", artifact_type="route",
                file_path="server/api/users.py", line_number=5,
                language="python", details="GET /api/users",
            ),
            CodeArtifact(
                name="/api/users", artifact_type="route",
                file_path="server/api/users.py", line_number=20,
                language="python", details="POST /api/users",
            ),
            CodeArtifact(
                name="Dashboard", artifact_type="component",
                file_path="src/components/Dashboard.tsx", line_number=1,
                language="typescript", details="",
            ),
            CodeArtifact(
                name="users", artifact_type="model",
                file_path="schema/schema.sql", line_number=1,
                language="sql", details="TABLE users",
            ),
        ],
        summary={
            "total_files": 4,
            "total_lines": 360,
            "languages": {"python": 2, "typescript": 1, "sql": 1},
            "function_count": 2,
            "class_count": 0,
            "route_count": 2,
            "component_count": 1,
            "model_count": 1,
        },
    )


@pytest.fixture
def sample_test_evidence():
    """Test evidence with some passing and failing tests."""
    evidence = TestEvidence(
        total_tests=5,
        passed=4,
        failed=1,
        pending=0,
        pass_rate=0.8,
        by_task=[
            TaskTestEvidence(
                task_id=1,
                task_name="Implement login endpoint",
                epic_id=1,
                epic_name="Authentication",
                task_status="completed",
                tests_passed=2,
                tests_failed=0,
            ),
            TaskTestEvidence(
                task_id=2,
                task_name="Create dashboard UI",
                epic_id=2,
                epic_name="Dashboard",
                task_status="completed",
                tests_passed=1,
                tests_failed=0,
            ),
            TaskTestEvidence(
                task_id=3,
                task_name="Add user API endpoints",
                epic_id=1,
                epic_name="Authentication",
                task_status="completed",
                tests_passed=1,
                tests_failed=1,
            ),
        ],
        by_epic={},
    )
    return evidence


# ---- RequirementMatch Tests ----

class TestRequirementMatch:
    """Test RequirementMatch dataclass."""

    def test_default_values(self):
        req = Requirement(id="R1", section="Test", text="test", keywords=[], priority="high")
        match = RequirementMatch(requirement=req)
        assert match.status == "missing"
        assert match.matched_epic_ids == []
        assert match.matched_task_ids == []
        assert match.match_confidence == 0.0
        assert match.implementation_notes == ""

    def test_custom_values(self):
        req = Requirement(id="R1", section="Test", text="test", keywords=[], priority="high")
        match = RequirementMatch(
            requirement=req,
            status="met",
            matched_epic_ids=[1, 2],
            matched_task_ids=[10, 20],
            match_confidence=0.85,
            implementation_notes="Found in auth.py",
        )
        assert match.status == "met"
        assert match.matched_epic_ids == [1, 2]
        assert match.match_confidence == 0.85


# ---- Requirement Matching Tests ----

class TestRequirementMatching:
    """Test the _match_requirements logic."""

    def test_matches_login_requirement(
        self, reviewer, sample_spec, sample_code_inventory, sample_test_evidence
    ):
        matches = reviewer._match_requirements(
            sample_spec, sample_code_inventory, sample_test_evidence
        )
        login_match = next(m for m in matches if m.requirement.id == "REQ-1")
        assert login_match.status == "met"
        assert login_match.match_confidence > 0

    def test_matches_dashboard_requirement(
        self, reviewer, sample_spec, sample_code_inventory, sample_test_evidence
    ):
        matches = reviewer._match_requirements(
            sample_spec, sample_code_inventory, sample_test_evidence
        )
        dashboard_match = next(m for m in matches if m.requirement.id == "REQ-2")
        assert dashboard_match.status in ("met", "partial")

    def test_matches_api_requirement(
        self, reviewer, sample_spec, sample_code_inventory, sample_test_evidence
    ):
        matches = reviewer._match_requirements(
            sample_spec, sample_code_inventory, sample_test_evidence
        )
        api_match = next(m for m in matches if m.requirement.id == "REQ-3")
        # "api" and "user" keywords match, "rest" and "endpoint" don't appear literally
        assert api_match.status in ("met", "partial")
        assert api_match.match_confidence > 0

    def test_missing_notification_requirement(
        self, reviewer, sample_spec, sample_code_inventory, sample_test_evidence
    ):
        """Notification system has no matching code."""
        matches = reviewer._match_requirements(
            sample_spec, sample_code_inventory, sample_test_evidence
        )
        notif_match = next(m for m in matches if m.requirement.id == "REQ-5")
        # "email" keyword appears in auth context but "notification" and "send" don't
        # Should be partial at best
        assert notif_match.status in ("partial", "missing")

    def test_all_requirements_get_a_match(
        self, reviewer, sample_spec, sample_code_inventory, sample_test_evidence
    ):
        matches = reviewer._match_requirements(
            sample_spec, sample_code_inventory, sample_test_evidence
        )
        assert len(matches) == len(sample_spec.requirements)

    def test_empty_keywords_returns_missing(self, reviewer, sample_code_inventory, sample_test_evidence):
        spec = ParsedSpecification(
            overview="Test",
            spec_hash="test",
            requirements=[
                Requirement(id="R-EMPTY", section="Test", text="No keywords", keywords=[], priority="low"),
            ],
        )
        matches = reviewer._match_requirements(spec, sample_code_inventory, sample_test_evidence)
        assert len(matches) == 1
        assert matches[0].status == "missing"
        assert matches[0].match_confidence == 0.0

    def test_implementation_notes_contain_evidence(
        self, reviewer, sample_spec, sample_code_inventory, sample_test_evidence
    ):
        matches = reviewer._match_requirements(
            sample_spec, sample_code_inventory, sample_test_evidence
        )
        login_match = next(m for m in matches if m.requirement.id == "REQ-1")
        assert login_match.implementation_notes != ""
        assert login_match.implementation_notes != "No matching code found"

    def test_test_boost_for_passing_tests(
        self, reviewer, sample_spec, sample_code_inventory, sample_test_evidence
    ):
        """Tasks with passing tests should boost confidence."""
        matches = reviewer._match_requirements(
            sample_spec, sample_code_inventory, sample_test_evidence
        )
        login_match = next(m for m in matches if m.requirement.id == "REQ-1")
        # Login has matching code AND passing tests → should have high confidence
        assert login_match.match_confidence >= 0.5


# ---- Metrics Tests ----

class TestMetricsCalculation:
    """Test _calculate_metrics."""

    def test_all_met(self, reviewer):
        req = Requirement(id="R1", section="T", text="t", keywords=[], priority="high")
        matches = [
            RequirementMatch(requirement=req, status="met"),
            RequirementMatch(requirement=req, status="met"),
        ]
        evidence = TestEvidence(pass_rate=1.0)
        metrics = reviewer._calculate_metrics(matches, evidence)
        assert metrics['met'] == 2
        assert metrics['missing'] == 0
        assert metrics['coverage_pct'] == 100.0

    def test_all_missing(self, reviewer):
        req = Requirement(id="R1", section="T", text="t", keywords=[], priority="high")
        matches = [
            RequirementMatch(requirement=req, status="missing"),
            RequirementMatch(requirement=req, status="missing"),
        ]
        evidence = TestEvidence(pass_rate=0.0)
        metrics = reviewer._calculate_metrics(matches, evidence)
        assert metrics['met'] == 0
        assert metrics['missing'] == 2
        assert metrics['coverage_pct'] == 0.0

    def test_partial_counts_half(self, reviewer):
        req = Requirement(id="R1", section="T", text="t", keywords=[], priority="high")
        matches = [
            RequirementMatch(requirement=req, status="partial"),
            RequirementMatch(requirement=req, status="partial"),
        ]
        evidence = TestEvidence(pass_rate=0.5)
        metrics = reviewer._calculate_metrics(matches, evidence)
        assert metrics['partial'] == 2
        assert metrics['coverage_pct'] == 50.0  # 2 * 0.5 / 2 * 100

    def test_mixed_statuses(self, reviewer):
        req = Requirement(id="R1", section="T", text="t", keywords=[], priority="high")
        matches = [
            RequirementMatch(requirement=req, status="met"),
            RequirementMatch(requirement=req, status="partial"),
            RequirementMatch(requirement=req, status="missing"),
        ]
        evidence = TestEvidence(pass_rate=0.5)
        metrics = reviewer._calculate_metrics(matches, evidence)
        assert metrics['met'] == 1
        assert metrics['partial'] == 1
        assert metrics['missing'] == 1
        # (1 + 0.5) / 3 * 100 = 50.0
        assert metrics['coverage_pct'] == 50.0

    def test_empty_matches(self, reviewer):
        evidence = TestEvidence(pass_rate=0.0)
        metrics = reviewer._calculate_metrics([], evidence)
        assert metrics['total'] == 0
        assert metrics['coverage_pct'] == 0.0


# ---- Scoring Tests ----

class TestScoring:
    """Test _calculate_score."""

    def test_perfect_score(self, reviewer):
        metrics = {'coverage_pct': 100.0, 'met': 10, 'total': 10, 'missing': 0}
        evidence = TestEvidence(pass_rate=1.0)
        score = reviewer._calculate_score(metrics, evidence)
        assert score == 100

    def test_zero_score(self, reviewer):
        metrics = {'coverage_pct': 0.0, 'met': 0, 'total': 10, 'missing': 10}
        evidence = TestEvidence(pass_rate=0.0)
        score = reviewer._calculate_score(metrics, evidence)
        assert score == 1  # Minimum score

    def test_score_in_range(self, reviewer):
        metrics = {'coverage_pct': 60.0, 'met': 6, 'total': 10, 'missing': 2}
        evidence = TestEvidence(pass_rate=0.8)
        score = reviewer._calculate_score(metrics, evidence)
        assert 1 <= score <= 100

    def test_score_weights(self, reviewer):
        """Score should weight: 40% coverage, 30% tests, 30% met ratio."""
        metrics = {'coverage_pct': 50.0, 'met': 5, 'total': 10, 'missing': 5}
        evidence = TestEvidence(pass_rate=0.5)
        score = reviewer._calculate_score(metrics, evidence)
        # Expected: 0.4*50 + 0.3*50 + 0.3*50 = 20+15+15 = 50
        assert score == 50


# ---- Recommendation Tests ----

class TestRecommendation:
    """Test _determine_recommendation."""

    def test_complete(self, reviewer):
        assert reviewer._determine_recommendation(80, {'missing': 0}) == 'complete'

    def test_complete_requires_no_missing(self, reviewer):
        assert reviewer._determine_recommendation(80, {'missing': 1}) == 'needs_work'

    def test_needs_work(self, reviewer):
        assert reviewer._determine_recommendation(60, {'missing': 2}) == 'needs_work'

    def test_failed(self, reviewer):
        assert reviewer._determine_recommendation(30, {'missing': 5}) == 'failed'

    def test_boundary_75(self, reviewer):
        assert reviewer._determine_recommendation(75, {'missing': 0}) == 'complete'

    def test_boundary_50(self, reviewer):
        assert reviewer._determine_recommendation(50, {'missing': 1}) == 'needs_work'

    def test_boundary_49(self, reviewer):
        assert reviewer._determine_recommendation(49, {'missing': 1}) == 'failed'


# ---- Requirements Table Tests ----

class TestRequirementsTable:
    """Test _build_requirements_table."""

    def test_table_format(self, reviewer):
        req = Requirement(id="REQ-1", section="Auth", text="Login feature", keywords=["login"], priority="high")
        matches = [RequirementMatch(
            requirement=req, status="met",
            match_confidence=0.9,
            implementation_notes="Found in auth.py"
        )]
        table = reviewer._build_requirements_table(matches)
        assert '| REQ-1 |' in table
        assert 'MET' in table
        assert '90%' in table

    def test_long_text_truncated(self, reviewer):
        long_text = "A" * 100
        req = Requirement(id="R1", section="T", text=long_text, keywords=[], priority="high")
        matches = [RequirementMatch(requirement=req, status="missing")]
        table = reviewer._build_requirements_table(matches)
        assert '...' in table


# ---- Executive Summary Extraction ----

class TestExecutiveSummaryExtraction:
    """Test _extract_executive_summary."""

    def test_extracts_summary_section(self, reviewer):
        review_text = (
            "### Executive Summary\n\n"
            "The project is well implemented.\n\n"
            "### Implementation Coverage\n\n"
            "All requirements met."
        )
        summary = reviewer._extract_executive_summary(review_text)
        assert "well implemented" in summary

    def test_extracts_numbered_header(self, reviewer):
        review_text = (
            "### 1. Executive Summary\n\n"
            "Good implementation.\n\n"
            "### 2. Coverage\n\n"
            "Details."
        )
        summary = reviewer._extract_executive_summary(review_text)
        assert "Good implementation" in summary

    def test_fallback_to_first_paragraph(self, reviewer):
        review_text = "This is a review of the project.\n\nMore details follow."
        summary = reviewer._extract_executive_summary(review_text)
        assert "review of the project" in summary

    def test_truncates_long_summary(self, reviewer):
        long_summary = "A" * 600
        review_text = f"### Executive Summary\n\n{long_summary}\n\n### Next"
        summary = reviewer._extract_executive_summary(review_text)
        assert len(summary) <= 500


# ---- Full Review Flow (Mocked) ----

class TestFullReviewFlow:
    """Test the full review_implementation flow with mocks."""

    @pytest.mark.asyncio
    async def test_full_review_returns_expected_shape(self, reviewer):
        """Test that review_implementation returns correct dict shape."""
        project_id = uuid4()
        mock_db = AsyncMock()

        # Mock project
        mock_db.get_project.return_value = {
            'id': str(project_id),
            'name': 'test-project',
            'local_path': '/tmp/test-project',
            'spec_file_path': '',
            'spec_content': '# Test Spec\n\n## Features\n- User login\n- Dashboard\n',
        }

        # Mock the spec parser
        mock_spec = ParsedSpecification(
            overview="Test spec",
            spec_hash="test123",
            requirements=[
                Requirement(id="R1", section="Features", text="User login",
                           keywords=["login", "user"], priority="high"),
            ],
        )

        # Mock code inventory
        mock_inventory = CodeInventory(
            project_path="/tmp/test-project",
            files=[{"path": "auth.py", "language": "python", "lines": 50}],
            artifacts=[
                CodeArtifact(name="login", artifact_type="function",
                            file_path="auth.py", line_number=1, language="python"),
            ],
            summary={"total_files": 1, "total_lines": 50, "languages": {"python": 1},
                     "function_count": 1, "class_count": 0, "route_count": 0,
                     "component_count": 0, "model_count": 0},
        )

        # Mock test evidence
        mock_evidence = TestEvidence(
            total_tests=2, passed=2, failed=0, pending=0, pass_rate=1.0,
            by_task=[], by_epic={},
        )

        with patch.object(reviewer.parser, 'parse_spec', return_value=mock_spec), \
             patch.object(reviewer, '_parse_spec_from_content', return_value=mock_spec), \
             patch.object(reviewer.code_analyzer, 'analyze', return_value=mock_inventory), \
             patch.object(reviewer.test_collector, 'collect', return_value=mock_evidence), \
             patch.object(reviewer, '_generate_claude_review',
                         return_value=("Review text here", "Executive summary")), \
             patch('pathlib.Path.is_dir', return_value=True):

            result = await reviewer.review_implementation(project_id, mock_db)

        # Verify shape matches store_completion_review() expectations
        assert 'project_id' in result
        assert 'spec_hash' in result
        assert 'spec_parsed_at' in result
        assert 'requirements_total' in result
        assert 'requirements_met' in result
        assert 'requirements_missing' in result
        assert 'requirements_extra' in result
        assert 'coverage_percentage' in result
        assert 'overall_score' in result
        assert 'recommendation' in result
        assert 'executive_summary' in result
        assert 'review_text' in result
        assert 'review_model' in result
        assert 'matches' in result

        # Verify types
        assert isinstance(result['overall_score'], int)
        assert 1 <= result['overall_score'] <= 100
        assert result['recommendation'] in ('complete', 'needs_work', 'failed')
        assert isinstance(result['matches'], list)

    @pytest.mark.asyncio
    async def test_review_raises_for_missing_project(self, reviewer):
        project_id = uuid4()
        mock_db = AsyncMock()
        mock_db.get_project.return_value = None

        with pytest.raises(ValueError, match="Project not found"):
            await reviewer.review_implementation(project_id, mock_db)

    @pytest.mark.asyncio
    async def test_review_raises_for_missing_spec(self, reviewer):
        project_id = uuid4()
        mock_db = AsyncMock()
        mock_db.get_project.return_value = {
            'local_path': '/tmp/test',
            'spec_file_path': '',
            'spec_content': '',
        }

        with patch('pathlib.Path.is_dir', return_value=True):
            with pytest.raises(ValueError, match="No spec"):
                await reviewer.review_implementation(project_id, mock_db)
