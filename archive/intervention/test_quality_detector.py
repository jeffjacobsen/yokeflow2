"""
Tests for Quality Pattern Detection System
==========================================

Tests the QualityPatternDetector class that identifies quality degradation
patterns during sessions.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from server.agent.quality_detector import (
    QualityPatternDetector,
    TaskType,
    TaskVerificationTracking,
    ToolUsageTracking,
    QualityIssue
)


class TestTaskTypeInference:
    """Test task type inference from descriptions."""

    def test_infer_ui_task(self):
        """Test UI task detection."""
        detector = QualityPatternDetector()

        ui_descriptions = [
            "Create login component with form validation",
            "Update navbar styling for responsive design",
            "Add modal for user settings page",
            "Fix button alignment in header",
            "Implement React component for dashboard"
        ]

        for desc in ui_descriptions:
            assert detector.infer_task_type(desc) == TaskType.UI, f"Failed for: {desc}"

    def test_infer_api_task(self):
        """Test API task detection."""
        detector = QualityPatternDetector()

        api_descriptions = [
            "Create REST endpoint for user authentication",
            "Add GraphQL mutation for updating profile",
            "Implement webhook handler for payment events",
            "Fix CORS issue in API middleware",
            "Add rate limiting to authentication routes"
        ]

        for desc in api_descriptions:
            assert detector.infer_task_type(desc) == TaskType.API, f"Failed for: {desc}"

    def test_infer_database_task(self):
        """Test database task detection."""
        detector = QualityPatternDetector()

        db_descriptions = [
            "Create migration for users table",
            "Add foreign key constraint to orders",
            "Optimize database query for product search",
            "Update schema to add indexes",
            "Fix SQL injection vulnerability in query"
        ]

        for desc in db_descriptions:
            assert detector.infer_task_type(desc) == TaskType.DATABASE, f"Failed for: {desc}"

    def test_infer_config_task(self):
        """Test configuration task detection."""
        detector = QualityPatternDetector()

        config_descriptions = [
            "Update webpack configuration for production build",
            "Install and configure ESLint rules",
            "Setup environment variables for deployment",
            "Add prettier configuration file",
            "Update package dependencies"
        ]

        for desc in config_descriptions:
            assert detector.infer_task_type(desc) == TaskType.CONFIG, f"Failed for: {desc}"

    def test_infer_integration_task(self):
        """Test integration task detection."""
        detector = QualityPatternDetector()

        integration_descriptions = [
            "Create end-to-end test for checkout workflow",
            "Test full user journey from signup to purchase",
            "Implement integration test for payment flow",
            "Add system test for email notifications",
            "Test complete user registration scenario"
        ]

        for desc in integration_descriptions:
            assert detector.infer_task_type(desc) == TaskType.INTEGRATION, f"Failed for: {desc}"

    def test_infer_unknown_task(self):
        """Test unknown task type for ambiguous descriptions."""
        detector = QualityPatternDetector()

        unknown_descriptions = [
            "Fix the bug",
            "Update documentation",
            "Refactor code",
            ""
        ]

        for desc in unknown_descriptions:
            assert detector.infer_task_type(desc) == TaskType.UNKNOWN, f"Failed for: {desc}"


class TestToolMisuseDetection:
    """Test detection of tool misuse patterns."""

    def test_detect_bash_for_file_read(self):
        """Test detection of using bash for file operations."""
        detector = QualityPatternDetector()

        # Should detect misuse
        is_blocked, reason = detector.track_tool_use(
            "bash",
            {"command": "cat /src/app.js"},
            "local"
        )
        assert not is_blocked  # First misuse doesn't block
        assert detector.tool_usage.incorrect_tool_count == 1

        # Should not detect misuse for legitimate bash commands
        is_blocked, reason = detector.track_tool_use(
            "bash",
            {"command": "npm install"},
            "local"
        )
        assert not is_blocked
        assert detector.tool_usage.correct_tool_count == 1

    def test_detect_bash_for_file_write(self):
        """Test detection of using bash for file writing."""
        detector = QualityPatternDetector()

        is_blocked, reason = detector.track_tool_use(
            "bash",
            {"command": "echo 'test' > file.txt"},
            "local"
        )
        assert not is_blocked
        assert detector.tool_usage.incorrect_tool_count == 1

    def test_detect_incorrect_docker_mode(self):
        """Test detection of using wrong bash in Docker."""
        detector = QualityPatternDetector(environment="docker")

        # Using regular bash in Docker environment is wrong
        is_blocked, reason = detector.track_tool_use(
            "bash",
            {"command": "ls"},
            "docker"
        )
        assert not is_blocked
        assert detector.tool_usage.incorrect_tool_count == 1

        # Using Bash tool is the correct tool
        is_blocked, reason = detector.track_tool_use(
            "Bash",
            {"command": "ls"},
            "docker"
        )
        assert not is_blocked
        assert detector.tool_usage.correct_tool_count == 1

    def test_systematic_tool_misuse_triggers_intervention(self):
        """Test that systematic misuse triggers intervention."""
        detector = QualityPatternDetector(config={"max_incorrect_tool_uses": 3})

        # Repeatedly misuse tools
        for i in range(3):
            is_blocked, reason = detector.track_tool_use(
                "bash",
                {"command": f"cat file{i}.txt"},
                "local"
            )

        # Third misuse should trigger intervention
        assert is_blocked
        assert "Systematic tool misuse" in reason
        assert detector.tool_usage.incorrect_tool_count == 3


class TestVerificationTracking:
    """Test verification attempt tracking."""

    def test_track_verification_attempts(self):
        """Test tracking verification attempts for tasks."""
        detector = QualityPatternDetector()

        # Start a UI task
        detector.start_task("task-1", "Create login component")
        assert detector.current_task.task_type == TaskType.UI

        # Track verification attempts
        detector.track_verification_attempt("task-1", "browser", True)
        detector.track_verification_attempt("task-1", "browser", False, "Element not found")

        tracking = detector.task_tracking["task-1"]
        assert len(tracking.verification_attempts) == 2
        assert "browser" in tracking.verification_methods_used
        assert tracking.verification_attempts[1]["error"] == "Element not found"

    def test_detect_verification_mismatch(self):
        """Test detection of wrong verification method for task type."""
        detector = QualityPatternDetector()

        # Start a UI task
        detector.start_task("task-1", "Create user interface component")

        # Use wrong verification method (build test instead of browser)
        detector.track_verification_attempt("task-1", "build_test", True)

        tracking = detector.task_tracking["task-1"]
        assert tracking.verification_mismatch is True

        # Check quality issue was recorded
        assert len(detector.quality_issues) == 1
        issue = detector.quality_issues[0]
        assert issue.issue_type == "verification_mismatch"
        assert issue.severity == "HIGH"  # UI tasks have high severity


class TestTaskCompletionQuality:
    """Test task completion quality checks."""

    def test_block_ui_task_without_browser_verification(self):
        """Test that UI tasks without browser verification are blocked."""
        detector = QualityPatternDetector()

        # Start a UI task
        detector.start_task("task-1", "Create login form component")

        # Try to complete without browser verification
        is_blocked, reason = detector.check_task_completion_quality("task-1", marking_complete=True)

        assert is_blocked
        assert "UI task MUST have browser verification" in reason

    def test_allow_ui_task_with_browser_verification(self):
        """Test that UI tasks with browser verification are allowed."""
        detector = QualityPatternDetector()

        # Start a UI task
        detector.start_task("task-1", "Create login form component")

        # Add browser verification
        detector.track_verification_attempt("task-1", "browser", True)

        # Should be allowed to complete
        is_blocked, reason = detector.check_task_completion_quality("task-1", marking_complete=True)

        assert not is_blocked

    def test_block_task_after_verification_abandonment(self):
        """Test blocking task completion after many failed verifications."""
        detector = QualityPatternDetector(
            config={"verification_abandonment_threshold": 3}
        )

        detector.start_task("task-1", "Create API endpoint")

        # Add many failed verification attempts
        for i in range(3):
            detector.track_verification_attempt("task-1", "api_test", False, f"Error {i}")

        # Try to complete after failures
        is_blocked, reason = detector.check_task_completion_quality("task-1", marking_complete=True)

        assert is_blocked
        assert "Cannot complete task after 3 failed verifications" in reason

    def test_allow_config_task_without_browser(self):
        """Test that config tasks don't require browser verification."""
        detector = QualityPatternDetector()

        # Start a config task
        detector.start_task("task-1", "Update webpack configuration")

        # Add build verification
        detector.track_verification_attempt("task-1", "build_test", True)

        # Should be allowed without browser verification
        is_blocked, reason = detector.check_task_completion_quality("task-1", marking_complete=True)

        assert not is_blocked


class TestQualityScoring:
    """Test quality score calculation."""

    def test_perfect_quality_score(self):
        """Test perfect quality score with no issues."""
        detector = QualityPatternDetector()
        summary = detector.get_quality_summary()

        assert summary["quality_score"] == 10
        assert summary["total_issues"] == 0

    def test_quality_score_with_high_issues(self):
        """Test quality score reduction with high severity issues."""
        detector = QualityPatternDetector()

        # Record high severity issues
        detector._record_quality_issue(
            "ui_task_no_browser",
            "HIGH",
            "UI task without browser verification",
            {"task_id": "1"}
        )
        detector._record_quality_issue(
            "systematic_tool_misuse",
            "HIGH",
            "Repeated tool misuse",
            {"count": 10}
        )

        summary = detector.get_quality_summary()
        assert summary["quality_score"] == 6  # 10 - (2 * 2)
        assert summary["high_severity_issues"] == 2

    def test_quality_score_with_medium_issues(self):
        """Test quality score reduction with medium severity issues."""
        detector = QualityPatternDetector()

        # Record medium severity issues
        for i in range(4):
            detector._record_quality_issue(
                f"issue_{i}",
                "MEDIUM",
                f"Medium issue {i}",
                {}
            )

        summary = detector.get_quality_summary()
        assert summary["quality_score"] == 8  # 10 - (4 * 0.5)
        assert summary["medium_severity_issues"] == 4

    def test_quality_score_floor(self):
        """Test quality score doesn't go below 0."""
        detector = QualityPatternDetector()

        # Record many high severity issues
        for i in range(10):
            detector._record_quality_issue(
                f"issue_{i}",
                "HIGH",
                f"High issue {i}",
                {}
            )

        summary = detector.get_quality_summary()
        assert summary["quality_score"] == 0  # Floored at 0


class TestInterventionTriggers:
    """Test conditions that trigger intervention."""

    def test_intervention_on_quality_issues(self):
        """Test intervention triggers on quality issues."""
        detector = QualityPatternDetector()

        # Create issue requiring intervention
        detector._record_quality_issue(
            "ui_task_no_browser",
            "HIGH",
            "UI task without browser verification",
            {"task_id": "1"},
            requires_intervention=True
        )

        should_intervene, reason = detector.should_intervene()
        assert should_intervene
        assert "UI task without browser verification" in reason

    def test_intervention_on_low_quality_score(self):
        """Test intervention triggers on low quality score."""
        detector = QualityPatternDetector()

        # Create many issues to lower score
        for i in range(5):
            detector._record_quality_issue(
                f"issue_{i}",
                "HIGH",
                f"High severity issue {i}",
                {}
            )

        should_intervene, reason = detector.should_intervene()
        assert should_intervene
        assert "Quality score too low" in reason

    def test_no_intervention_with_good_quality(self):
        """Test no intervention with good quality."""
        detector = QualityPatternDetector()

        # Minor issues that don't require intervention
        detector._record_quality_issue(
            "minor_issue",
            "LOW",
            "Minor formatting issue",
            {}
        )

        should_intervene, reason = detector.should_intervene()
        assert not should_intervene


class TestErrorRecoveryTracking:
    """Test error recovery pattern tracking."""

    def test_track_successful_recovery(self):
        """Test tracking successful error recovery."""
        detector = QualityPatternDetector()

        # Track successful recoveries
        for i in range(5):
            detector.track_error_recovery("network_error", True, "retry")

        # Should not create quality issue
        assert len(detector.quality_issues) == 0

    def test_detect_poor_error_recovery(self):
        """Test detection of poor error recovery patterns."""
        detector = QualityPatternDetector(
            config={"error_recovery_threshold": 0.5}
        )

        # Track mostly failed recoveries
        detector.track_error_recovery("network_error", True, "retry")
        for i in range(4):
            detector.track_error_recovery("network_error", False, "retry")

        # Should detect poor recovery rate
        assert len(detector.quality_issues) == 1
        issue = detector.quality_issues[0]
        assert issue.issue_type == "poor_error_recovery"
        assert issue.severity == "MEDIUM"


class TestIntegrationWithIntervention:
    """Test integration with intervention manager."""

    @patch('server.agent.quality_detector.logger')
    def test_quality_detector_in_intervention_manager(self, mock_logger):
        """Test quality detector integration in intervention manager."""
        from server.agent.intervention import InterventionManager

        config = {
            "enabled": True,
            "detect_quality_issues": True,
            "max_retries": 3
        }

        manager = InterventionManager(config=config, environment="docker")
        assert manager.quality_detector is not None

        # Test task tracking
        manager.set_current_task("task-1", "Create UI component")
        assert manager.quality_detector.current_task is not None

    @patch('server.agent.quality_detector.logger')
    async def test_quality_blocking_in_intervention(self, mock_logger):
        """Test that quality issues can block operations."""
        from server.agent.intervention import InterventionManager

        config = {
            "enabled": True,
            "detect_quality_issues": True,
            "quality_detection": {
                "max_incorrect_tool_uses": 2
            }
        }

        manager = InterventionManager(config=config)
        manager.set_current_task("task-1", "Create login form")

        # Simulate tool misuse
        for i in range(2):
            is_blocked, reason = await manager.check_tool_use(
                "bash",
                {"command": f"cat file{i}.txt"}
            )

        # Should eventually block
        assert is_blocked
        assert "Systematic tool misuse" in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])