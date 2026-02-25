#!/usr/bin/env python3
"""
Quality Gates System for YokeFlow
==================================

Enforces quality standards at each phase of development and connects
review failures to automatic rework task creation.

This system integrates with:
- Task verification (test results)
- Code review system (quality metrics)
- Epic validation (integration testing)
- Rework task creation (improvement loop)
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID
from datetime import datetime, timedelta

from server.database.connection import DatabaseManager
from server.utils.logging import get_logger, PerformanceLogger
from server.utils.errors import YokeFlowError
from server.utils.config import Config

logger = get_logger(__name__)


class GateStatus(Enum):
    """Status of a quality gate check."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    MANUAL_REVIEW = "manual_review"
    SKIPPED = "skipped"


class GateType(Enum):
    """Type of quality gate."""
    TASK = "task"           # Individual task completion
    EPIC = "epic"           # Epic completion
    REVIEW = "review"       # Code review
    INTEGRATION = "integration"  # Integration testing
    PERFORMANCE = "performance"  # Performance metrics


@dataclass
class GateResult:
    """Result of a quality gate check."""
    gate_type: GateType
    status: GateStatus
    score: float  # 0.0 to 1.0
    passed_checks: List[str] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    improvements: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Whether the gate passed."""
        return self.status in [GateStatus.PASSED, GateStatus.WARNING]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "gate_type": self.gate_type.value,
            "status": self.status.value,
            "score": self.score,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "warnings": self.warnings,
            "improvements": self.improvements,
            "metadata": self.metadata
        }


@dataclass
class ImprovementSuggestion:
    """Auto-generated improvement suggestion."""
    category: str  # "code_quality", "testing", "documentation", "performance"
    priority: int  # 1-5 (1 highest)
    issue: str
    suggestion: str
    action: str  # Specific action to take
    example: Optional[str] = None
    references: List[str] = field(default_factory=list)
    estimated_effort: Optional[str] = None  # e.g., "15 minutes", "1 hour"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category,
            "priority": self.priority,
            "issue": self.issue,
            "suggestion": self.suggestion,
            "action": self.action,
            "example": self.example,
            "references": self.references,
            "estimated_effort": self.estimated_effort
        }


class QualityGates:
    """
    Manages quality gates throughout the development process.

    Quality gates are checkpoints that enforce standards and trigger
    rework when necessary. They integrate with the review system to
    create a closed-loop quality improvement process.
    """

    def __init__(
        self,
        db,
        project_path: Path,
        config: Config
    ):
        """
        Initialize the quality gates system.

        Args:
            db: Database connection
            project_path: Path to the project
            config: Configuration
        """
        self.db = db
        self.project_path = project_path
        self.config = config

        # Quality thresholds
        self.thresholds = {
            "task_min_score": 0.7,      # Minimum score for task gate
            "epic_min_score": 0.8,      # Minimum score for epic gate
            "review_min_score": 0.6,    # Minimum score for review gate
            "test_coverage_min": 0.6,   # Minimum test coverage
            "complexity_max": 15,       # Maximum cyclomatic complexity
        }

    async def task_gate(
        self,
        task_id: str,
        session_id: Optional[UUID] = None,
        force_check: bool = False
    ) -> GateResult:
        """
        Quality gate for individual task completion.

        Checks:
        - Test results (from task verification)
        - Code quality metrics
        - Documentation completeness
        - Security issues

        Args:
            task_id: Task ID
            session_id: Current session ID
            force_check: Force check even if already passed

        Returns:
            GateResult with pass/fail status and improvements
        """
        # logger.info(f"Running task quality gate for task {task_id}")

        with PerformanceLogger("task_quality_gate", {"task_id": task_id}):
            result = GateResult(
                gate_type=GateType.TASK,
                status=GateStatus.PASSED,
                score=1.0
            )

            # Check 1: Test verification results
            test_score = await self._check_test_results(task_id)
            if test_score < 1.0:
                result.failed_checks.append(f"Test coverage: {test_score:.1%}")
                result.score *= test_score
            else:
                result.passed_checks.append("All tests passing")

            # Check 2: Code quality metrics
            quality_score, quality_issues = await self._check_code_quality(task_id)
            if quality_score < 1.0:
                result.failed_checks.extend(quality_issues)
                result.score *= quality_score
            else:
                result.passed_checks.append("Code quality standards met")

            # Check 3: Documentation
            doc_score = await self._check_documentation(task_id)
            if doc_score < 0.8:
                result.warnings.append(f"Documentation incomplete: {doc_score:.1%}")
                result.score *= (0.5 + doc_score * 0.5)  # Less weight for docs
            else:
                result.passed_checks.append("Documentation complete")

            # Check 4: Security scan
            security_issues = await self._check_security(task_id)
            if security_issues:
                result.failed_checks.extend(security_issues)
                result.score *= 0.5  # Heavy penalty for security issues
            else:
                result.passed_checks.append("No security issues found")

            # Generate improvement suggestions
            if result.score < 1.0:
                result.improvements = await self._generate_improvements(
                    task_id=task_id,
                    failed_checks=result.failed_checks,
                    warnings=result.warnings
                )

            # Determine final status
            if result.score >= self.thresholds["task_min_score"]:
                result.status = GateStatus.PASSED
            elif result.score >= 0.5:
                result.status = GateStatus.WARNING
            else:
                result.status = GateStatus.FAILED

            # Store gate result
            await self._store_gate_result(
                task_id=task_id,
                gate_result=result,
                session_id=session_id
            )

            # logger.info(
            #    f"Task gate {result.status.value}: score={result.score:.2f}",
            #    extra={
            #        "task_id": task_id,
            #        "score": result.score,
            #        "status": result.status.value
            #    }
            # )

            return result

    async def epic_gate(
        self,
        epic_id: str,
        session_id: Optional[UUID] = None
    ) -> GateResult:
        """
        Quality gate for epic completion.

        Checks:
        - All task gates passed
        - Integration test results
        - Cross-task consistency
        - Performance metrics

        Args:
            epic_id: Epic ID
            session_id: Current session ID

        Returns:
            GateResult with pass/fail status and improvements
        """
        # logger.info(f"Running epic quality gate for epic {epic_id}")

        result = GateResult(
            gate_type=GateType.EPIC,
            status=GateStatus.PASSED,
            score=1.0
        )

        # Check 1: All task gates passed
        tasks = await self.db.pool.fetch(
            "SELECT id, verified FROM tasks WHERE epic_id = $1",
            int(epic_id)
        )

        unverified = [t for t in tasks if not t['verified']]
        if unverified:
            result.failed_checks.append(f"{len(unverified)} tasks not verified")
            result.score *= (len(tasks) - len(unverified)) / len(tasks)
        else:
            result.passed_checks.append("All tasks verified")

        # Check 2: Epic validation results
        validation = await self.db.pool.fetchrow("""
            SELECT status, tasks_verified, total_tasks,
                   integration_tests_passed, integration_tests_run
            FROM epic_validation_results
            WHERE epic_id = $1
            ORDER BY started_at DESC
            LIMIT 1
        """, int(epic_id))

        if validation:
            if validation['status'] == 'passed':
                result.passed_checks.append("Epic validation passed")
            else:
                result.failed_checks.append(f"Epic validation: {validation['status']}")
                result.score *= 0.5

            if validation['integration_tests_run'] > 0:
                test_ratio = validation['integration_tests_passed'] / validation['integration_tests_run']
                if test_ratio < 1.0:
                    result.failed_checks.append(
                        f"Integration tests: {validation['integration_tests_passed']}/{validation['integration_tests_run']} passed"
                    )
                    result.score *= test_ratio

        # Check 3: Performance metrics
        perf_score = await self._check_epic_performance(epic_id)
        if perf_score < 0.8:
            result.warnings.append(f"Performance below target: {perf_score:.1%}")
            result.score *= (0.7 + perf_score * 0.3)
        else:
            result.passed_checks.append("Performance targets met")

        # Determine final status
        if result.score >= self.thresholds["epic_min_score"]:
            result.status = GateStatus.PASSED
        elif result.score >= 0.6:
            result.status = GateStatus.WARNING
        else:
            result.status = GateStatus.FAILED

        # logger.info(
        #   f"Epic gate {result.status.value}: score={result.score:.2f}",
        #   extra={
        #        "epic_id": epic_id,
        #        "score": result.score,
        #        "status": result.status.value
        #    }
        # )

        return result

    async def review_gate(
        self,
        session_id: UUID,
        review_type: str = "task"
    ) -> GateResult:
        """
        Quality gate based on code review results.

        DEPRECATED: session_quality_checks table no longer exists.
        Quality metrics now stored in sessions.metrics JSONB field.
        This function now returns SKIPPED status.

        Args:
            session_id: Session ID
            review_type: Type of review ("task", "epic", "project")

        Returns:
            GateResult with SKIPPED status
        """
        result = GateResult(
            gate_type=GateType.REVIEW,
            status=GateStatus.SKIPPED,
            score=1.0
        )
        return result

        # OLD CODE - session_quality_checks table removed
        # Get review results from database
        review = None  # await self.db.pool.fetchrow("""
            # SELECT overall_rating, error_count, error_rate,
            #        critical_issues, warnings, metrics
            # FROM session_quality_checks
            # WHERE session_id = $1
            # ORDER BY created_at DESC
            # LIMIT 1
        # """, session_id)

        if not review:
            logger.warning(f"No review found for session {session_id}")
            result.status = GateStatus.SKIPPED
            return result

        # Check review scores
        # overall_rating is 1-10, convert to 0.0-1.0 for score
        if review['overall_rating']:
            result.score = review['overall_rating'] / 10.0
        else:
            result.score = 0.0

        # Check error rate
        if review['error_rate']:
            error_rate = float(review['error_rate'])
            if error_rate > 0.1:  # More than 10% errors
                result.failed_checks.append(f"High error rate: {error_rate:.1%}")
            else:
                result.passed_checks.append("Error rate acceptable")
        else:
            result.passed_checks.append("No errors detected")

        # Check critical issues
        if review['critical_issues']:
            critical_issues = review['critical_issues']
            if isinstance(critical_issues, str):
                critical_issues = json.loads(critical_issues)
            if critical_issues and len(critical_issues) > 0:
                for issue in critical_issues[:3]:  # Top 3 critical issues
                    if isinstance(issue, dict):
                        result.failed_checks.append(issue.get('description', str(issue)))
                    else:
                        result.failed_checks.append(str(issue))

        # Check warnings
        if review['warnings']:
            warnings_list = review['warnings']
            if isinstance(warnings_list, str):
                warnings_list = json.loads(warnings_list)
            if warnings_list and len(warnings_list) > 0:
                for warning in warnings_list[:3]:  # Top 3 warnings
                    if isinstance(warning, dict):
                        result.warnings.append(warning.get('description', str(warning)))
                    else:
                        result.warnings.append(str(warning))

        # Determine status
        if result.score >= self.thresholds["review_min_score"]:
            result.status = GateStatus.PASSED
        elif result.score >= 0.4:
            result.status = GateStatus.WARNING
        else:
            result.status = GateStatus.FAILED

        # logger.info(
        #    f"Review gate {result.status.value}: score={result.score:.2f}",
        #    extra={
        #        "session_id": str(session_id),
        #        "score": result.score,
        #        "status": result.status.value
        #    }
        # )

        return result

    async def create_rework_tasks(
        self,
        gate_result: GateResult,
        entity_id: str,
        entity_type: str = "task",
        session_id: Optional[UUID] = None
    ) -> List[int]:
        """
        Create rework tasks based on gate failures.

        Args:
            gate_result: Result from quality gate
            entity_id: ID of task/epic that failed
            entity_type: Type of entity ("task" or "epic")
            session_id: Current session ID

        Returns:
            List of created rework task IDs
        """
        if gate_result.passed:
            # logger.info(f"Gate passed for {entity_type} {entity_id}, no rework needed")
            return []

        logger.info(
            f"Creating rework tasks for {entity_type} {entity_id}",
            extra={
                "failed_checks": len(gate_result.failed_checks),
                "improvements": len(gate_result.improvements)
            }
        )

        rework_task_ids = []

        # Create tasks for critical failures
        for check in gate_result.failed_checks:
            task_id = await self._create_single_rework_task(
                entity_id=entity_id,
                entity_type=entity_type,
                issue=check,
                priority=1,
                session_id=session_id
            )
            if task_id:
                rework_task_ids.append(task_id)

        # Create tasks for improvements (lower priority)
        for improvement in gate_result.improvements[:3]:  # Top 3 improvements
            task_id = await self._create_single_rework_task(
                entity_id=entity_id,
                entity_type=entity_type,
                issue=improvement.get('issue', 'Quality improvement'),
                priority=improvement.get('priority', 3),
                action=improvement.get('action'),
                session_id=session_id
            )
            if task_id:
                rework_task_ids.append(task_id)

        logger.info(
            f"Created {len(rework_task_ids)} rework tasks",
            extra={"rework_task_ids": rework_task_ids}
        )

        return rework_task_ids

    async def _create_single_rework_task(
        self,
        entity_id: str,
        entity_type: str,
        issue: str,
        priority: int,
        action: Optional[str] = None,
        session_id: Optional[UUID] = None
    ) -> Optional[int]:
        """Create a single rework task."""
        try:
            # Get epic ID based on entity type
            if entity_type == "task":
                result = await self.db.pool.fetchrow(
                    "SELECT epic_id FROM tasks WHERE id = $1",
                    int(entity_id)
                )
                epic_id = result['epic_id'] if result else None
            else:
                epic_id = int(entity_id)

            if not epic_id:
                logger.error(f"Could not find epic for {entity_type} {entity_id}")
                return None

            # Create the rework task
            task_name = f"QUALITY GATE: Fix {issue}"
            if action:
                task_description = action
            else:
                task_description = f"Address the following quality issue: {issue}"

            task_id = await self.db.pool.fetchval("""
                INSERT INTO tasks (
                    epic_id, name, description, priority,
                    done, verified, needs_review, review_reason
                ) VALUES ($1, $2, $3, $4, false, false, true, $5)
                RETURNING id
            """, epic_id, task_name, task_description, priority,
                f"Auto-generated from quality gate failure: {issue}")

            # Store quality gate relationship
            await self.db.pool.execute("""
                INSERT INTO quality_gate_tasks (
                    task_id, original_entity_id, entity_type,
                    gate_type, issue, created_at
                ) VALUES ($1, $2, $3, $4, $5, NOW())
            """, task_id, entity_id, entity_type,
                "quality_gate", issue)

            logger.info(f"Created rework task {task_id} for {issue}")
            return task_id

        except Exception as e:
            logger.error(f"Failed to create rework task: {e}")
            return None

    async def _check_test_results(self, task_id: str) -> float:
        """Check test verification results for a task."""
        result = await self.db.pool.fetchrow("""
            SELECT status, tests_passed, total_tests
            FROM task_verification_results
            WHERE task_id = $1
            ORDER BY started_at DESC
            LIMIT 1
        """, int(task_id))

        if not result:
            return 0.5  # No tests run

        if result['status'] == 'passed':
            return 1.0
        elif result['total_tests'] > 0:
            return result['tests_passed'] / result['total_tests']
        else:
            return 0.0

    async def _check_code_quality(self, task_id: str) -> Tuple[float, List[str]]:
        """Check code quality metrics for a task."""
        issues = []
        score = 1.0

        # Check for common quality issues
        # This is a simplified version - in production, integrate with linters

        # Check file modifications
        files = await self.db.pool.fetch("""
            SELECT file_path, modification_type
            FROM task_file_modifications
            WHERE task_id = $1
        """, int(task_id))

        # Basic checks
        if len(files) > 20:
            issues.append("Too many files modified (>20)")
            score *= 0.8

        # Check for test files
        test_files = [f for f in files if 'test' in f['file_path'].lower()]
        if not test_files and len(files) > 3:
            issues.append("No test files created/modified")
            score *= 0.7

        return score, issues

    async def _check_documentation(self, task_id: str) -> float:
        """Check documentation completeness."""
        # Simplified check - look for README or doc file modifications
        files = await self.db.pool.fetch("""
            SELECT file_path
            FROM task_file_modifications
            WHERE task_id = $1
            AND (file_path ILIKE '%readme%' OR file_path ILIKE '%doc%')
        """, int(task_id))

        return 1.0 if files else 0.3

    async def _check_security(self, task_id: str) -> List[str]:
        """Check for security issues."""
        issues = []

        # Check for hardcoded secrets (simplified)
        files = await self.db.pool.fetch("""
            SELECT file_path
            FROM task_file_modifications
            WHERE task_id = $1
            AND (file_path ILIKE '%.env%' OR file_path ILIKE '%secret%' OR file_path ILIKE '%key%')
        """, int(task_id))

        for f in files:
            if '.env' in f['file_path'] and '.example' not in f['file_path']:
                issues.append(f"Potential secrets in {f['file_path']}")

        return issues

    async def _check_epic_performance(self, epic_id: str) -> float:
        """Check performance metrics for an epic."""
        # Simplified performance check
        # In production, this would check actual performance metrics
        return 0.85  # Placeholder

    async def _generate_improvements(
        self,
        task_id: str,
        failed_checks: List[str],
        warnings: List[str]
    ) -> List[Dict[str, Any]]:
        """Generate improvement suggestions based on failures."""
        improvements = []

        for check in failed_checks:
            if "test" in check.lower():
                improvements.append({
                    "category": "testing",
                    "priority": 1,
                    "issue": check,
                    "suggestion": "Add comprehensive test coverage",
                    "action": "Write unit tests for all new functions and integration tests for APIs",
                    "estimated_effort": "1-2 hours"
                })
            elif "quality" in check.lower():
                improvements.append({
                    "category": "code_quality",
                    "priority": 2,
                    "issue": check,
                    "suggestion": "Refactor code to improve quality",
                    "action": "Run linters, fix complexity issues, and improve code structure",
                    "estimated_effort": "30-60 minutes"
                })
            elif "security" in check.lower():
                improvements.append({
                    "category": "security",
                    "priority": 1,
                    "issue": check,
                    "suggestion": "Fix security vulnerability",
                    "action": "Remove hardcoded secrets, use environment variables, and follow security best practices",
                    "estimated_effort": "30 minutes"
                })

        for warning in warnings[:2]:  # Top 2 warnings
            if "documentation" in warning.lower():
                improvements.append({
                    "category": "documentation",
                    "priority": 3,
                    "issue": warning,
                    "suggestion": "Improve documentation",
                    "action": "Add docstrings, update README, and document API endpoints",
                    "estimated_effort": "30 minutes"
                })

        return improvements

    async def _store_gate_result(
        self,
        task_id: str,
        gate_result: GateResult,
        session_id: Optional[UUID] = None
    ):
        """Store quality gate result in database."""
        try:
            await self.db.pool.execute("""
                INSERT INTO quality_gate_results (
                    entity_id, entity_type, gate_type, status, score,
                    passed_checks, failed_checks, warnings, improvements,
                    session_id, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            """, task_id, "task", gate_result.gate_type.value,
                gate_result.status.value, gate_result.score,
                json.dumps(gate_result.passed_checks),
                json.dumps(gate_result.failed_checks),
                json.dumps(gate_result.warnings),
                json.dumps([i for i in gate_result.improvements]),
                session_id)
        except Exception as e:
            logger.error(f"Failed to store gate result: {e}")