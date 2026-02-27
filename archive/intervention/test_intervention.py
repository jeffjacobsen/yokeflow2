#!/usr/bin/env python3
"""
Test script for the intervention system.
Tests retry tracking, blocker detection, and notifications.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from server.agent.intervention import (
    RetryTracker,
    BlockerDetector,
    NotificationService,
    InterventionManager
)


async def test_retry_tracker():
    """Test retry tracking functionality."""
    print("\n=== Testing Retry Tracker ===")

    tracker = RetryTracker(max_retries=3)

    # Test command retry detection
    commands = [
        ("Bash", {"command": "curl http://localhost:3001/health"}),
        ("Bash", {"command": "curl http://localhost:3001/health"}),
        ("Bash", {"command": "curl http://localhost:3001/health"}),
        ("Bash", {"command": "curl http://localhost:3001/health"}),  # 4th attempt should trigger
    ]

    for i, (tool, input_) in enumerate(commands, 1):
        is_blocked, reason = tracker.track_command(tool, input_)
        print(f"Attempt {i}: Blocked={is_blocked}, Reason={reason}")

        if is_blocked:
            print(f"✅ Successfully detected retry loop after {i} attempts")
            break

    # Test error tracking
    print("\n--- Testing Error Tracking ---")
    error_tracker = RetryTracker(max_retries=2)

    errors = [
        "Connection refused: localhost:3001",
        "Connection refused: localhost:3001",
        "Connection refused: localhost:3001",  # 3rd occurrence should trigger
    ]

    for i, error in enumerate(errors, 1):
        is_blocked, reason = error_tracker.track_error(error)
        print(f"Error {i}: Blocked={is_blocked}")

        if is_blocked:
            print(f"✅ Successfully detected repeated errors after {i} occurrences")
            break

    # Print stats
    print(f"\nStats: {tracker.get_stats()}")


def test_blocker_detector():
    """Test blocker detection for critical errors."""
    print("\n=== Testing Blocker Detector ===")

    detector = BlockerDetector()

    test_errors = [
        ("Prisma schema validation error", True),
        ("Command \"prisma\" not found", True),
        ("Redis not running", True),
        ("ECONNREFUSED 127.0.0.1:5432", True),
        ("Port 3001 already in use", True),
        ("Cannot find module 'express'", True),
        ("Everything is working fine", False),
    ]

    for error_msg, should_block in test_errors:
        is_blocker, info = detector.check_for_blocker(error_msg)
        status = "✅" if is_blocker == should_block else "❌"
        print(f"{status} '{error_msg[:40]}...' -> Blocker: {is_blocker}")

        if is_blocker and info:
            print(f"    Type: {info['type']}")

    print(f"\nTotal blockers detected: {len(detector.get_blockers())}")


async def test_notification_service():
    """Test notification service (requires webhook URL)."""
    print("\n=== Testing Notification Service ===")

    # Check if webhook URL is configured
    import os
    webhook_url = os.getenv("YOKEFLOW_WEBHOOK_URL")

    if not webhook_url:
        print("⚠️ No webhook URL configured. Set YOKEFLOW_WEBHOOK_URL to test notifications.")
        print("   Example: export YOKEFLOW_WEBHOOK_URL='https://hooks.slack.com/services/...'")
        return

    config = {
        "enabled": True,
        "webhook_url": webhook_url
    }

    service = NotificationService(config)

    blocker_info = {
        "type": "test_blocker",
        "message": "This is a test notification from YokeFlow intervention system",
        "timestamp": "2024-01-01T12:00:00"
    }

    retry_stats = {
        "total_retries": 10,
        "max_retries_on_single_command": 4,
        "unique_errors": 3
    }

    success = await service.send_blocker_notification(
        session_id="test-session-123",
        project_name="test-project",
        blocker_info=blocker_info,
        retry_stats=retry_stats
    )

    if success:
        print(f"✅ Notification sent successfully to webhook!")
    else:
        print(f"❌ Failed to send notification")


async def test_intervention_manager():
    """Test the complete intervention manager."""
    print("\n=== Testing Intervention Manager ===")

    config = {
        "enabled": True,
        "max_retries": 2,
        "notifications": {
            "enabled": False  # Disable for test
        }
    }

    manager = InterventionManager(config)
    manager.set_session_info("test-session", "test-project")

    # Test command tracking
    print("\n--- Testing Command Retry Detection ---")
    commands = [
        ("Bash", {"command": "npm start"}),
        ("Bash", {"command": "npm start"}),
        ("Bash", {"command": "npm start"}),  # Should trigger on 3rd attempt
    ]

    for i, (tool, input_) in enumerate(commands, 1):
        is_blocked, reason = await manager.check_tool_use(tool, input_)
        print(f"Command {i}: Blocked={is_blocked}")

        if is_blocked:
            print(f"✅ Manager blocked after {i} attempts: {reason}")
            break

    # Test error detection
    print("\n--- Testing Error Detection ---")
    errors = [
        "Everything is fine",
        "Prisma schema validation failed",  # Should trigger immediately
    ]

    for i, error in enumerate(errors, 1):
        is_blocked, reason = await manager.check_tool_error(error)
        print(f"Error {i}: Blocked={is_blocked}")

        if is_blocked:
            print(f"✅ Manager detected critical error: {reason}")
            break

    # Print summary
    summary = manager.get_summary()
    print(f"\nManager Summary:")
    print(f"  Retry Stats: {summary['retry_stats']}")
    print(f"  Blockers Found: {len(summary['blockers'])}")


async def main():
    """Run all tests."""
    print("=" * 70)
    print("YokeFlow Intervention System Test Suite")
    print("=" * 70)

    # Run tests
    await test_retry_tracker()
    test_blocker_detector()
    await test_notification_service()
    await test_intervention_manager()

    print("\n" + "=" * 70)
    print("All tests complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())