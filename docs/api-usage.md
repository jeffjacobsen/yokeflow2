# API Usage Guide

YokeFlow provides a RESTful API for managing projects and sessions programmatically. The Web UI uses this API, and you can use it directly for automation or integration.

**Version**: 2.1.0

---

## What's New in v2.1

YokeFlow 2.1 adds comprehensive quality system endpoints and project completion verification:

- **Project Completion Reviews** - AI-powered verification against original specs (5 endpoints)
- **Intervention Management** - Handle session blockers gracefully (5 endpoints)
- **Enhanced Quality Monitoring** - Deep reviews and statistics (4 endpoints)
- **Screenshot Access** - Visual verification artifacts (2 endpoints)
- **Administration Tools** - Cleanup and validation utilities (3 endpoints)

**Total API Growth**: 17 endpoints (v2.0) → 60+ endpoints (v2.1)

See [QUALITY_SYSTEM_SUMMARY.md](../QUALITY_SYSTEM_SUMMARY.md) for complete implementation details.

### Quick Reference: Most Used v2.1 Endpoints

| Task | Endpoint | Method |
|------|----------|--------|
| Trigger completion review | `/api/projects/{id}/completion-review` | `POST` |
| Check active interventions | `/api/interventions/active` | `GET` |
| Resume from blocker | `/api/interventions/{id}/resume` | `POST` |
| View deep reviews | `/api/projects/{id}/deep-reviews` | `GET` |
| Get review statistics | `/api/projects/{id}/review-stats` | `GET` |
| List screenshots | `/api/projects/{id}/screenshots` | `GET` |
| Clean orphaned sessions | `/api/admin/cleanup-orphaned-sessions` | `POST` |

---

## Quick Start

### Start the API Server

```bash
# Start PostgreSQL (required)
docker-compose up -d

# Start API server
uvicorn server.api.app:app --host 0.0.0.0 --port 8010 --reload
```

Server runs at: http://localhost:8010

### Interactive Documentation

- **Swagger UI**: http://localhost:8010/docs (try endpoints interactively)
- **ReDoc**: http://localhost:8010/redoc (reference documentation)
- **Health Check**: http://localhost:8010/api/health

---

## Common API Workflows

### 1. Create a New Project

```bash
curl -X POST http://localhost:8010/api/projects \
  -F "name=my-todo-app" \
  -F "spec_file=@app_spec.txt"
```

**Response:**
```json
{
  "project_id": "550e8400-...",
  "name": "my-todo-app",
  "is_initialized": false
}
```

### 2. Initialize Project (Session 0)

```bash
curl -X POST http://localhost:8010/api/projects/550e8400-.../initialize
```

**Response:**
```json
{
  "session_id": "abc123...",
  "status": "running",
  "type": "initializer"
}
```

This creates the complete roadmap (epics → tasks → tests).

### 3. Check Progress

```bash
curl http://localhost:8010/api/projects/550e8400-.../progress
```

**Response:**
```json
{
  "total_epics": 20,
  "completed_epics": 0,
  "total_tasks": 150,
  "completed_tasks": 0,
  "task_completion_pct": 0.0
}
```

### 4. Start Coding Session

```bash
curl -X POST http://localhost:8010/api/projects/550e8400-.../coding/start
```

**Response:**
```json
{
  "session_id": "def456...",
  "status": "running",
  "type": "coding"
}
```

### 5. Monitor Real-Time Progress (WebSocket)

```javascript
// JavaScript example
const ws = new WebSocket('ws://localhost:8010/api/ws/550e8400-...');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Progress:', data.progress);
  console.log('Current task:', data.current_task);
};
```

---

## API Endpoints Reference

YokeFlow provides **60+ RESTful endpoints** for complete platform control.

### Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Basic health check |
| `GET` | `/health/detailed` | Detailed component status |
| `GET` | `/api/health` | API health check |
| `GET` | `/api/info` | API version and info |

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/projects` | List all projects |
| `POST` | `/api/projects` | Create new project |
| `GET` | `/api/projects/{id}` | Get project details |
| `PATCH` | `/api/projects/{id}` | Update project (rename) |
| `DELETE` | `/api/projects/{id}` | Delete project |
| `GET` | `/api/projects/{id}/progress` | Get progress stats |
| `POST` | `/api/projects/{id}/reset` | Reset project to post-init state |
| `GET` | `/api/projects/{id}/settings` | Get project settings |
| `PUT` | `/api/projects/{id}/settings` | Update project settings |
| `GET` | `/api/projects/{id}/env` | Get environment variables |
| `POST` | `/api/projects/{id}/env` | Set environment variables |
| `GET` | `/api/projects/{id}/coverage` | Get test coverage data |
| `GET` | `/api/projects/{id}/epics` | List all epics |
| `GET` | `/api/projects/{id}/tasks` | List all tasks |
| `GET` | `/api/projects/{id}/tasks/{task_id}` | Get specific task |
| `GET` | `/api/projects/{id}/epics/{epic_id}` | Get specific epic |
| `GET` | `/api/projects/{id}/logs` | List available log files |
| `GET` | `/api/projects/{id}/logs/human/{filename}` | Get human-readable log |
| `GET` | `/api/projects/{id}/logs/events/{filename}` | Get event log (JSONL) |
| `GET` | `/api/projects/{id}/screenshots` | List screenshots ⭐ NEW v2.1 |
| `GET` | `/api/projects/{id}/screenshots/{filename}` | Get screenshot ⭐ NEW v2.1 |

### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/projects/{id}/initialize` | Start initialization (Session 0) |
| `POST` | `/api/projects/{id}/initialize/cancel` | Cancel initialization |
| `POST` | `/api/projects/{id}/coding/start` | Start coding session |
| `POST` | `/api/projects/{id}/sessions/start` | Start generic session |
| `POST` | `/api/projects/{id}/coding/stop` | Stop current session |
| `POST` | `/api/projects/{id}/stop-after-current` | Queue stop after current session |
| `DELETE` | `/api/projects/{id}/stop-after-current` | Cancel queued stop |
| `GET` | `/api/projects/{id}/sessions` | List all sessions |
| `GET` | `/api/projects/{id}/sessions/{sid}` | Get session details |
| `POST` | `/api/projects/{id}/sessions/{sid}/stop` | Stop specific session |
| `GET` | `/api/sessions/{sid}/logs` | Get session logs with pagination |
| `POST` | `/api/sessions/{sid}/pause` | Pause active session |
| `POST` | `/api/sessions/{sid}/resume` | Resume paused session |

### Tasks & Epics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/tasks/{task_id}` | Get task details |
| `PATCH` | `/api/tasks/{task_id}` | Update task status |
| `GET` | `/api/epics/{epic_id}/progress` | Get epic progress with task breakdown |

### Quality & Verification

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions/{sid}/quality-review` | Trigger quality review for session |
| `GET` | `/api/projects/{id}/quality-metrics` | Get quality metrics summary |
| `GET` | `/api/projects/{id}/deep-reviews` | List all deep reviews ⭐ NEW v2.1 |
| `GET` | `/api/projects/{id}/review-stats` | Get review statistics ⭐ NEW v2.1 |
| `POST` | `/api/projects/{id}/sessions/{sid}/review` | Trigger session review ⭐ NEW v2.1 |
| `POST` | `/api/projects/{id}/trigger-reviews` | Batch trigger reviews ⭐ NEW v2.1 |

### Project Completion Reviews ⭐ NEW v2.1

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/projects/{id}/completion-review` | Get latest completion review |
| `POST` | `/api/projects/{id}/completion-review` | Trigger completion review |
| `GET` | `/api/completion-reviews` | List all reviews (with filters) |
| `GET` | `/api/completion-reviews/{id}/requirements` | Get requirement breakdown |
| `GET` | `/api/completion-reviews/{id}/section-summary` | Get section-level summary |

### Intervention Management ⭐ NEW v2.1

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/interventions/active` | List active interventions |
| `POST` | `/api/interventions/{id}/resume` | Resume from intervention |
| `GET` | `/api/interventions/history` | View intervention history |
| `GET` | `/api/projects/{id}/notifications/preferences` | Get notification settings |
| `POST` | `/api/projects/{id}/notifications/preferences` | Update notification settings |

### Administration ⭐ NEW v2.1

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/admin/cleanup-orphaned-sessions` | Clean up orphaned sessions |
| `POST` | `/api/generate-spec` | Generate spec with AI (see [ai-spec-generation.md](ai-spec-generation.md)) |
| `POST` | `/api/validate-spec` | Validate specification file |

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/login` | Login and get JWT token |
| `GET` | `/api/auth/verify` | Verify token validity |

### Real-Time

| Method | Endpoint | Description |
|--------|----------|-------------|
| `WS` | `/api/ws/{id}` | WebSocket for live updates |

---

**Total: 60+ endpoints** | ⭐ **v2.1 additions** marked above | See detailed examples below

**Interactive Documentation**: http://localhost:8010/docs (Swagger UI with try-it-out functionality)

---

## Authentication

### Development Mode (Default)

No authentication required when `UI_PASSWORD` is not set:

```bash
# Just call the API directly
curl http://localhost:8010/api/projects
```

### Production Mode

When `UI_PASSWORD` is set, you need a JWT token:

**1. Login:**
```bash
curl -X POST http://localhost:8010/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password": "your-password"}'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**2. Use Token:**
```bash
curl http://localhost:8010/api/projects \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

**See [authentication.md](authentication.md) for details**

---

## WebSocket Events

Subscribe to project updates:

```javascript
const ws = new WebSocket('ws://localhost:8010/api/ws/PROJECT_ID');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case 'session_update':
      console.log('Session:', data.status);
      break;
    case 'progress_update':
      console.log('Progress:', data.progress.task_completion_pct + '%');
      break;
    case 'tool_use':
      console.log('Tool:', data.tool_name);
      break;
    case 'session_complete':
      console.log('Session finished:', data.session_id);
      break;
  }
};
```

**Event Types:**
- `session_update` - Session status changed
- `progress_update` - Task/test progress updated
- `tool_use` - Agent used a tool
- `tool_result` - Tool execution result
- `session_complete` - Session finished
- `error` - Error occurred

---

## Example: Automated Project Creation

```python
import requests

API_URL = "http://localhost:8010"

# 1. Create project
with open('app_spec.txt', 'rb') as f:
    response = requests.post(
        f"{API_URL}/api/projects",
        files={'spec_file': f},
        data={
            'name': 'automated-project'
        }
    )
    project = response.json()
    project_id = project['project_id']

# 2. Initialize (creates roadmap)
response = requests.post(
    f"{API_URL}/api/projects/{project_id}/initialize"
)
session = response.json()
print(f"Initialization started: {session['session_id']}")

# 3. Poll until initialization complete
import time
while True:
    response = requests.get(
        f"{API_URL}/api/projects/{project_id}/sessions/{session['session_id']}"
    )
    status = response.json()

    if status['status'] == 'completed':
        print("Initialization complete!")
        break
    elif status['status'] == 'error':
        print("Error:", status.get('error_message'))
        break

    time.sleep(5)

# 4. Start coding sessions
response = requests.post(
    f"{API_URL}/api/projects/{project_id}/coding/start"
)
print("Coding session started")
```

---

## Example: Monitor Progress

```python
import requests

API_URL = "http://localhost:8010"
PROJECT_ID = "550e8400-..."

# Get current progress
response = requests.get(f"{API_URL}/api/projects/{PROJECT_ID}/progress")
progress = response.json()

print(f"Tasks: {progress['completed_tasks']}/{progress['total_tasks']}")
print(f"Tests: {progress['passing_tests']}/{progress['total_tests']}")
print(f"Completion: {progress['task_completion_pct']:.1f}%")
```

---

## Example: WebSocket with Python

```python
import asyncio
import websockets
import json

async def monitor_project(project_id):
    uri = f"ws://localhost:8010/api/ws/{project_id}"

    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)

            if data['type'] == 'progress_update':
                progress = data['progress']
                print(f"Progress: {progress['task_completion_pct']:.1f}%")

            elif data['type'] == 'session_complete':
                print("Session finished!")
                break

# Run
asyncio.run(monitor_project("550e8400-..."))
```

---

## Example: Project Completion Review (v2.1)

```python
import requests
import time

API_URL = "http://localhost:8010"
PROJECT_ID = "550e8400-..."

# 1. Check if project is complete
response = requests.get(f"{API_URL}/api/projects/{PROJECT_ID}/progress")
progress = response.json()

if progress['task_completion_pct'] >= 100:
    print("Project complete! Triggering completion review...")

    # 2. Trigger completion review
    response = requests.post(
        f"{API_URL}/api/projects/{PROJECT_ID}/completion-review"
    )
    review = response.json()
    review_id = review['id']

    # 3. Wait for review to complete (reviews are async)
    while True:
        response = requests.get(
            f"{API_URL}/api/projects/{PROJECT_ID}/completion-review"
        )
        review = response.json()

        if review.get('status') == 'completed':
            break

        time.sleep(5)

    # 4. Display results
    print(f"\n=== Completion Review Results ===")
    print(f"Overall Score: {review['overall_score']}/100")
    print(f"Coverage: {review['coverage_percentage']:.1f}%")
    print(f"Recommendation: {review['recommendation']}")
    print(f"\nExecutive Summary:")
    print(review['executive_summary'])

    # 5. Get detailed requirement breakdown
    response = requests.get(
        f"{API_URL}/api/completion-reviews/{review_id}/requirements"
    )
    requirements = response.json()

    print(f"\n=== Requirement Breakdown ===")
    for req in requirements['requirements']:
        status_icon = "✅" if req['status'] == 'implemented' else "❌"
        print(f"{status_icon} [{req['priority']}] {req['requirement_text']}")
        print(f"   Coverage: {req['coverage_score']:.1f}%")
        print(f"   Matched: {len(req['matched_epics'])} epics, {len(req['matched_tasks'])} tasks\n")

    # 6. Get section summary
    response = requests.get(
        f"{API_URL}/api/completion-reviews/{review_id}/section-summary"
    )
    sections = response.json()

    print(f"\n=== Section Coverage ===")
    for section in sections['sections']:
        print(f"{section['section_name']}: {section['coverage_percentage']:.1f}% ({section['requirements_met']}/{section['total_requirements']})")
else:
    print(f"Project not complete yet: {progress['task_completion_pct']:.1f}%")
```

---

## CORS Configuration

The API supports CORS for web applications:

**Default allowed origins:**
- `http://localhost:3010` (Next.js dev server)
- `http://localhost:5173` (Vite dev server)

**To add custom origins:**

Set `CORS_ORIGINS` in `.env`:
```bash
CORS_ORIGINS=http://localhost:3010,https://my-domain.com
```

---

## Error Handling

**Common HTTP Status Codes:**

| Code | Meaning | Example |
|------|---------|---------|
| `200` | Success | Project retrieved |
| `201` | Created | Project created |
| `400` | Bad Request | Missing spec file |
| `401` | Unauthorized | Invalid/missing token |
| `404` | Not Found | Project doesn't exist |
| `409` | Conflict | Session already running |
| `500` | Server Error | Database connection failed |

**Error Response Format:**
```json
{
  "detail": "Project with name 'my-project' already exists"
}
```

---

## Rate Limiting

Currently no rate limiting is implemented. For production deployment, consider adding:
- Nginx rate limiting
- API gateway (Kong, AWS API Gateway)
- Application-level rate limiting

---

## Troubleshooting

### Cannot connect to API

**Check server is running:**
```bash
curl http://localhost:8010/api/health
```

**Should return:**
```json
{"status": "healthy", "timestamp": "..."}
```

### 401 Unauthorized

**Development mode:** Ensure `UI_PASSWORD` is not set in `.env`

**Production mode:** Get a token via `/api/auth/login` and use it in requests

### 500 Database errors

**Ensure PostgreSQL is running:**
```bash
docker ps | grep postgres
```

**Check connection:**
```bash
psql $DATABASE_URL -c "SELECT 1;"
```

### WebSocket disconnects

**Check project exists:**
```bash
curl http://localhost:8010/api/projects/PROJECT_ID
```

**Check firewall/proxy settings** - WebSocket needs persistent connection

---

## v2.1 New Features & Endpoints

### Project Completion Reviews

Automatically verify projects meet original specifications with AI-powered analysis.

#### Get Latest Completion Review

```bash
curl http://localhost:8010/api/projects/PROJECT_ID/completion-review
```

**Response:**
```json
{
  "id": "review-123",
  "project_id": "PROJECT_ID",
  "overall_score": 87,
  "coverage_percentage": 92.5,
  "recommendation": "COMPLETE",
  "executive_summary": "Project successfully implements all core features...",
  "created_at": "2026-02-02T10:30:00Z"
}
```

#### Trigger Completion Review

```bash
curl -X POST http://localhost:8010/api/projects/PROJECT_ID/completion-review
```

#### Get Requirement Breakdown

```bash
curl http://localhost:8010/api/completion-reviews/review-123/requirements
```

**Response:**
```json
{
  "requirements": [
    {
      "id": 1,
      "section": "User Management",
      "requirement_text": "User registration with email verification",
      "priority": "high",
      "status": "implemented",
      "matched_epics": [5, 6],
      "matched_tasks": [42, 43, 44],
      "coverage_score": 95.0
    }
  ]
}
```

**Scoring Algorithm:**
- Coverage: 60% (requirements matched to epics/tasks)
- Quality: 20% (test pass rate, code quality)
- Bonus/Penalty: 20% (extra features, missing critical items)

**Recommendations:**
- `COMPLETE`: ≥90% coverage, score ≥85, no missing high-priority
- `NEEDS_WORK`: ≥70% coverage, score ≥70
- `FAILED`: <70% coverage or score <70

### Intervention Management

Handle session blockers and interruptions gracefully.

#### List Active Interventions

```bash
curl http://localhost:8010/api/interventions/active
```

**Response:**
```json
[
  {
    "intervention_id": "int-456",
    "project_id": "PROJECT_ID",
    "session_id": "session-789",
    "blocker_type": "epic_test_failure",
    "blocker_info": {
      "epic_id": 5,
      "epic_name": "User Authentication",
      "failed_tests": 3,
      "critical": true
    },
    "paused_at": "2026-02-02T10:00:00Z",
    "status": "active"
  }
]
```

#### Resume from Intervention

```bash
curl -X POST http://localhost:8010/api/interventions/int-456/resume \
  -H "Content-Type: application/json" \
  -d '{"resolution_notes": "Fixed authentication tests"}'
```

#### Notification Preferences

```bash
# Get preferences
curl http://localhost:8010/api/projects/PROJECT_ID/notifications/preferences

# Update preferences
curl -X POST http://localhost:8010/api/projects/PROJECT_ID/notifications/preferences \
  -H "Content-Type: application/json" \
  -d '{
    "email_enabled": true,
    "webhook_url": "https://hooks.slack.com/...",
    "on_session_blocked": true,
    "on_project_complete": true
  }'
```

### Deep Reviews & Statistics

Enhanced quality monitoring with detailed analytics.

#### List Deep Reviews

```bash
curl http://localhost:8010/api/projects/PROJECT_ID/deep-reviews?limit=10
```

**Response:**
```json
{
  "reviews": [
    {
      "id": "review-789",
      "session_id": "session-123",
      "quality_score": 8.5,
      "issues_found": 5,
      "recommendations": [
        {
          "theme": "error_handling",
          "suggestion": "Add try-catch blocks for API calls",
          "confidence": 0.85
        }
      ],
      "created_at": "2026-02-02T09:00:00Z"
    }
  ]
}
```

#### Get Review Statistics

```bash
curl http://localhost:8010/api/projects/PROJECT_ID/review-stats
```

**Response:**
```json
{
  "total_reviews": 25,
  "average_quality_score": 8.2,
  "total_issues_found": 120,
  "total_issues_resolved": 95,
  "resolution_rate": 79.2,
  "quality_trend": "improving"
}
```

#### Batch Trigger Reviews

```bash
curl -X POST http://localhost:8010/api/projects/PROJECT_ID/trigger-reviews \
  -H "Content-Type: application/json" \
  -d '{
    "review_type": "comprehensive",
    "session_ids": ["session-1", "session-2", "session-3"]
  }'
```

### Screenshots

Access visual verification artifacts from browser testing.

#### List Screenshots

```bash
curl http://localhost:8010/api/projects/PROJECT_ID/screenshots
```

**Response:**
```json
{
  "screenshots": [
    {
      "filename": "login-page-2026-02-02-10-30-45.png",
      "task_id": 42,
      "session_id": "session-123",
      "timestamp": "2026-02-02T10:30:45Z",
      "size_bytes": 125678,
      "url": "/api/projects/PROJECT_ID/screenshots/login-page-2026-02-02-10-30-45.png"
    }
  ]
}
```

#### Get Screenshot

```bash
# Download screenshot
curl http://localhost:8010/api/projects/PROJECT_ID/screenshots/login-page.png \
  --output login-page.png
```

---

## v2.0 Endpoints (Legacy Documentation)

### Session Management

#### Get Session Logs

Retrieve structured logs for a session with pagination and filtering:

```bash
# Get latest 100 log entries
curl "http://localhost:8010/api/sessions/SESSION_ID/logs?offset=0&limit=100"

# Filter by log level
curl "http://localhost:8010/api/sessions/SESSION_ID/logs?level=error"
```

**Response:**
```json
{
  "logs": [
    {
      "timestamp": "2026-01-08T15:30:45Z",
      "level": "info",
      "message": "Task completed successfully",
      "task_id": "123"
    }
  ],
  "total": 1250,
  "offset": 0,
  "limit": 100
}
```

#### Pause/Resume Sessions

```bash
# Pause an active session
curl -X POST http://localhost:8010/api/sessions/SESSION_ID/pause

# Resume a paused session
curl -X POST http://localhost:8010/api/sessions/SESSION_ID/resume
```

Both return `204 No Content` on success.

### Task & Epic Management

#### Get Task Details

```bash
curl http://localhost:8010/api/tasks/42
```

**Response:**
```json
{
  "id": 42,
  "name": "Implement user authentication",
  "status": "in_progress",
  "description": "Add JWT-based authentication",
  "epic_id": 5
}
```

#### Update Task Status

```bash
curl -X PATCH http://localhost:8010/api/tasks/42 \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}'
```

#### Get Epic Progress

```bash
curl http://localhost:8010/api/epics/5/progress
```

**Response:**
```json
{
  "epic_id": 5,
  "name": "User Management",
  "total_tasks": 15,
  "completed_tasks": 8,
  "in_progress_tasks": 2,
  "pending_tasks": 5,
  "progress_percentage": 53.3,
  "status": "in_progress"
}
```

### Quality & Verification

#### Trigger Quality Review

```bash
curl -X POST http://localhost:8010/api/sessions/SESSION_ID/quality-review \
  -H "Content-Type: application/json" \
  -d '{"review_type": "comprehensive"}'
```

**Response:**
```json
{
  "id": "review-abc123",
  "session_id": "SESSION_ID",
  "review_type": "comprehensive",
  "status": "pending"
}
```

#### Get Quality Metrics

```bash
curl http://localhost:8010/api/projects/PROJECT_ID/quality-metrics
```

**Response:**
```json
{
  "project_id": "PROJECT_ID",
  "code_quality_score": 8.5,
  "test_coverage": 85.3,
  "issues_found": 12,
  "issues_resolved": 8,
  "last_review": "2026-01-08T15:30:45Z"
}
```

### Health Check

#### Detailed Health Status

Get component-level health information:

```bash
curl http://localhost:8010/health/detailed
```

**Response:**
```json
{
  "status": "healthy",
  "database": {
    "status": "healthy",
    "pool_size": 10,
    "active_connections": 2
  },
  "mcp_server": {
    "status": "healthy",
    "version": "1.0.0"
  },
  "disk": {
    "status": "healthy",
    "free_space_gb": 150.5
  },
  "sessions": {
    "active": 2,
    "paused": 1
  }
}
```

---

## Related Documentation

### Core Documentation
- **[authentication.md](authentication.md)** - Authentication system details
- **[deployment-guide.md](deployment-guide.md)** - Production deployment
- **[developer-guide.md](developer-guide.md)** - Platform architecture
- **[configuration.md](configuration.md)** - Configuration reference

### Quality & Testing
- **[quality-system.md](quality-system.md)** - Complete quality system (Phases 0-8) ⭐ NEW v2.1
- **[verification-system.md](verification-system.md)** - Automatic verification system
- **[testing-guide.md](testing-guide.md)** - Testing practices

### Reference
- **[mcp-usage.md](mcp-usage.md)** - MCP tools documentation
- **[input-validation.md](input-validation.md)** - Validation framework
- **[ai-spec-generation.md](ai-spec-generation.md)** - AI specification generation ⭐ NEW v2.1
- **[QUALITY_SYSTEM_SUMMARY.md](../QUALITY_SYSTEM_SUMMARY.md)** - Phase-by-phase implementation summary ⭐ NEW v2.1

---

## Need Help?

- **Interactive docs:** http://localhost:8010/docs
- **API reference:** http://localhost:8010/redoc
- **GitHub issues:** Report bugs or request features

The Swagger UI at `/docs` is the best place to explore and test the API interactively!
