"""
Test Result Collector for Completion Review

Gathers actual test execution outcomes from the database to provide
evidence of whether tasks were successfully implemented.
"""

import logging
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from uuid import UUID

if TYPE_CHECKING:
    from server.database.operations import TaskDatabase

logger = logging.getLogger(__name__)


@dataclass
class TaskTestEvidence:
    """Test evidence for a single task."""
    task_id: int
    task_name: str
    epic_id: int
    epic_name: str
    task_status: str          # completed, in_progress, pending, etc.
    tests_passed: int = 0
    tests_failed: int = 0
    tests_pending: int = 0
    test_details: List[Dict] = field(default_factory=list)  # {name, status, error}

    @property
    def total_tests(self) -> int:
        return self.tests_passed + self.tests_failed + self.tests_pending

    @property
    def summary(self) -> str:
        """Human-readable summary like '3/3 passed' or '1/2 failed'."""
        if self.total_tests == 0:
            return "no tests"
        if self.tests_failed > 0:
            return f"{self.tests_failed}/{self.total_tests} failed"
        if self.tests_pending > 0:
            return f"{self.tests_passed}/{self.total_tests} passed ({self.tests_pending} pending)"
        return f"{self.tests_passed}/{self.total_tests} passed"


@dataclass
class TestEvidence:
    """Aggregated test evidence for an entire project."""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    pending: int = 0
    pass_rate: float = 0.0
    by_task: List[TaskTestEvidence] = field(default_factory=list)
    by_epic: Dict[int, Dict] = field(default_factory=dict)  # epic_id -> counts

    def to_summary_text(self) -> str:
        """Generate human-readable summary for Claude prompt."""
        lines = [
            f"**Total Tests**: {self.total_tests}",
            f"**Passed**: {self.passed}",
            f"**Failed**: {self.failed}",
            f"**Pending**: {self.pending}",
            f"**Pass Rate**: {self.pass_rate:.0%}",
        ]

        if self.failed > 0:
            lines.append("")
            lines.append("**Failed Tasks:**")
            for te in self.by_task:
                if te.tests_failed > 0:
                    lines.append(f"- {te.task_name}: {te.summary}")

        return '\n'.join(lines)


class TestResultCollector:
    """Collects test execution results from the database."""

    async def collect(self, project_id: UUID, db: "TaskDatabase") -> TestEvidence:
        """
        Gather all test results for a project.

        Args:
            project_id: Project UUID
            db: Database connection

        Returns:
            TestEvidence with per-task and per-epic breakdowns
        """
        evidence = TestEvidence()

        async with db.acquire() as conn:
            # Get all tasks with their tests for this project
            rows = await conn.fetch(
                """
                SELECT
                    t.id as task_id,
                    t.name as task_name,
                    t.done as task_done,
                    t.epic_id,
                    e.name as epic_name,
                    tt.id as test_id,
                    tt.description as test_name,
                    tt.passes as test_passes
                FROM tasks t
                JOIN epics e ON t.epic_id = e.id
                LEFT JOIN task_tests tt ON tt.task_id = t.id
                WHERE t.project_id = $1
                ORDER BY e.id, t.id, tt.id
                """,
                project_id
            )

        # Group by task
        task_map: Dict[int, TaskTestEvidence] = {}
        for row in rows:
            task_id = row['task_id']
            if task_id not in task_map:
                task_map[task_id] = TaskTestEvidence(
                    task_id=task_id,
                    task_name=row['task_name'],
                    epic_id=row['epic_id'],
                    epic_name=row['epic_name'],
                    task_status='completed' if row['task_done'] else 'pending',
                )

            te = task_map[task_id]

            # Skip if this task has no tests (LEFT JOIN null row)
            if row['test_id'] is None:
                continue

            # passes is boolean: True = passed, False = failed/pending
            test_passes = row['test_passes']
            if test_passes is True:
                test_status = 'passed'
            elif test_passes is False:
                test_status = 'failed'
            else:
                test_status = 'pending'

            detail = {
                'name': row['test_name'] or f"test_{row['test_id']}",
                'status': test_status,
            }

            te.test_details.append(detail)

            if test_status == 'passed':
                te.tests_passed += 1
            elif test_status == 'failed':
                te.tests_failed += 1
            else:
                te.tests_pending += 1

        # Also gather epic-level tests
        async with db.acquire() as conn:
            epic_test_rows = await conn.fetch(
                """
                SELECT
                    et.epic_id,
                    e.name as epic_name,
                    et.name as test_name,
                    et.passes
                FROM epic_tests et
                JOIN epics e ON et.epic_id = e.id
                WHERE e.project_id = $1
                ORDER BY et.epic_id
                """,
                project_id
            )

        # Count epic tests into totals
        for row in epic_test_rows:
            passes = row['passes']
            if passes is True:
                evidence.passed += 1
            elif passes is False:
                evidence.failed += 1
            else:
                evidence.pending += 1
            evidence.total_tests += 1

        # Build evidence
        evidence.by_task = list(task_map.values())

        # Aggregate task-level test counts
        for te in evidence.by_task:
            evidence.total_tests += te.total_tests
            evidence.passed += te.tests_passed
            evidence.failed += te.tests_failed
            evidence.pending += te.tests_pending

            # Aggregate by epic
            eid = te.epic_id
            if eid not in evidence.by_epic:
                evidence.by_epic[eid] = {
                    'epic_name': te.epic_name,
                    'passed': 0, 'failed': 0, 'pending': 0,
                }
            evidence.by_epic[eid]['passed'] += te.tests_passed
            evidence.by_epic[eid]['failed'] += te.tests_failed
            evidence.by_epic[eid]['pending'] += te.tests_pending

        # Calculate pass rate
        executed = evidence.passed + evidence.failed
        evidence.pass_rate = evidence.passed / executed if executed > 0 else 0.0

        logger.info(
            f"Test evidence: {evidence.total_tests} tests, "
            f"{evidence.passed} passed, {evidence.failed} failed "
            f"({evidence.pass_rate:.0%} pass rate)"
        )

        return evidence
