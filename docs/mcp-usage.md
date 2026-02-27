# MCP Task Management

YokeFlow uses MCP (Model Context Protocol) for all task management operations. This provides a structured, type-safe, protocol-based interface for agents to manage tasks.

**Version**: 2.1.0

## What's New in v2.1

YokeFlow 2.1 adds quality system MCP tools:

- **Test Execution Tracking** (Phase 1-2): `update_task_test_result`, `update_epic_test_result` - Track error messages, execution time, retry counts

See [QUALITY_SYSTEM_SUMMARY.md](../QUALITY_SYSTEM_SUMMARY.md) for implementation details.

**For detailed MCP server documentation, see [mcp-task-manager/README.md](../mcp-task-manager/README.md)**

---

## Quick Start

### Running the Agent

The MCP task manager is automatically enabled when you run sessions:

```bash
# Via Web UI
# Navigate to http://localhost:3010 and click "Start Session"
```

No configuration needed - MCP is automatically set up.

### Testing MCP

Test the MCP integration:

```bash
python tests/test_mcp.py
```

This verifies the MCP server is working correctly with the database.

---

## Available Tools

All tools are prefixed with `mcp__task-manager__`:

### Query Tools (Read)
- `task_status` - Overall project progress
- `get_next_task` - Next task to work on
- `list_epics` - All epics
- `get_epic` - Epic details with tasks
- `list_tasks` - Tasks with filtering
- `get_task` - Task details including tests
- `list_tests` - Tests for a task
- `get_session_history` - Recent sessions

### Update Tools (Write)
- `update_task_status` - Mark task complete/incomplete
- `start_task` - Mark task as started
- `update_test_result` - Mark test pass/fail (legacy)
- `update_task_test_result` - Mark task test pass/fail with error details ⭐ NEW v2.1
- `update_epic_test_result` - Mark epic test pass/fail with error details ⭐ NEW v2.1

### Create Tools
- `create_epic` - Create new epic
- `create_task` - Create task in epic
- `create_test` - Add test to task
- `expand_epic` - Break epic into tasks

**See [mcp-task-manager/README.md](../mcp-task-manager/README.md#features) for detailed tool documentation**

---

## v2.1 New Tools

### Test Execution Tracking (Phase 1-2)

Enhanced test result tracking with error details, execution time, and retry counts.

#### `update_task_test_result`

Record task test results with comprehensive execution details:

```typescript
mcp__task-manager__update_task_test_result({
  test_id: 42,
  passed: false,
  error_message: "AssertionError: Expected 200, got 404",
  execution_time_ms: 1250
})
```

**What it tracks:**
- Pass/fail status
- Last error message (for debugging)
- Execution time in milliseconds (for performance analysis)
- Retry count (auto-incremented on failures)

**Use cases:**
- Debugging test failures with exact error messages
- Detecting slow tests (execution_time_ms > threshold)
- Identifying flaky tests (high retry count)

#### `update_epic_test_result`

Similar to task test results, but for epic-level integration tests:

```typescript
mcp__task-manager__update_epic_test_result({
  epic_test_id: 15,
  passed: true,
  execution_time_ms: 3500
})
```

---

## Why MCP?

**MCP (Model Context Protocol) provides:**
- ✅ Structured, type-safe interface
- ✅ Proper parameter validation
- ✅ Better error handling
- ✅ No shell escaping issues
- ✅ Easier to extend
- ✅ JSON-based communication

**vs. Shell scripts:**
- ❌ String parsing fragile
- ❌ Hard to validate inputs
- ❌ Escaping/quoting issues
- ❌ No type safety

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│ Autonomous      │────▶│ Claude SDK      │
│ Agent           │     │ Client          │
└─────────────────┘     └─────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ MCP Server          │
                    │ (task-manager)      │
                    └─────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ PostgreSQL Database │
                    │ (centralized)       │
                    └─────────────────────┘
```

**Key Points:**
- **MCP Server** runs as a subprocess of the agent
- **PostgreSQL** stores all task data centrally
- **Project Scoping** via `PROJECT_ID` environment variable
- **Connection Pooling** for efficient database access

---

## Database Connection

The MCP server connects to PostgreSQL automatically:

**Environment Variables:**
```bash
DATABASE_URL="postgresql://user:pass@localhost:5432/yokeflow"
PROJECT_ID="550e8400-e29b-41d4-a716-446655440000"
```

These are automatically set by `orchestrator.py` when sessions start.

**Database Schema:**
- `projects` - Project metadata
- `epics` - High-level feature areas (15-25 per project)
- `tasks` - Specific work items (8-15 per epic)
- `tests` - Test cases (1-3 per task)
- `sessions` - Session history and metrics

**See [schema/postgresql/](../schema/postgresql/) for complete schema**

---

## Troubleshooting

### MCP Server Not Found

**Error:** `MCP server not found` or `dist/index.js missing`

**Solution:**
```bash
cd mcp-task-manager
npm install
npm run build
```

### Database Connection Failed

**Error:** `Connection refused` or `database "yokeflow" does not exist`

**Solution:**
```bash
# Start PostgreSQL
docker-compose up -d

# Initialize database
python scripts/init_database.py

# Verify connection
psql $DATABASE_URL -c "SELECT version();"
```

### Tools Not Available

**Error:** Agent doesn't see `mcp__task-manager__*` tools

**Solution:**
1. Check MCP server is built (`ls mcp-task-manager/dist/index.js`)
2. Verify PostgreSQL is running (`docker ps | grep postgres`)
3. Check `DATABASE_URL` in `.env` file
4. Restart the session

---

## For Developers

### Building the MCP Server

```bash
cd mcp-task-manager
npm install       # Install dependencies
npm run build     # Compile TypeScript → JavaScript
npm run watch     # Auto-rebuild on changes
```

### Adding New Tools

1. Edit `mcp-task-manager/src/index.ts`
2. Add tool to `server.setRequestHandler(ListToolsRequestSchema, ...)`
3. Implement handler in `server.setRequestHandler(CallToolRequestSchema, ...)`
4. Rebuild: `npm run build`

**See [mcp-task-manager/README.md#development](../mcp-task-manager/README.md#development) for detailed development guide**

### Testing Changes

```bash
# Test MCP server directly
npm test

# Test via agent
python tests/test_mcp.py
```

---

## Related Documentation

- **[mcp-task-manager/README.md](../mcp-task-manager/README.md)** - Complete MCP server documentation
- **[developer-guide.md](developer-guide.md)** - Platform architecture and development
- **[configuration.md](configuration.md)** - Configuration options

---

## Historical Note

**MCP replaced shell scripts (December 2025):**
- Old: `task-helper.sh` with JSONL file storage
- New: MCP server with PostgreSQL database
- Migration: Automatic via database schema

All new development uses MCP. Shell-based task management has been removed.
