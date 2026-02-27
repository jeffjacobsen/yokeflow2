"""
Quality Pattern Detection for YokeFlow Intervention System
===========================================================

Detects quality degradation patterns during sessions that don't manifest
as technical blockers but indicate poor quality practices.

This module implements the Quality Improvement Plan.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Set, Any
from collections import defaultdict
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Task types that require different verification approaches."""
    UI = "ui"
    API = "api"
    DATABASE = "database"
    CONFIG = "config"
    INTEGRATION = "integration"
    UNKNOWN = "unknown"


@dataclass
class TaskVerificationTracking:
    """Track verification attempts for a task."""
    task_id: str
    task_type: TaskType = TaskType.UNKNOWN
    task_name: str = ""
    verification_attempts: List[Dict] = field(default_factory=list)
    verification_methods_used: Set[str] = field(default_factory=set)
    marked_complete: bool = False
    completion_time: Optional[datetime] = None
    required_verification: Optional[str] = None
    actual_verification: Optional[str] = None
    verification_mismatch: bool = False


@dataclass
class ToolUsageTracking:
    """Track tool usage patterns."""
    correct_tool_count: int = 0
    incorrect_tool_count: int = 0
    tool_errors: List[Dict] = field(default_factory=list)
    last_incorrect_use: Optional[datetime] = None
    consecutive_incorrect_uses: int = 0
    tool_misuse_patterns: Dict[str, int] = field(default_factory=dict)


@dataclass
class QualityIssue:
    """Represents a detected quality issue."""
    issue_type: str
    severity: str  # HIGH, MEDIUM, LOW
    description: str
    evidence: Dict[str, Any]
    detected_at: datetime = field(default_factory=datetime.now)
    requires_intervention: bool = False


class QualityPatternDetector:
    """
    Detects quality issues that don't manifest as technical blockers.
    Works alongside existing retry/blocker detection to catch:
    - UI tasks completed without browser verification
    - Wrong testing methods for task types
    - Systematic tool misuse
    - Poor error recovery patterns
    """

    # Task type keywords for inference
    TASK_TYPE_KEYWORDS = {
        TaskType.UI: [
            'component', 'page', 'ui', 'button', 'form', 'modal', 'navbar',
            'header', 'footer', 'layout', 'style', 'css', 'responsive',
            'user interface', 'frontend', 'react', 'vue', 'angular', 'display'
        ],
        TaskType.API: [
            'api', 'endpoint', 'route', 'rest', 'graphql', 'http',
            'request', 'response', 'controller', 'middleware', 'auth',
            'authentication', 'authorization', 'webhook', 'cors'
        ],
        TaskType.DATABASE: [
            'database', 'db', 'schema', 'migration', 'table', 'column',
            'index', 'query', 'sql', 'postgres', 'mysql', 'mongodb',
            'relation', 'foreign key', 'constraint', 'model'
        ],
        TaskType.CONFIG: [
            'config', 'configuration', 'setup', 'build', 'package',
            'dependency', 'install', 'initialize', 'environment', 'settings',
            'webpack', 'babel', 'eslint', 'prettier', 'tsconfig'
        ],
        TaskType.INTEGRATION: [
            'integration', 'e2e', 'end-to-end', 'workflow', 'flow',
            'scenario', 'user journey', 'full stack', 'system test'
        ]
    }

    # Expected verification methods by task type
    VERIFICATION_REQUIREMENTS = {
        TaskType.UI: "browser",
        TaskType.API: "api_test",
        TaskType.DATABASE: "database_test",
        TaskType.CONFIG: "build_test",
        TaskType.INTEGRATION: "e2e_test"
    }

    # Tool usage patterns that indicate problems
    TOOL_MISUSE_PATTERNS = {
        "bash_for_file_read": r"(cat|head|tail|less|more)\s+",
        "bash_for_file_write": r"(echo|printf).*>",
        "bash_for_search": r"(grep|find|rg)\s+",
        "incorrect_docker_mode": r"mcp__task-manager__bash_docker",
        "browser_for_config": r"browser_(navigate|click|snapshot).*config",
    }

    def __init__(self, environment: str = "docker", config: Optional[Dict] = None):
        """
        Initialize quality detector.

        Args:
            environment: Running environment (docker/local)
            config: Optional configuration overrides
        """
        self.environment = environment
        self.config = config or {}

        # Tracking state
        self.task_tracking: Dict[str, TaskVerificationTracking] = {}
        self.current_task: Optional[TaskVerificationTracking] = None
        self.tool_usage = ToolUsageTracking()
        self.error_recovery_tracking: Dict[str, List] = defaultdict(list)
        self.quality_issues: List[QualityIssue] = []

        # Thresholds (configurable)
        self.max_incorrect_tool_uses = self.config.get("max_incorrect_tool_uses", 10)
        self.verification_abandonment_threshold = self.config.get("verification_abandonment_threshold", 5)
        self.error_recovery_threshold = self.config.get("error_recovery_threshold", 0.3)

    def infer_task_type(self, task_name: str) -> TaskType:
        """
        Infer task type from name using keyword matching.

        Args:
            task_name: Task name text

        Returns:
            Inferred TaskType
        """
        if not task_name:
            return TaskType.UNKNOWN

        desc_lower = task_name.lower()

        # Count keyword matches for each type
        matches = {}
        for task_type, keywords in self.TASK_TYPE_KEYWORDS.items():
            match_count = sum(1 for kw in keywords if kw in desc_lower)
            if match_count > 0:
                matches[task_type] = match_count

        # Return type with most matches, or UNKNOWN if no matches
        if matches:
            return max(matches, key=matches.get)

        return TaskType.UNKNOWN

    def start_task(self, task_id: str, task_name: str):
        """
        Begin tracking a new task.

        Args:
            task_id: Task identifier
            task_name: Task name for type inference
        """
        task_type = self.infer_task_type(task_name)

        tracking = TaskVerificationTracking(
            task_id=task_id,
            task_type=task_type,
            task_name=task_name,
            required_verification=self.VERIFICATION_REQUIREMENTS.get(task_type)
        )

        self.task_tracking[task_id] = tracking
        self.current_task = tracking

        logger.info(f"Started tracking task {task_id} (type: {task_type.value})")

        # Log if this is a UI task (critical for verification)
        if task_type == TaskType.UI:
            logger.warning(f"⚠️ UI task detected - browser verification REQUIRED: {task_name[:100]}")

    def track_verification_attempt(
        self,
        task_id: str,
        verification_method: str,
        success: bool,
        error_message: Optional[str] = None
    ):
        """
        Track a verification attempt for a task.

        Args:
            task_id: Task identifier
            verification_method: Method used (browser, api_test, etc.)
            success: Whether verification succeeded
            error_message: Optional error message if failed
        """
        if task_id not in self.task_tracking:
            return

        tracking = self.task_tracking[task_id]

        attempt = {
            "method": verification_method,
            "success": success,
            "error": error_message,
            "timestamp": datetime.now().isoformat()
        }

        tracking.verification_attempts.append(attempt)
        tracking.verification_methods_used.add(verification_method)

        # Check for verification mismatch
        if tracking.required_verification and verification_method != tracking.required_verification:
            tracking.verification_mismatch = True
            self._record_quality_issue(
                issue_type="verification_mismatch",
                severity="MEDIUM" if tracking.task_type != TaskType.UI else "HIGH",
                description=f"Task type {tracking.task_type.value} requires {tracking.required_verification} but got {verification_method}",
                evidence={
                    "task_id": task_id,
                    "expected": tracking.required_verification,
                    "actual": verification_method
                }
            )

    def track_tool_use(
        self,
        tool_name: str,
        tool_input: Dict,
        environment: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Track tool usage and detect misuse patterns.

        Args:
            tool_name: Name of the tool being used
            tool_input: Tool parameters
            environment: Current environment (docker/local)

        Returns:
            Tuple of (should_block, reason)
        """
        # Check for tool misuse patterns
        is_misused = self._check_tool_misuse(tool_name, tool_input, environment or self.environment)

        if is_misused:
            self.tool_usage.incorrect_tool_count += 1
            self.tool_usage.consecutive_incorrect_uses += 1
            self.tool_usage.last_incorrect_use = datetime.now()

            # Track specific misuse pattern
            pattern_key = f"{tool_name}:{is_misused}"
            self.tool_usage.tool_misuse_patterns[pattern_key] = \
                self.tool_usage.tool_misuse_patterns.get(pattern_key, 0) + 1

            # Check if we should intervene
            if self.tool_usage.consecutive_incorrect_uses >= self.max_incorrect_tool_uses:
                self._record_quality_issue(
                    issue_type="systematic_tool_misuse",
                    severity="HIGH",
                    description=f"Systematic misuse of tools detected ({self.tool_usage.incorrect_tool_count} incorrect uses)",
                    evidence={
                        "incorrect_count": self.tool_usage.incorrect_tool_count,
                        "patterns": self.tool_usage.tool_misuse_patterns,
                        "last_misuse": self.tool_usage.last_incorrect_use.isoformat()
                    },
                    requires_intervention=True
                )
                return True, f"Systematic tool misuse: {self.tool_usage.incorrect_tool_count} incorrect uses"
        else:
            self.tool_usage.correct_tool_count += 1
            self.tool_usage.consecutive_incorrect_uses = 0

        return False, None

    def _check_tool_misuse(
        self,
        tool_name: str,
        tool_input: Dict,
        environment: str
    ) -> Optional[str]:
        """
        Check if a tool is being misused.

        Returns:
            Misuse pattern name if detected, None otherwise
        """
        # Check bash commands for file operations (should use dedicated tools)
        if tool_name in ["bash", "Bash"]:
            command = tool_input.get("command", "")

            # Check for file operations that should use dedicated tools
            if re.search(self.TOOL_MISUSE_PATTERNS["bash_for_file_read"], command):
                return "bash_for_file_read"
            if re.search(self.TOOL_MISUSE_PATTERNS["bash_for_file_write"], command):
                return "bash_for_file_write"
            if re.search(self.TOOL_MISUSE_PATTERNS["bash_for_search"], command):
                return "bash_for_search"

        # Check for using wrong bash in Docker environment
        if environment == "docker":
            if tool_name == "bash" and "bash_docker" not in tool_name:
                return "incorrect_docker_mode"

        # Check for browser testing on config tasks
        if self.current_task and self.current_task.task_type == TaskType.CONFIG:
            if "browser" in tool_name.lower() or "agent-browser" in tool_name.lower():
                return "browser_for_config"

        return None

    def check_task_completion_quality(
        self,
        task_id: str,
        marking_complete: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a task is being completed with proper quality standards.

        Args:
            task_id: Task identifier
            marking_complete: Whether task is being marked as complete

        Returns:
            Tuple of (should_block, reason)
        """
        if task_id not in self.task_tracking:
            return False, None

        tracking = self.task_tracking[task_id]

        # Check UI tasks MUST have browser verification
        if tracking.task_type == TaskType.UI and marking_complete:
            if "browser" not in tracking.verification_methods_used:
                self._record_quality_issue(
                    issue_type="ui_task_no_browser_verification",
                    severity="HIGH",
                    description=f"UI task being completed without browser verification",
                    evidence={
                        "task_id": task_id,
                        "task_name": tracking.task_name[:200],
                        "methods_used": list(tracking.verification_methods_used)
                    },
                    requires_intervention=True
                )
                return True, "UI task MUST have browser verification before completion"

        # Check for verification abandonment (many failed attempts then giving up)
        if len(tracking.verification_attempts) >= self.verification_abandonment_threshold:
            failed_attempts = sum(1 for a in tracking.verification_attempts if not a["success"])
            if failed_attempts >= self.verification_abandonment_threshold and marking_complete:
                self._record_quality_issue(
                    issue_type="verification_abandoned",
                    severity="HIGH",
                    description=f"Task being completed after {failed_attempts} failed verification attempts",
                    evidence={
                        "task_id": task_id,
                        "failed_attempts": failed_attempts,
                        "total_attempts": len(tracking.verification_attempts)
                    },
                    requires_intervention=True
                )
                return True, f"Cannot complete task after {failed_attempts} failed verifications"

        # Check for verification mismatch
        if tracking.verification_mismatch and tracking.task_type in [TaskType.UI, TaskType.API]:
            severity = "HIGH" if tracking.task_type == TaskType.UI else "MEDIUM"
            if severity == "HIGH" and marking_complete:
                return True, f"Task type mismatch: {tracking.task_type.value} requires {tracking.required_verification}"

        return False, None

    def track_error_recovery(
        self,
        error_type: str,
        recovery_successful: bool,
        recovery_method: Optional[str] = None
    ):
        """
        Track error recovery patterns.

        Args:
            error_type: Type of error encountered
            recovery_successful: Whether recovery was successful
            recovery_method: Method used for recovery
        """
        recovery = {
            "error_type": error_type,
            "successful": recovery_successful,
            "method": recovery_method,
            "timestamp": datetime.now().isoformat()
        }

        self.error_recovery_tracking[error_type].append(recovery)

        # Check recovery success rate
        recoveries = self.error_recovery_tracking[error_type]
        if len(recoveries) >= 5:  # Need enough samples
            success_rate = sum(1 for r in recoveries if r["successful"]) / len(recoveries)
            if success_rate < self.error_recovery_threshold:
                self._record_quality_issue(
                    issue_type="poor_error_recovery",
                    severity="MEDIUM",
                    description=f"Poor error recovery for {error_type} (success rate: {success_rate:.1%})",
                    evidence={
                        "error_type": error_type,
                        "success_rate": success_rate,
                        "attempts": len(recoveries)
                    }
                )

    def _record_quality_issue(
        self,
        issue_type: str,
        severity: str,
        description: str,
        evidence: Dict[str, Any],
        requires_intervention: bool = False
    ):
        """Record a quality issue."""
        issue = QualityIssue(
            issue_type=issue_type,
            severity=severity,
            description=description,
            evidence=evidence,
            requires_intervention=requires_intervention
        )

        self.quality_issues.append(issue)

        # Log based on severity
        if severity == "HIGH":
            logger.error(f"🔴 HIGH quality issue: {description}")
        elif severity == "MEDIUM":
            logger.warning(f"🟡 MEDIUM quality issue: {description}")
        else:
            logger.info(f"🟢 LOW quality issue: {description}")

    def get_quality_summary(self) -> Dict:
        """
        Get summary of detected quality issues.

        Returns:
            Dictionary with quality metrics and issues
        """
        high_issues = [i for i in self.quality_issues if i.severity == "HIGH"]
        medium_issues = [i for i in self.quality_issues if i.severity == "MEDIUM"]

        # Calculate quality score (10 = perfect, 0 = terrible)
        quality_score = 10
        quality_score -= len(high_issues) * 2  # High issues cost 2 points
        quality_score -= len(medium_issues) * 0.5  # Medium issues cost 0.5 points
        quality_score = max(0, quality_score)  # Don't go below 0

        return {
            "quality_score": quality_score,
            "total_issues": len(self.quality_issues),
            "high_severity_issues": len(high_issues),
            "medium_severity_issues": len(medium_issues),
            "requires_intervention": any(i.requires_intervention for i in self.quality_issues),
            "issues": [
                {
                    "type": i.issue_type,
                    "severity": i.severity,
                    "description": i.description,
                    "evidence": i.evidence,
                    "detected_at": i.detected_at.isoformat()
                }
                for i in self.quality_issues
            ],
            "tool_usage": {
                "correct_uses": self.tool_usage.correct_tool_count,
                "incorrect_uses": self.tool_usage.incorrect_tool_count,
                "misuse_patterns": self.tool_usage.tool_misuse_patterns
            },
            "task_verification": {
                "total_tasks": len(self.task_tracking),
                "verification_mismatches": sum(
                    1 for t in self.task_tracking.values()
                    if t.verification_mismatch
                ),
                "ui_tasks_without_browser": sum(
                    1 for t in self.task_tracking.values()
                    if t.task_type == TaskType.UI and "browser" not in t.verification_methods_used
                )
            }
        }

    def should_intervene(self) -> Tuple[bool, Optional[str]]:
        """
        Check if intervention is needed based on quality issues.

        Returns:
            Tuple of (should_intervene, reason)
        """
        # Check for any issues requiring intervention
        intervention_issues = [i for i in self.quality_issues if i.requires_intervention]

        if intervention_issues:
            # Get the most severe issue
            high_issues = [i for i in intervention_issues if i.severity == "HIGH"]
            if high_issues:
                return True, high_issues[0].description
            else:
                return True, intervention_issues[0].description

        # Check quality score
        summary = self.get_quality_summary()
        if summary["quality_score"] < 3:
            return True, f"Quality score too low: {summary['quality_score']}/10"

        return False, None