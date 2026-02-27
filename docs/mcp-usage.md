# MCP Task Manager

A Model Context Protocol (MCP) server for managing hierarchical task tracking in autonomous coding projects. TypeScript server using `pg` (node-postgres) for PostgreSQL operations with connection pooling.

## Building

```bash
cd mcp-task-manager
npm install
npm run build
```

## Configuration

The MCP server is automatically configured by `client.py` when sessions start. It receives two environment variables:

- `DATABASE_URL` — PostgreSQL connection string
- `PROJECT_ID` — UUID scoping all queries to a specific project

No manual configuration is needed. Just ensure `dist/index.js` exists (run `npm run build`) and PostgreSQL is running.

## Tools

All tools are prefixed with `mcp__task-manager__` when called by agents.

### Query Tools

| Tool | Description |
|------|-------------|
| `task_status` | Overall project progress statistics |
| `get_next_task` | Next highest priority task to work on |
| `list_epics` | All epics (with optional `needs_expansion` filter) |
| `get_epic` | Epic details with all tasks |
| `list_tasks` | Tasks with filtering (by epic, status) |
| `get_task` | Task details including tests |
| `list_tests` | All tests for a specific task |
| `get_task_tests` | Task-level test cases |
| `get_epic_tests` | Epic-level integration tests |
| `get_session_history` | Recent work session log |

### Mutation Tools

| Tool | Description |
|------|-------------|
| `create_epic` | Create new high-level feature area |
| `create_task` | Create task within an epic |
| `create_task_test` | Add test case to a task |
| `create_epic_test` | Add integration test to an epic |
| `expand_epic` | Break epic into multiple tasks (bulk create) |
| `update_task_status` | Mark task complete/incomplete |
| `start_task` | Mark task as started (tracks timing) |
| `update_task_test_result` | Record task test pass/fail with error details and execution time |
| `update_epic_test_result` | Record epic test pass/fail with error details and execution time |
| `mark_project_complete` | Mark entire project as complete |

## Database Schema

The MCP server interacts with these PostgreSQL tables:

- `projects` — Project definitions (UUID primary keys, JSONB metadata)
- `epics` — High-level feature areas
- `tasks` — Individual coding tasks within epics
- `task_tests` — Test cases for each task
- `epic_tests` — Integration tests for each epic
- `sessions` — Work session history

Key views: `v_progress` (aggregate statistics), `v_epic_progress` (per-epic completion).

All queries are automatically scoped by `PROJECT_ID`. See `schema/postgresql/` for complete DDL.

## Development

```bash
cd mcp-task-manager
npm run dev       # Watch mode (auto-rebuild on changes)
npm run build     # Build once
```

### Adding New Tools

1. Edit `mcp-task-manager/src/index.ts`
2. Add tool definition to the `ListToolsRequestSchema` handler
3. Add tool implementation to the `CallToolRequestSchema` handler
4. Rebuild: `npm run build`

## Troubleshooting

**"MCP server not found"** — Rebuild: `cd mcp-task-manager && npm run build`

**"Database connection error"** — Ensure PostgreSQL is running (`docker-compose up -d`) and `DATABASE_URL` is set in `.env`

**Agent doesn't see tools** — Check `dist/index.js` exists, PostgreSQL is running, and `DATABASE_URL` is correct. Restart the session.
