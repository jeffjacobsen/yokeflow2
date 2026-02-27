# Intervention System

*Status: Backend fully implemented, UI dashboard commented out (available for future use)*

## Overview

The intervention system detects when autonomous coding sessions encounter blockers and pauses them for human review. It covers three failure modes:

1. **Retry loops** — Agent repeats the same command or encounters the same error 3+ times
2. **Critical infrastructure errors** — Pattern-matched errors like database failures, port conflicts, missing modules
3. **Degenerate sessions** — 3 consecutive sessions complete with zero tool calls (rate limits, auth failures)

When triggered, the system pauses the session, persists state to PostgreSQL, optionally sends webhook/email/SMS notifications, and waits for human resolution before resuming.

## Architecture

```
Agent Loop (agent.py)
  │
  ├── check_tool_use() ──→ RetryTracker (command repetition)
  │                    ──→ QualityPatternDetector (optional)
  │
  ├── check_tool_error() ──→ RetryTracker (error repetition)
  │                      ──→ BlockerDetector (17 critical patterns)
  │
  └── If blocked ──→ PausedSessionManager.pause_session()
                       ├── Write to paused_sessions table
                       ├── Log to intervention_actions table
                       ├── Send notification (if configured)
                       └── Document in agent-progress.md

Orchestrator (orchestrator.py)
  │
  └── Degenerate loop detection (3 consecutive zero-tool sessions)
       └── PausedSessionManager.pause_session(pause_type="degenerate_loop")

API Endpoints (app.py)
  │
  ├── GET  /api/interventions/active
  ├── POST /api/interventions/{id}/resume
  ├── GET  /api/interventions/history
  ├── POST /api/sessions/{id}/pause
  ├── POST /api/sessions/{id}/resume
  ├── GET  /api/projects/{id}/notifications/preferences
  └── POST /api/projects/{id}/notifications/preferences

Web UI (InterventionDashboard.tsx)
  └── Currently commented out in page.tsx — see "Re-enabling the UI" below
```

## Detection Layer

### RetryTracker (`server/agent/intervention.py`)

Tracks command signatures (MD5 hash of tool_name + normalized parameters) and error messages. Triggers a block when:
- Same command executed more than `max_retries` times (default: 3)
- Same error message encountered more than `max_retries` times

### BlockerDetector (`server/agent/intervention.py`)

Pattern-matches error messages against 17 critical infrastructure patterns:

| Category | Patterns |
|----------|----------|
| Prisma | Schema validation, not found, exec fail |
| Redis | Not running, connection failed/refused |
| Database | Connection failed, auth failed, PostgreSQL refused |
| Port conflicts | Port in use, EADDRINUSE |
| Dependencies | Cannot find module, command not found |
| Build | TypeScript error, SyntaxError, compilation failed |

### InterventionManager (`server/agent/intervention.py`)

Orchestrates RetryTracker, BlockerDetector, and NotificationService. Integrated into the agent loop via two hooks:
- `check_tool_use(tool_name, tool_input)` — called after each tool execution
- `check_tool_error(error_message)` — called on tool failures

Both return `(is_blocked: bool, reason: str)`.

### Degenerate Loop Detection (`server/agent/orchestrator.py`)

The orchestrator's auto-continue loop tracks consecutive sessions that complete with zero tool calls. After 3 consecutive degenerate sessions, it pauses with `pause_type="degenerate_loop"` and sends a WebSocket event to the UI.

## Management Layer

### PausedSessionManager (`server/agent/session_manager.py`)

Handles pause/resume lifecycle with PostgreSQL persistence:

- **`pause_session()`** — Gathers blocker info and retry stats, inserts into `paused_sessions`, updates session status to `'paused'`, logs action to `intervention_actions`
- **`resume_session()`** — Generates a resume prompt with context about the pause/fix, marks as resolved, returns resume context for the next session
- **`get_active_pauses()`** — Queries `v_active_interventions` view
- **`get_intervention_history()`** — Queries `v_intervention_history` view

### AutoRecoveryManager (`server/agent/session_manager.py`)

Implements automatic recovery for common issues (port conflicts, Redis, database, missing modules). Built but not yet integrated into the pause flow — available for future enhancement.

## Database Tables

### `paused_sessions`
Stores the full state of a paused session:
- Session/project references, pause reason and type
- Current task context (ID, description, message count)
- Blocker details (JSONB), retry statistics (JSONB), error messages (TEXT[])
- Resolution tracking (resolved, resolved_at, resolved_by, resolution_notes)
- Auto-resume flag and resume prompt/context

### `intervention_actions`
Audit trail for actions taken during an intervention:
- Linked to `paused_sessions` via foreign key
- Action type: `notification_sent`, `auto_recovery`, `manual_fix`, `resumed`
- Status, details (JSONB), result/error messages

### `notification_preferences`
Per-project notification configuration:
- Webhook (URL, enabled flag)
- Email (addresses, enabled flag)
- SMS (phone numbers, enabled flag)
- Trigger conditions: retry_limit, critical_error, timeout, manual_pause
- Minimum notification interval (rate limiting)

### Views
- `v_active_interventions` — Unresolved pauses with project info and notification count
- `v_intervention_history` — Resolved pauses with resolution time and actions taken

## Configuration

The intervention system is configured via `InterventionConfig` in `server/utils/config.py`:

```python
@dataclass
class InterventionConfig:
    enabled: bool = False        # Must be explicitly enabled
    max_retries: int = 3         # Retries before blocking
```

Additional configuration is passed through the orchestrator's `intervention_config` dict, which can include:
- `notifications.webhook_url` — Slack/Discord/generic webhook
- `notifications.enabled` — Enable/disable notifications
- `detect_quality_issues` — Enable quality pattern detection
- `environment` — `"local"` or `"docker"`

To enable intervention in `.yokeflow.yaml`:
```yaml
intervention:
  enabled: true
  max_retries: 3
  notifications:
    enabled: true
    webhook_url: "https://hooks.slack.com/services/..."
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sessions/{id}/pause` | POST | Pause an active session |
| `/api/sessions/{id}/resume` | POST | Resume a paused session |
| `/api/interventions/active` | GET | List unresolved interventions |
| `/api/interventions/{id}/resume` | POST | Resume with resolution notes |
| `/api/interventions/history` | GET | List resolved interventions |
| `/api/projects/{id}/notifications/preferences` | GET | Get notification settings |
| `/api/projects/{id}/notifications/preferences` | POST | Update notification settings |

## Re-enabling the UI

The `InterventionDashboard.tsx` component (442 lines) is fully implemented with:
- Active interventions list with blocker details and retry stats
- Resume dialog with resolution notes
- Intervention history table
- 30-second auto-refresh

To re-enable it, uncomment the Interventions tab in `web-ui/src/app/projects/[id]/page.tsx`:

1. Uncomment the tab button (search for `{/* Interventions tab commented out`)
2. Uncomment the tab content rendering
3. Add `'interventions'` back to the tab type union

## Tests

- `tests/test_intervention_system.py` — RetryTracker, BlockerDetector, InterventionManager, PausedSessionManager, AutoRecoveryManager, NotificationService
- `tests/test_intervention.py` — Basic retry tracking, blocker detection, notification service

## Key Files

| File | Purpose |
|------|---------|
| `server/agent/intervention.py` | Detection: RetryTracker, BlockerDetector, InterventionManager |
| `server/agent/session_manager.py` | Management: PausedSessionManager, AutoRecoveryManager |
| `server/utils/notifications.py` | Multi-channel notifications (webhook, email, SMS) |
| `server/agent/agent.py` | Agent loop integration (lines 142-330) |
| `server/agent/orchestrator.py` | Degenerate loop detection (lines 750-790) |
| `server/api/app.py` | REST API endpoints |
| `server/database/operations.py` | Database operations for pause/resume |
| `server/utils/config.py` | InterventionConfig dataclass |
| `schema/postgresql/schema.sql` | Table/view/function definitions |
| `web-ui/src/components/InterventionDashboard.tsx` | UI dashboard (commented out) |
