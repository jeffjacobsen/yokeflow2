# Developer Guide

Technical reference for developers who want to understand, customize, or extend YokeFlow.

## Architecture Overview

```
┌─────────────────┐
│   Web Browser   │
└────────┬────────┘
         │ HTTP/WebSocket
         ▼
┌─────────────────────┐
│  Next.js Web UI     │  TypeScript/React (port 3010)
└────────┬────────────┘
         │ REST API
         ▼
┌─────────────────────┐
│   FastAPI Server    │  Python (port 8010)
│ server/api/app.py   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────────────┐
│  server/agent/orchestrator  │  Session lifecycle
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  server/agent/agent.py      │  Agent loop
└────────┬────────────────────┘
         │
         ├──────────────────────────┐
         ▼                          ▼
┌────────────────────┐   ┌─────────────────────┐
│ server/client/     │   │ server/client/      │
│   claude.py        │   │   prompts.py        │
└──────┬─────────────┘   └─────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│   Claude SDK Client             │
│   - MCP servers loaded          │
│   - Security hooks active       │
│   - Observability logging       │
└──────┬──────────────────────────┘
       │
       ├────────────────┬─────────────┐
       ▼                ▼             ▼
┌──────────────┐  ┌─────────┐  ┌──────────────┐
│ MCP Server   │  │Security │  │Observability │
│ task-manager │  │Blocklist│  │Session Logs  │
└──────┬───────┘  └─────────┘  └──────────────┘
       │
       ▼
┌─────────────────────────┐
│ PostgreSQL Database     │
└─────────────────────────┘
```

### Data Flow

**Initialization (Session 0):**
1. User creates project via Web UI or CLI
2. `orchestrator.py` creates project in PostgreSQL, copies spec
3. `client.py` creates Claude SDK client with MCP task-manager
4. `prompts.py` loads `initializer_prompt.md`
5. Agent creates epics, tasks, and tests via MCP tools
6. Session auto-stops when roadmap is complete

**Coding (Sessions 1+):**
1. `orchestrator.py` detects existing epics, selects coding mode
2. `prompts.py` loads `coding_prompt.md`
3. Agent loop: `get_next_task` → implement → browser verify → `update_task_status` → git commit
4. Auto-continues with configurable delay between sessions

---

## Server Directory Structure

```
server/
├── agent/               # Session orchestration & lifecycle
│   ├── agent.py         # Agent loop and session logic
│   ├── orchestrator.py  # Session lifecycle (greenfield + brownfield)
│   ├── codebase_import.py # Brownfield codebase import & analysis
│   ├── checkpoint.py    # Session checkpointing and recovery
│   └── models.py        # Orchestrator data models
├── api/                 # REST API & WebSocket
│   ├── app.py           # Main FastAPI application (60+ endpoints)
│   ├── auth.py          # JWT authentication
│   ├── validation.py    # Pydantic validation models
│   ├── validators.py    # Custom validators
│   ├── rate_limiter.py  # Rate limiting
│   ├── start.py         # API startup wrapper
│   └── routes/
│       └── prompt_improvements.py
├── client/              # External service clients
│   ├── claude.py        # Claude SDK client + MCP pre-flight check
│   └── prompts.py       # Prompt loading and project setup
├── database/            # Database layer
│   ├── operations.py    # PostgreSQL operations (async)
│   ├── connection.py    # Connection pooling
│   └── retry.py         # Retry logic with exponential backoff
├── quality/             # Quality & review system
│   ├── reviews.py       # Deep AI-powered reviews
│   ├── integration.py   # Quality trigger coordination
│   ├── spec_parser.py   # Specification parser
│   ├── code_analyzer.py # Codebase analysis
│   ├── prompt_analyzer.py # Prompt improvement suggestions
│   ├── implementation_reviewer.py # Implementation review
│   ├── test_compliance_analyzer.py # Test compliance checking
│   └── test_result_collector.py # Test result collection
├── generation/          # Spec generation
│   ├── spec_analyzer.py # Spec analysis
│   ├── spec_generator.py # Spec generation
│   ├── spec_validator.py # Spec validation
│   ├── context_manager.py # Context management
│   └── context_manifest.py # Context manifest
└── utils/               # Shared utilities
    ├── config.py        # Configuration (.yokeflow.yaml)
    ├── logging.py       # Structured logging (JSON/dev formatters)
    ├── errors.py        # Error hierarchy (30+ error types)
    ├── security.py      # Bash command blocklist
    ├── observability.py # Session logging (JSONL + TXT)
    ├── progress.py      # Progress tracking utilities
    ├── project_paths.py # Project directory path resolution
    ├── reset.py         # Project reset logic
    ├── metrics_collector.py # Metrics collection
    └── cancel_initialization.py # Cancel operations
```

---

## Core Components

### server/agent/agent.py

Core agent session logic. `run_agent_session()` creates a Claude SDK client context, sends the prompt, processes the response stream (AssistantMessage, UserMessage, SystemMessage), applies output filtering for terminal display, and logs via SessionLogger.

### server/agent/orchestrator.py

Session lifecycle management. Detects first run vs continuation by checking for epics in PostgreSQL. Selects the appropriate model (Opus for initialization, Sonnet for coding) and prompt. Auto-stops after initialization, auto-continues after coding sessions.

**Session type detection:**
```python
async with DatabaseManager() as db:
    epics = await db.list_epics(project_id)
    is_first_run = len(epics) == 0
```

### server/client/claude.py

Claude SDK client configuration. Loads MCP servers (task-manager), configures `bypassPermissions` for autonomous operation, sets up security hooks (Bash blocklist), and passes project-specific environment variables to MCP servers. Includes MCP pre-flight check that auto-rebuilds the MCP server if stale.

### server/client/prompts.py

Prompt loading and project setup. Loads prompt files from `prompts/` directory and copies spec files to the project directory.

### server/database/operations.py

PostgreSQL abstraction layer with async operations via asyncpg. Provides `TaskDatabase` class with methods for all CRUD operations on projects, epics, tasks, tests, and sessions. All operations use connection pooling and automatic retry logic (see `retry.py`).

### server/database/retry.py

Exponential backoff retry logic for transient database failures. Covers 20+ PostgreSQL error codes. Applied automatically to all database operations.

### server/utils/security.py

Bash command blocklist validation. Blocks dangerous commands (rm, sudo, apt, reboot, etc.) while allowing development tools (npm, git, curl, python). Special handling for `pkill` (only allows development processes). See [CLAUDE.md](../CLAUDE.md) for the full blocked command list.

### server/utils/observability.py

Session logging with dual-format output:
- **JSONL** (machine-readable): events with timestamps, tool calls, results
- **TXT** (human-readable): formatted session transcript

Log location: `projects/[project]/yokeflow/logs/`

`QuietOutputFilter` controls terminal verbosity — quiet mode shows only assistant text and Bash tools; verbose mode shows everything.

### server/utils/config.py

Configuration management. Loads settings from `.yokeflow.yaml` with priority: Web UI settings > config file > defaults. See [configuration.md](configuration.md) for all options.

### server/quality/

Quality system components for AI-powered reviews, spec parsing, test compliance analysis, and prompt improvement suggestions. See [quality-system.md](quality-system.md) for details.

---

## MCP Integration

The MCP task-manager server (`mcp-task-manager/src/index.ts`) provides 20 tools for managing the epic/task/test hierarchy in PostgreSQL. See [mcp-usage.md](mcp-usage.md) for the complete tool reference, build instructions, and development guide.

**How it connects:** `client.py` passes `DATABASE_URL` and `PROJECT_ID` as environment variables to the MCP server process. All queries are automatically scoped by project.

---

## Database

PostgreSQL with UUID-based project identification and a 3-tier hierarchy: projects → epics → tasks (with task_tests and epic_tests).

See `schema/postgresql/schema.sql` for the complete DDL. Key tables and views are documented in [CLAUDE.md](../CLAUDE.md).

**Modifying the schema:**
1. Edit `schema/postgresql/schema.sql`
2. Test with a fresh database: `python scripts/init_database.py --docker`

---

## Security

**Blocklist approach:** Allow all commands except explicitly dangerous ones. The blocklist is in `server/utils/security.py`. Edit the `BLOCKED_COMMANDS` set to add or remove commands.

**Authentication:** JWT-based, implemented in `server/api/auth.py`. Single-user mode with password set via `UI_PASSWORD` environment variable. When not set, auth is bypassed (development mode). See [authentication.md](authentication.md) for details.

---

## Testing

173 pure unit tests with no mocks or external dependencies. Run in ~1 second.

```bash
pytest                      # Run all tests
python scripts/test_quick.py  # Helper script
```

See [testing-guide.md](testing-guide.md) for the full test file listing and coverage instructions.

---

## Extending the System

### Adding Custom Prompts

1. Create a new prompt file in `prompts/`
2. Add a loader function in `server/client/prompts.py`
3. Call it from the orchestrator when needed

### Adding a Custom MCP Server

1. Create a new MCP server (Node.js or Python)
2. Register it in `server/client/claude.py`:
```python
mcp_servers = {
    "task-manager": {...},
    "my-server": {
        "command": "node",
        "args": [str(my_server_path)],
        "env": {"MY_VAR": "value"}
    }
}
```
3. Reference tools in prompts: `mcp__my-server__tool_name`

See [MCP Protocol Specification](https://spec.modelcontextprotocol.io/) for details.

### Adding API Endpoints

Add routes to `server/api/app.py` or create a new route module in `server/api/routes/`. Use Pydantic models from `server/api/validation.py` for request validation. See [api-usage.md](api-usage.md) for the existing endpoint reference.

### Web UI Changes

- Pages and routes: `web-ui/src/app/`
- React components: `web-ui/src/components/`
- API client: `web-ui/src/lib/api.ts`

---

## Development Workflow

```bash
# Start PostgreSQL
docker compose up -d

# Start API server (with auto-reload)
uvicorn server.api.app:app --host 0.0.0.0 --port 8010 --reload

# Start Web UI (in another terminal)
cd web-ui && npm run dev

# Run tests after changes
pytest
```

### Debugging

**MCP server:** Add `console.error()` calls in `mcp-task-manager/src/index.ts` — MCP stderr output appears in agent logs. Rebuild with `npm run build`.

**Database:** Connect directly with `psql $DATABASE_URL`. Key views: `v_progress`, `v_epic_progress`.

**Session logs:** Check `projects/[project]/yokeflow/logs/` for JSONL (structured) and TXT (human-readable) logs.

---

## Related Documentation

- [CLAUDE.md](../CLAUDE.md) — Quick reference for the entire platform
- [api-usage.md](api-usage.md) — REST API endpoint reference
- [mcp-usage.md](mcp-usage.md) — MCP tools reference
- [configuration.md](configuration.md) — Configuration options
- [quality-system.md](quality-system.md) — Quality system overview
- [testing-guide.md](testing-guide.md) — Test suite documentation
- [deployment-guide.md](deployment-guide.md) — Digital Ocean deployment
- [authentication.md](authentication.md) — JWT authentication details
