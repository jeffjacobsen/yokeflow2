# API Usage Guide

YokeFlow provides a RESTful API for managing projects and sessions programmatically. The Web UI uses this API, and you can use it directly for automation or integration.

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

---

## Common Workflows

### 1. Create and Build a Project

```bash
# Create project with spec file
curl -X POST http://localhost:8010/api/projects \
  -F "name=my-todo-app" \
  -F "spec_files=@app_spec.txt"

# Initialize (creates epics, tasks, and tests)
curl -X POST http://localhost:8010/api/projects/{project_id}/initialize

# Check progress
curl http://localhost:8010/api/projects/{project_id}/progress

# Start coding sessions
curl -X POST http://localhost:8010/api/projects/{project_id}/coding/start
```

### 2. Import an Existing Codebase (Brownfield)

```bash
# Import from local path or GitHub
curl -X POST http://localhost:8010/api/projects/import \
  -F "name=my-existing-app" \
  -F "source_path=/path/to/codebase" \
  -F "change_spec=@change_spec.md"

# Roll back to original imported state
curl -X POST http://localhost:8010/api/projects/{project_id}/rollback
```

### 3. Monitor with WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8010/api/ws/{project_id}');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.type, data);
};
```

---

## API Endpoints

### Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/health/detailed` | Component-level health status |
| `GET` | `/api/info` | API version and info |

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/login` | Login and get JWT token |
| `GET` | `/api/auth/verify` | Verify token validity |

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/projects` | List all projects |
| `POST` | `/api/projects` | Create new project |
| `POST` | `/api/projects/import` | Import existing codebase (brownfield) |
| `GET` | `/api/projects/{id}` | Get project details |
| `PATCH` | `/api/projects/{id}` | Rename project |
| `DELETE` | `/api/projects/{id}` | Delete project |
| `POST` | `/api/projects/{id}/reset` | Reset to post-initialization state |
| `POST` | `/api/projects/{id}/rollback` | Roll back brownfield project to imported state |
| `GET` | `/api/projects/{id}/progress` | Get progress stats |
| `GET` | `/api/projects/{id}/settings` | Get project settings |
| `PUT` | `/api/projects/{id}/settings` | Update project settings |
| `GET` | `/api/projects/{id}/env` | Get environment variables |
| `POST` | `/api/projects/{id}/env` | Set environment variables |

### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/projects/{id}/initialize` | Start initialization (Session 0) |
| `POST` | `/api/projects/{id}/initialize/cancel` | Cancel running initialization |
| `POST` | `/api/projects/{id}/coding/start` | Start coding sessions |
| `GET` | `/api/projects/{id}/sessions` | List all sessions |
| `GET` | `/api/projects/{id}/sessions/{sid}` | Get session details |
| `POST` | `/api/projects/{id}/sessions/{sid}/stop` | Stop a running session |
| `POST` | `/api/projects/{id}/stop-after-current` | Stop after current session completes |
| `DELETE` | `/api/projects/{id}/stop-after-current` | Cancel queued stop |
| `GET` | `/api/sessions/{sid}/logs` | Get session logs (paginated) |

### Epics & Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/projects/{id}/epics` | List all epics |
| `GET` | `/api/projects/{id}/epics/{epic_id}` | Get epic with tasks |
| `GET` | `/api/epics/{epic_id}/progress` | Get epic progress breakdown |
| `GET` | `/api/projects/{id}/tasks` | List all tasks (optional `?status=` filter) |
| `GET` | `/api/projects/{id}/tasks/{task_id}` | Get task with tests and epic context |
| `GET` | `/api/tasks/{task_id}` | Get task by ID (without project ID) |
| `PATCH` | `/api/tasks/{task_id}` | Update task status |

### Testing & Coverage

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/projects/{id}/coverage` | Test coverage analysis |
| `GET` | `/api/projects/{id}/test-health` | Test health aggregates |
| `GET` | `/api/projects/{id}/all-tests` | All tests grouped by epic and task |

### Quality & Reviews

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions/{sid}/quality-review` | Trigger quality review for session |
| `GET` | `/api/projects/{id}/quality-metrics` | Quality metrics summary |
| `GET` | `/api/projects/{id}/deep-reviews` | List deep reviews |
| `GET` | `/api/projects/{id}/review-stats` | Review statistics |
| `POST` | `/api/projects/{id}/sessions/{sid}/review` | Trigger session review |
| `POST` | `/api/projects/{id}/trigger-reviews` | Batch trigger reviews |

### Completion Reviews

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/projects/{id}/completion-review` | Get latest completion review |
| `POST` | `/api/projects/{id}/completion-review` | Trigger completion review |
| `GET` | `/api/completion-reviews` | List all reviews (with filters) |
| `GET` | `/api/completion-reviews/{id}/requirements` | Requirement breakdown |
| `GET` | `/api/completion-reviews/{id}/section-summary` | Section-level summary |

### Logs & Screenshots

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/projects/{id}/logs` | List available log files |
| `GET` | `/api/projects/{id}/logs/human/{filename}` | Get human-readable log |
| `GET` | `/api/projects/{id}/logs/events/{filename}` | Get event log (JSONL) |
| `GET` | `/api/projects/{id}/screenshots` | List screenshots |
| `GET` | `/api/projects/{id}/screenshots/{filename}` | Get screenshot image |

### Prompt Improvements

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/prompt-improvements` | Trigger cross-project analysis |
| `GET` | `/api/prompt-improvements` | List analyses |
| `GET` | `/api/prompt-improvements/config` | Get system configuration |
| `GET` | `/api/prompt-improvements/metrics` | Get improvement metrics |
| `GET` | `/api/prompt-improvements/{id}` | Get analysis details |
| `DELETE` | `/api/prompt-improvements/{id}` | Delete analysis |
| `GET` | `/api/prompt-improvements/{id}/proposals` | Get proposals from analysis |
| `GET` | `/api/prompt-improvements/{id}/raw-report` | Get raw analysis report |
| `PATCH` | `/api/prompt-improvements/proposals/{id}` | Update proposal status |
| `POST` | `/api/prompt-improvements/proposals/{id}/apply` | Apply proposal to prompt file |
| `POST` | `/api/prompt-improvements/proposals/{id}/generate-diff` | Generate diff for proposal |

### Administration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/admin/cleanup-orphaned-sessions` | Clean up orphaned sessions |
| `POST` | `/api/generate-spec` | Generate spec with AI (streaming) |
| `POST` | `/api/validate-spec` | Validate specification file |

### WebSocket

| Method | Endpoint | Description |
|--------|----------|-------------|
| `WS` | `/api/ws/{project_id}` | Real-time project updates |

**WebSocket event types:** `session_update`, `progress_update`, `tool_use`, `tool_result`, `session_complete`, `error`

---

## Authentication

### Development Mode (Default)

No authentication required when `UI_PASSWORD` is not set:

```bash
curl http://localhost:8010/api/projects
```

### Production Mode

When `UI_PASSWORD` is set, obtain a JWT token:

```bash
# Login
curl -X POST http://localhost:8010/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password": "your-password"}'

# Use token
curl http://localhost:8010/api/projects \
  -H "Authorization: Bearer YOUR_TOKEN"
```

See [authentication.md](authentication.md) for details.

---

## Examples

### Automated Project Lifecycle (Python)

```python
import requests
import time

API_URL = "http://localhost:8010"

# Create project
with open('app_spec.txt', 'rb') as f:
    response = requests.post(
        f"{API_URL}/api/projects",
        files={'spec_files': f},
        data={'name': 'automated-project'}
    )
    project_id = response.json()['project_id']

# Initialize
response = requests.post(f"{API_URL}/api/projects/{project_id}/initialize")
session_id = response.json()['session_id']

# Wait for initialization
while True:
    status = requests.get(
        f"{API_URL}/api/projects/{project_id}/sessions/{session_id}"
    ).json()
    if status['status'] in ('completed', 'error'):
        break
    time.sleep(5)

# Start coding
requests.post(f"{API_URL}/api/projects/{project_id}/coding/start")
```

### Monitor Progress

```python
response = requests.get(f"{API_URL}/api/projects/{project_id}/progress")
progress = response.json()

print(f"Tasks: {progress['completed_tasks']}/{progress['total_tasks']}")
print(f"Completion: {progress['task_completion_pct']:.1f}%")
```

### WebSocket with Python

```python
import asyncio
import websockets
import json

async def monitor_project(project_id):
    uri = f"ws://localhost:8010/api/ws/{project_id}"
    async with websockets.connect(uri) as ws:
        while True:
            data = json.loads(await ws.recv())
            if data['type'] == 'progress_update':
                print(f"Progress: {data['progress']['task_completion_pct']:.1f}%")
            elif data['type'] == 'session_complete':
                break

asyncio.run(monitor_project("your-project-id"))
```

---

## CORS Configuration

**Default allowed origins:**
- `http://localhost:3010` (Next.js dev server)
- `http://localhost:5173` (Vite dev server)

Set `CORS_ORIGINS` in `.env` to add custom origins:
```bash
CORS_ORIGINS=http://localhost:3010,https://my-domain.com
```

---

## Error Handling

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `400` | Bad request (missing/invalid parameters) |
| `401` | Unauthorized (invalid/missing token) |
| `404` | Not found |
| `409` | Conflict (e.g., session already running) |
| `500` | Server error |

Error response format:
```json
{
  "detail": "Project with name 'my-project' already exists"
}
```

---

## Troubleshooting

**Cannot connect to API:**
```bash
curl http://localhost:8010/api/health
# Should return: {"status": "healthy", ...}
```

**401 Unauthorized:** In development mode, ensure `UI_PASSWORD` is not set in `.env`. In production, get a token via `/api/auth/login`.

**500 Database errors:** Ensure PostgreSQL is running (`docker-compose up -d`) and `DATABASE_URL` is correct in `.env`.

**WebSocket disconnects:** Verify the project ID exists and check firewall/proxy settings (WebSocket needs a persistent connection).

---

## Related Documentation

- [authentication.md](authentication.md) - Authentication details
- [configuration.md](configuration.md) - Configuration reference
- [developer-guide.md](developer-guide.md) - Platform architecture
- [quality-system.md](quality-system.md) - Quality system
- [mcp-usage.md](mcp-usage.md) - MCP tools
- [input-validation.md](input-validation.md) - Validation framework
