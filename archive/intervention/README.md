# Intervention System (Archived)

This directory contains the YokeFlow intervention/pause system that was implemented but never integrated into production use. It's preserved here for reference if someone wants to implement session pause/resume functionality in the future.

## What's here

- `intervention.py` - RetryTracker, BlockerDetector, NotificationService, InterventionManager
- `session_manager.py` - PausedSessionManager, AutoRecoveryManager (DB persistence)
- `quality_detector.py` - Quality pattern detection (used by intervention.py)
- `notifications.py` - Multi-channel notification service (webhook, email, SMS)
- `intervention.md` - Full documentation with architecture, API, and database schema
- `InterventionDashboard.tsx` - Web UI dashboard for viewing/resolving interventions
- `web-ui-pages/page.tsx` - Next.js page wrapper for the dashboard
- `test_intervention.py` - RetryTracker, BlockerDetector tests
- `test_intervention_system.py` - Full pause/resume flow tests
- `test_session_manager.py` - PausedSessionManager tests (17 tests)
- `test_quality_detector.py` - Quality pattern detection tests

## Database tables (removed from schema)

The following tables were also removed from `schema/postgresql/schema.sql`:
- `paused_sessions` - Session state when paused
- `intervention_actions` - Actions taken on paused sessions
- `notification_preferences` - Per-project notification settings

See `intervention.md` for the full database schema.
