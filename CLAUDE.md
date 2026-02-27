# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## What This Is

**YokeFlow 2** - An autonomous AI development platform that uses Claude to build complete applications over multiple sessions.

**Status**: Production Ready - v2.5.0 (February 2026)

**Architecture**: API-first platform with FastAPI + Next.js Web UI + PostgreSQL + MCP task management

**Workflow**: Opus creates roadmap (Session 0: epics + tasks + tests) → Sonnet implements features (Sessions 1+)

**Latest Updates** (February 2026):
- ✅ **Simplified Initialization**: Single-agent initializer creates epics, tasks, and tests with parallel MCP tool calls
- ✅ **MCP Pre-flight Check**: Auto-rebuilds stale MCP server, validates before sessions start
- ✅ **Brownfield Support**: Import existing codebases from local paths or GitHub, analyze, and modify (43 tests)
- ✅ **REST API Complete**: 60+ endpoints with comprehensive validation
- ✅ **Quality System**: Quality system with test tracking and epic re-testing
- ✅ **Production Hardening**: Database retry logic, session checkpointing
- 🚀 **Clean Architecture**: No circular dependencies, clear module boundaries

## Core Workflow

**Greenfield Session 0**: Reads spec from `yokeflow/specs/` → Creates epics, tasks, and tests in PostgreSQL → Runs `init.sh`

**Brownfield Session 0**: Explores imported codebase → Reads `yokeflow/specs/change_spec.md` → Creates scoped epics, tasks, and tests

**Sessions 1+ (Coding)**: Get next task → Implement → Browser verify (with agent-browser) → Update database → Git commit → Auto-continue

**Key Files**:
- `server/agent/orchestrator.py` - Session lifecycle (greenfield + brownfield)
- `server/agent/codebase_import.py` - Codebase import and analysis (brownfield)
- `server/agent/agent.py` - Agent loop and session logic
- `server/database/operations.py` - PostgreSQL abstraction (async) + retry logic
- `server/database/retry.py` - Retry logic with exponential backoff (30 tests)
- `server/client/claude.py` - Claude SDK client + MCP pre-flight check/auto-rebuild
- `server/agent/checkpoint.py` - Session checkpointing and recovery (19 tests)
- `server/utils/logging.py` - Structured logging with JSON/dev formatters (19 tests)
- `server/utils/errors.py` - Error hierarchy with 30+ error types (36 tests)
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

The `mcp-task-manager/` provides 15+ tools (prefix: `mcp__task-manager__`):

**Query**: `task_status`, `get_next_task`, `list_epics`, `get_epic`, `list_tasks`, `get_task`, `list_tests`

**Update**: `update_task_status`, `start_task`, `update_test_result`

**Create**: `create_epic`, `create_task`, `create_test`, `expand_epic`

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

## Input Validation

**Framework**: Pydantic-based validation with 20 models and 66 tests (100% passing)

**What's validated**:
- API requests: Project names, spec content, session parameters, environment variables
- Brownfield imports: Source URLs, local paths, change spec content
- Configuration: Model names, timing settings, database URLs
- Verification: Test timeouts, coverage thresholds, webhook URLs

**Benefits**:
- Type safety with runtime validation
- Clear error messages for invalid inputs
- Sensible defaults for configuration
- Automatic OpenAPI schema generation

See [docs/input-validation.md](docs/input-validation.md) for usage examples.

## Security

**Blocklist approach**: Allows dev tools (npm, git, curl), blocks dangerous commands (rm, sudo, apt)

Edit `server/utils/security.py` `BLOCKED_COMMANDS` to modify.

## Project Structure

```
yokeflow2/
├── server/                  # All server code (reorganized)
│   ├── agent/               # Session orchestration & lifecycle
│   │   ├── agent.py         # Agent loop and session logic
│   │   ├── orchestrator.py  # Session lifecycle
│   │   ├── codebase_import.py  # Codebase import & analysis (brownfield)
│   │   ├── checkpoint.py    # Session checkpointing and recovery
│   │   └── models.py        # Orchestrator data models
│   ├── api/                 # REST API & WebSocket
│   │   ├── app.py           # Main FastAPI application
│   │   ├── auth.py          # API authentication
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
│   │   ├── metrics.py       # Quality metrics
│   │   ├── reviews.py       # Deep reviews
│   │   ├── integration.py   # Quality integration
│   │   └── prompt_analyzer.py  # Prompt improvements
│   ├── verification/        # Testing & validation
│   │   ├── task_verifier.py  # Task verification
│   │   ├── epic_validator.py  # Epic validation
│   │   ├── epic_manager.py  # Epic management
│   │   └── test_generator.py  # Test generation
│   ├── utils/               # Shared utilities
│   │   ├── config.py        # Configuration management
│   │   ├── logging.py       # Structured logging
│   │   ├── errors.py        # Error hierarchy
│   │   ├── security.py      # Blocklist validation
│   │   ├── observability.py # Session logging
│   │   └── reset.py         # Project reset logic
│   └── coverage/            # Test coverage
│       └── analyzer.py      # Coverage analysis
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

**Database error**: Ensure PostgreSQL running (`docker-compose up -d`), check DATABASE_URL in `.env`

**Command blocked**: Check `server/utils/security.py` BLOCKED_COMMANDS list

**Agent stuck**: Check logs in `projects/[project]/yokeflow/logs/`, run with `--verbose`

**Web UI no projects**: Ensure PostgreSQL running, verify API connection

**Import errors**: Update imports to new structure:
```python
# Old: from core.agent import
# New: from server.agent.agent import

# Old: from api.main import
# New: from server.api.app import

# Old: from review.review_client import
# New: from server.quality.reviews import
```

## Testing

**Test Suite Status** (February 2026):
- ✅ **450+ total tests** across all test files (13 MCP pre-flight, 43 brownfield), 10 skipped
- ✅ **70% coverage achieved** (target met)
- ✅ **Production ready** with comprehensive test infrastructure

**Quick Start**:
```bash
# Run fast tests (recommended for development)
python scripts/test_quick.py

# Or use pytest directly
pytest -m "not slow"

# Run with coverage
pytest --cov=server --cov-report=html --cov-report=term-missing
```

**Key Test Files**:
```bash
pytest tests/test_orchestrator.py            # Session lifecycle (17 tests)
pytest tests/test_mcp_preflight.py           # MCP pre-flight check (13 tests)
pytest tests/test_codebase_import.py         # Brownfield import & analysis (19 tests)
pytest tests/test_brownfield_orchestrator.py # Brownfield orchestration (10 tests)
pytest tests/test_brownfield_validation.py   # Brownfield validation (14 tests)
pytest tests/test_quality_integration.py     # Quality system (10 tests)
pytest tests/test_security.py               # Security validation (2 tests, 64 assertions)
pytest tests/test_task_verifier.py           # Task verification (11 tests)
pytest tests/test_test_generator.py          # Test generation (15 tests)
```

**Documentation**:
- [docs/testing-guide.md](docs/testing-guide.md) - Comprehensive developer guide
- [tests/README.md](tests/README.md) - Test descriptions and status

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
- `server/api/validation.py` - Pydantic validation models (20 models, 66 tests)
- `web-ui/src/lib/api.ts` - Frontend API client

**Verification**:
- `server/verification/task_verifier.py` - Task verification (11 tests)
- `server/verification/test_generator.py` - Test generation (15 tests)
- `server/verification/epic_validator.py` - Epic validation (14 tests)

**Utilities**:
- `server/utils/config.py` - Configuration
- `server/utils/logging.py` - Structured logging
- `server/utils/security.py` - Security validation

**Quality System**:
- `server/quality/metrics.py` - Quick checks (zero-cost) ✅
- `server/quality/reviews.py` - Deep reviews (AI-powered) ✅
- `web-ui/src/components/QualityDashboard.tsx` - UI dashboard ✅
- `server/quality/prompt_analyzer.py` - Prompt improvements ✅

**Other Key Files**:
- `mcp-task-manager/src/index.ts` - MCP server
- `schema/postgresql/schema.sql` - Database schema
- `prompts/` - Agent instruction templates
- `docs/` - Documentation

## Logging & Observability

**Structured Logging** (v1.4.0):
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

## Production Hardening (January 2026)

### Database Retry Logic
**File**: `server/database/retry.py` (350+ lines, 30 tests)
- Exponential backoff with configurable jitter
- 20+ PostgreSQL error codes covered
- Applied to all database operations in `server/database/operations.py`

### Session Checkpointing
**File**: `server/agent/checkpoint.py` (420+ lines, 19 tests)
- Complete session state preservation at key points
- Full conversation history capture for resume
- Tables: `session_checkpoints`; Views: `v_resumable_checkpoints`
- Functions: `create_checkpoint()`, `invalidate_checkpoints()`, `get_latest_resumable_checkpoint()`

### Intervention System (Archived)
The intervention/pause system was implemented but never used in production. Code is preserved in `archive/intervention/` for future reference.

---

## Version History

- **v2.5.0** (Feb 2026): Codebase cleanup — removed unused DB columns/views/functions, archived intervention system, removed parallel orchestrator
- **v2.4.0** (Feb 2026): Simplified initialization (single agent with parallel MCP calls), local-only mode (removed Docker sandbox), MCP pre-flight check
- **v2.2.0** (Feb 2026): Brownfield support — import existing codebases from local paths or GitHub (43 tests)
- **v2.1.0** (Feb 2026): Quality system completion — project completion reviews, prompt improvements
- **v2.0.0** (Jan 2026): Architecture reorganization, REST API (60+ endpoints), verification system, production hardening
- **v1.x** (Dec 2025): Browser automation, PostgreSQL migration, structured logging, error hierarchy

## Philosophy

**Greenfield + Brownfield Development**: Builds new applications from scratch OR modifies existing codebases.

**Greenfield Workflow**: Create `app_spec.txt` → Initialize roadmap → Review → Autonomous coding → Completion verification

**Brownfield Workflow**: Import codebase → Analyze → Write `change_spec.md` → Scoped roadmap → Modify on feature branch → Verify

**Core Principle**: One-shot success. Improve the agent system itself rather than fixing generated apps.

## Release Status

**Current State**: Production Ready - v2.5.0

See `IMPROVEMENT-IDEAS.md` for potential future enhancements.

---

**For detailed documentation, see `docs/` directory. Originally forked from Anthropic's autonomous coding demo, now evolved into YokeFlow with extensive enhancements.**
