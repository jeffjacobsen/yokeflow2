# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## What This Is

**YokeFlow 2** - An autonomous AI development platform that uses Claude to build complete applications over multiple sessions.

**Status**: Archived - v2.5.1

**Architecture**: API-first platform with FastAPI + Next.js Web UI + PostgreSQL + MCP task management

**Workflow**: Opus creates roadmap (Session 0: epics + tasks + tests) → Sonnet implements features (Sessions 1+)

## Core Workflow

**Greenfield Session 0**: Reads spec from `yokeflow/specs/` → Creates epics, tasks, and tests in PostgreSQL → Runs `init.sh`

**Brownfield Session 0**: Explores imported codebase → Reads `yokeflow/specs/change_spec.md` → Creates scoped epics, tasks, and tests

**Sessions 1+ (Coding)**: Get next task → Implement → Browser verify (with agent-browser) → Update database → Git commit → Auto-continue

**Key Files**:
- `server/agent/orchestrator.py` - Session lifecycle (greenfield + brownfield)
- `server/agent/codebase_import.py` - Codebase import and analysis (brownfield)
- `server/agent/agent.py` - Agent loop and session logic
- `server/database/operations.py` - PostgreSQL abstraction (async) + retry logic
- `server/database/retry.py` - Retry logic with exponential backoff
- `server/client/claude.py` - Claude SDK client + MCP pre-flight check/auto-rebuild
- `server/agent/checkpoint.py` - Session checkpointing and recovery
- `server/utils/logging.py` - Structured logging with JSON/dev formatters
- `server/utils/errors.py` - Error hierarchy with 30+ error types
- `server/api/app.py` - REST API + WebSocket
- `server/utils/observability.py` - Session logging (JSONL + TXT)
- `server/utils/security.py` - Blocklist validation
- `prompts/` - Agent instructions


## Database

**Schema**: PostgreSQL with 3-tier hierarchy: `epics` → `tasks` → `tests`

**Key tables**:
- Core: `projects` (with `project_type`, `codebase_analysis` for brownfield), `epics`, `tasks`, `task_tests`, `sessions`
- Production: `session_checkpoints`, `session_deep_reviews`
- Quality: `epic_tests`, `project_completion_reviews`, `completion_requirements`
- Prompt System: `prompt_improvement_analyses`, `prompt_proposals`

**Key views**:
- Core: `v_progress`, `v_epic_progress`
- Production: `v_resumable_checkpoints`
- Completion: `v_latest_completion_review`, `v_completion_section_summary`, `v_project_completion_stats`

**Access**: Use `server/database/operations.py` abstraction (async/await). See `schema/postgresql/` for DDL.

**Retry Logic**: All database operations automatically retry on transient failures (exponential backoff)

## MCP Tools

The `mcp-task-manager/` provides 20 tools (prefix: `mcp__task-manager__`):

**Query**: `task_status`, `get_next_task`, `list_epics`, `get_epic`, `list_tasks`, `get_task`, `list_tests`, `get_task_tests`, `get_epic_tests`, `get_session_history`

**Update**: `update_task_status`, `start_task`, `update_task_test_result`, `update_epic_test_result`, `mark_project_complete`

**Create**: `create_epic`, `create_task`, `create_task_test`, `create_epic_test`, `expand_epic`

Must build before use: `cd mcp-task-manager && npm run build`

## Configuration

**Priority**: Web UI settings > Config file (`.yokeflow.yaml`) > Defaults

**Key settings**:
- `models.initializer` / `models.coding` - Override default Opus/Sonnet models
- `timing.auto_continue_delay` - Seconds between sessions (default 3)
- `project.max_iterations` - Limit session count (null = unlimited)
- `brownfield.default_feature_branch_prefix` - Branch prefix (default: `yokeflow/`)
- `brownfield.run_existing_tests_before_changes` / `after_changes` - Regression safety (default: true)

## REST API

**Endpoints**: 60+ RESTful endpoints for complete platform control

**Key endpoints**:
- Health: `/health`, `/health/detailed` - System health monitoring
- Sessions: `/api/sessions/{id}/logs` - Session management
- Tasks: `/api/tasks/{id}`, `/api/tasks/{id}/status` - Task management
- Epics: `/api/epics/{id}/progress` - Epic tracking
- Quality: `/api/sessions/{id}/quality-review`, `/api/projects/{id}/quality-metrics`
- Brownfield: `/api/projects/import`, `/api/projects/{id}/rollback` - Import & rollback

**Documentation**: Interactive docs at `/docs` (Swagger UI) when API server running

See [docs/api-usage.md](docs/api-usage.md) for complete endpoint reference and examples.

## Security

**Blocklist approach**: Allows dev tools (npm, git, curl), blocks dangerous commands (rm, sudo, apt)

Edit `server/utils/security.py` `BLOCKED_COMMANDS` to modify.

## Project Structure

```
yokeflow2/
├── server/                  # All server code
│   ├── agent/               # Session orchestration & lifecycle
│   │   ├── agent.py         # Agent loop and session logic
│   │   ├── orchestrator.py  # Session lifecycle
│   │   ├── codebase_import.py  # Codebase import & analysis (brownfield)
│   │   ├── checkpoint.py    # Session checkpointing and recovery
│   │   └── models.py        # Orchestrator data models
│   ├── api/                 # REST API & WebSocket
│   │   ├── app.py           # Main FastAPI application
│   │   ├── auth.py          # API authentication
│   │   ├── validation.py    # Pydantic validation models
│   │   ├── start.py         # API startup wrapper
│   │   └── routes/          # API route modules
│   ├── database/            # Database layer
│   │   ├── operations.py    # PostgreSQL operations (async)
│   │   ├── connection.py    # Connection pooling
│   │   └── retry.py         # Retry logic with exponential backoff
│   ├── client/              # External service clients
│   │   ├── claude.py        # Claude SDK client
│   │   └── prompts.py       # Prompt loading
│   ├── quality/             # Quality & review system
│   │   ├── reviews.py       # Deep reviews
│   │   ├── integration.py   # Quality integration
│   │   ├── spec_parser.py   # Specification parser
│   │   └── prompt_analyzer.py  # Prompt improvements
│   ├── generation/          # Spec generation
│   ├── coverage/            # Test coverage analysis
│   └── utils/               # Shared utilities
│       ├── config.py        # Configuration management
│       ├── logging.py       # Structured logging
│       ├── errors.py        # Error hierarchy
│       ├── security.py      # Blocklist validation
│       ├── observability.py # Session logging
│       └── reset.py         # Project reset logic
├── web-ui/                  # Next.js Web UI
├── mcp-task-manager/        # MCP server (TypeScript)
├── scripts/                 # Utility scripts
├── prompts/                 # Agent instructions
├── schema/postgresql/       # Database DDL
├── tests/                   # Test suites
├── docs/                    # Documentation
└── projects/                # Project output directories
```

## Key Design Decisions

**PostgreSQL**: Production-ready, async operations, JSONB metadata, UUID-based IDs

**Orchestrator**: Decouples session management, enables API control, foundation for job queues

**MCP over Shell**: Protocol-based, structured I/O, no injection risks, language-agnostic

**Tasks Upfront**: Complete visibility from day 1, accurate progress tracking, user can review roadmap

**Dual Models**: Opus for planning (comprehensive), Sonnet for coding (fast + cheap)

**Blocklist Security**: Agent autonomy with safety

**Brownfield as Copy**: Imported codebases are copied to `projects/`, keeping originals safe. Feature branches isolate changes.

## Troubleshooting

**MCP server failed**: Run `cd mcp-task-manager && npm run build`

**Database error**: Ensure PostgreSQL running (`docker compose up -d`), check DATABASE_URL in `.env`

**Command blocked**: Check `server/utils/security.py` BLOCKED_COMMANDS list

**Agent stuck**: Check logs in `projects/[project]/yokeflow/logs/`, run with `--verbose`

**Web UI no projects**: Ensure PostgreSQL running, verify API connection

**Import errors**: All server imports use the `server.` prefix (e.g., `from server.agent.agent import ...`)

## Testing

**173 unit tests**, all passing, ~1 second runtime. No mocks or external dependencies.

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=server --cov-report=html --cov-report=term-missing

# Using the helper script
python scripts/test_quick.py
```

See [docs/testing-guide.md](docs/testing-guide.md) and [tests/README.md](tests/README.md) for details.

## Important Files

**Agent Core**:
- `server/agent/orchestrator.py` - Session lifecycle (greenfield + brownfield)
- `server/agent/codebase_import.py` - Codebase import & analysis (brownfield)
- `server/agent/agent.py` - Agent loop

**Database**:
- `server/database/operations.py` - PostgreSQL operations
- `server/database/retry.py` - Retry logic

**API**:
- `server/api/app.py` - FastAPI application (60+ endpoints)
- `server/api/validation.py` - Pydantic validation models
- `web-ui/src/lib/api.ts` - Frontend API client

**Utilities**:
- `server/utils/config.py` - Configuration
- `server/utils/logging.py` - Structured logging
- `server/utils/security.py` - Security validation

**Quality System**:
- `server/quality/reviews.py` - Deep reviews (AI-powered)
- `server/quality/prompt_analyzer.py` - Prompt improvements
- `web-ui/src/components/QualityDashboard.tsx` - UI dashboard

**Other Key Files**:
- `mcp-task-manager/src/index.ts` - MCP server
- `schema/postgresql/schema.sql` - Database schema
- `prompts/` - Agent instruction templates
- `docs/` - Documentation

## Logging & Observability

**Structured Logging**:
- **Terminal**: Development-friendly colored output
- **File**: `logs/yokeflow.log` - JSON format for analysis
- **Per-Session**: `projects/<project>/yokeflow/logs/session_*.jsonl` - Session details

**Configuration** (via environment variables):
```bash
export LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR, CRITICAL
export LOG_FORMAT=dev           # 'dev' (colored) or 'json' (production)
```

**Log Locations**:
- Application logs: `logs/yokeflow.log` (JSON format)
- Session logs: `projects/<project>/yokeflow/logs/session_NNN_TIMESTAMP.jsonl`
- Session summaries: `projects/<project>/yokeflow/logs/session_NNN_TIMESTAMP.txt`

**Features**:
- Automatic session_id and project_id context injection
- Performance logging for slow operations
- Exception tracking with stack traces
- Ready for ELK/Datadog/CloudWatch integration

## Production Hardening

### Database Retry Logic
**File**: `server/database/retry.py`
- Exponential backoff with configurable jitter
- 20+ PostgreSQL error codes covered
- Applied to all database operations in `server/database/operations.py`

### Session Checkpointing
**File**: `server/agent/checkpoint.py`
- Complete session state preservation at key points
- Full conversation history capture for resume
- Tables: `session_checkpoints`; Views: `v_resumable_checkpoints`
- Functions: `create_checkpoint()`, `invalidate_checkpoints()`, `get_latest_resumable_checkpoint()`

## Philosophy

**Greenfield + Brownfield Development**: Builds new applications from scratch OR modifies existing codebases.

**Greenfield Workflow**: Create `app_spec.txt` → Initialize roadmap → Review → Autonomous coding → Completion verification

**Brownfield Workflow**: Import codebase → Analyze → Write `change_spec.md` → Scoped roadmap → Modify on feature branch → Verify

**Core Principle**: One-shot success. Improve the agent system itself rather than fixing generated apps.

See `IMPROVEMENT-IDEAS.md` for potential future enhancements.

---

**For detailed documentation, see `docs/` directory.**
