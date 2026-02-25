# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## What This Is

**YokeFlow 2** - An autonomous AI development platform that uses Claude to build complete applications over multiple sessions.

**Status**: Production Ready - v2.4.0 (February 2026)

**Architecture**: API-first platform with FastAPI + Next.js Web UI + PostgreSQL + MCP task management

**Workflow**: Opus creates roadmap (Session 0: epics + tasks + tests) → Sonnet implements features (Sessions 1+)

**Latest Updates** (February 2026):
- ✅ **Simplified Initialization**: Single-agent initializer creates epics, tasks, and tests with parallel MCP tool calls
- ✅ **MCP Pre-flight Check**: Auto-rebuilds stale MCP server, validates before sessions start
- ✅ **Brownfield Support**: Import existing codebases from local paths or GitHub, analyze, and modify (43 tests)
- ✅ **REST API Complete**: 60+ endpoints with comprehensive validation
- ✅ **Quality System**: 8-phase quality system with test tracking and epic re-testing
- ✅ **Production Hardening**: Database retry logic, intervention system, session checkpointing
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
- `server/agent/session_manager.py` - Intervention system with DB persistence (15 tests)
- `server/utils/logging.py` - Structured logging with JSON/dev formatters (19 tests)
- `server/utils/errors.py` - Error hierarchy with 30+ error types (36 tests)
- `server/api/app.py` - REST API + WebSocket
- `server/utils/observability.py` - Session logging (JSONL + TXT)
- `server/utils/security.py` - Blocklist validation
- `prompts/` - Agent instructions


## Database

**Schema**: PostgreSQL with 3-tier hierarchy: `epics` → `tasks` → `tests`

**Key tables**:
- Core: `projects` (with `project_type`, `codebase_analysis` for brownfield), `epics`, `tasks`, `tests`, `sessions`, `session_quality_checks`
- ✅ **Production Hardening**: `paused_sessions`, `intervention_actions`, `session_checkpoints` (011-012)
- ✅ **Verification System**: `task_verifications`, `epic_validations`, `generated_tests` (013-016)

**Key views**:
- Core: `v_next_task`, `v_progress`, `v_epic_progress`
- Production: `v_active_interventions`, `v_latest_checkpoints`, `v_resumable_checkpoints`
- Verification: `v_latest_task_verifications`, `v_verification_statistics`

**Access**: Use `server/database/operations.py` abstraction (async/await). See `schema/postgresql/` for DDL.

**Retry Logic**: All database operations automatically retry on transient failures (exponential backoff)

## MCP Tools

The `mcp-task-manager/` provides 15+ tools (prefix: `mcp__task-manager__`):

**Query**: `task_status`, `get_next_task`, `list_epics`, `get_epic`, `list_tasks`, `get_task`, `list_tests`

**Update**: `update_task_status`, `start_task`, `update_test_result`

**Create**: `create_epic`, `create_task`, `create_test`, `expand_epic`, `log_session`

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
- Sessions: `/api/sessions/{id}/logs`, `/api/sessions/{id}/pause`, `/api/sessions/{id}/resume`
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
│   │   ├── session_manager.py  # Intervention system (DB persistence)
│   │   ├── checkpoint.py    # Session checkpointing and recovery
│   │   ├── intervention.py  # Blocker detection and retry tracking
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
│   │   ├── metrics.py       # Quality metrics (Phase 1)
│   │   ├── reviews.py       # Deep reviews (Phase 2)
│   │   ├── gates.py         # Quality gates
│   │   ├── integration.py   # Quality integration
│   │   └── prompt_analyzer.py  # Prompt improvements (Phase 4)
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
pytest tests/test_parallel_orchestrator.py   # Parallel orchestrator (varies)
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
- `server/agent/session_manager.py` - Session management

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
- Phase 1: `server/quality/metrics.py` - Quick checks (zero-cost) ✅
- Phase 2: `server/quality/reviews.py` - Deep reviews (AI-powered) ✅
- Phase 3: `web-ui/src/components/QualityDashboard.tsx` - UI dashboard ✅
- Phase 4: `server/quality/prompt_analyzer.py` - Prompt improvements ✅

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

**✅ P0 Critical Improvements Complete (v1.3.0)**

All three critical gaps have been addressed with production-ready implementations:

### 1. Database Retry Logic ✅
**File**: `server/database/retry.py` (350+ lines, 30 tests)
- Exponential backoff with configurable jitter
- 20+ PostgreSQL error codes covered
- Transient error detection (connection failures, deadlocks, resource exhaustion)
- Retry statistics tracking for observability
- Applied to all database operations in `server/database/operations.py`

**Usage**:
```python
from server.database.retry import with_retry, RetryConfig

@with_retry(RetryConfig(max_retries=5, base_delay=2.0))
async def my_database_operation():
    async with db.acquire() as conn:
        return await conn.fetchval("SELECT 1")
```

### 2. Intervention System ✅
**Files**: `server/agent/session_manager.py`, `server/database/operations.py` (9 new methods, 15 tests)
- Full database persistence for paused sessions
- Intervention action tracking and audit trail
- Pause/resume session operations
- Integration with existing `server/agent/intervention.py` blocker detection
- Web UI ready (`web-ui/src/components/InterventionDashboard.tsx`)

**Database**: `schema/postgresql/011_paused_sessions.sql`
- Tables: `paused_sessions`, `intervention_actions`, `notification_preferences`
- Views: `v_active_interventions`, `v_intervention_history`
- Functions: `pause_session()`, `resume_session()`

### 3. Session Checkpointing ✅
**Files**: `server/agent/checkpoint.py` (420+ lines, 19 tests), `server/database/operations.py` (9 new methods)
- Complete session state preservation at key points
- Full conversation history capture for resume
- State validation before resumption
- Recovery attempt tracking
- Context-aware resume prompt generation

**Database**: `schema/postgresql/012_session_checkpoints.sql`
- Tables: `session_checkpoints`, `checkpoint_recoveries`
- Views: `v_latest_checkpoints`, `v_resumable_checkpoints`, `v_checkpoint_recovery_history`
- Functions: `create_checkpoint()`, `start_checkpoint_recovery()`, `complete_checkpoint_recovery()`

**Usage**:
```python
from server.agent.checkpoint import CheckpointManager

manager = CheckpointManager(session_id, project_id)

# Create checkpoint after task completion
checkpoint_id = await manager.create_checkpoint(
    checkpoint_type="task_completion",
    conversation_history=messages,
    current_task_id=task.id,
    completed_tasks=completed_task_ids
)

# Resume from checkpoint after failure
from server.agent.checkpoint import CheckpointRecoveryManager

recovery = CheckpointRecoveryManager()
state = await recovery.restore_from_checkpoint(checkpoint_id)
# Continue with restored conversation_history, task state, etc.
```

---

## Recent Changes

**February 19, 2026 - v2.4.0 Simplified Initialization & Local-Only Mode**:
- ✅ **Simplified Initialization**: Removed parallel expansion workers; single initializer agent creates epics, tasks, and tests using parallel MCP tool calls
- ✅ **Local-Only Mode**: Removed Docker sandbox infrastructure; all sessions run locally
- ✅ **MCP Pre-flight Check**: Validates build exists, detects stale builds, auto-rebuilds, syntax checks
- ✅ **Improved Coding Prompt**: Stronger browser testing minimums, removed stale Docker references
- ✅ **Quality System Fixes**: Review system updated for local-only mode

**February 11, 2026 - v2.2.0 Brownfield Support**:
- ✅ **Codebase Import**: Import from local paths or GitHub URLs (public + private repos)
- ✅ **Codebase Analysis**: Detects languages, frameworks, test systems, CI, patterns (670-line module)
- ✅ **Brownfield Prompts**: Dedicated initializer (scoped epics) and coding preamble (regression safety)
- ✅ **Orchestrator**: `create_brownfield_project()` and `rollback_brownfield_changes()` methods
- ✅ **API**: `POST /api/projects/import` and `POST /api/projects/{id}/rollback` endpoints
- ✅ **Validation**: `ImportProjectRequest` Pydantic model with 14 tests
- ✅ **Web UI**: "Import Codebase" mode on create page (GitHub URL or local path)
- ✅ **Database**: `project_type`, `source_commit_sha`, `codebase_analysis` columns
- ✅ **Configuration**: `BrownfieldConfig` with feature branch prefix and test safety settings
- ✅ **Tests**: 43 new tests (import: 19, orchestrator: 10, validation: 14)

**January 31 - February 2, 2026 - Quality System Completion**:
- ✅ **Phase 0**: Database cleanup - Removed 34 unused objects (16 tables + 18 views)
- ✅ **Phase 1**: Test execution tracking - Error details, retry counts, performance indexes
- ✅ **Phase 2**: Epic test failure tracking - 22-field history table, 5 analysis views, flaky test detection
- ✅ **Phase 3**: Epic test blocking - Strict/autonomous modes, orchestrator integration, 5 passing tests
- ✅ **Phase 4.1**: Test viewer UI - Epic/task tests visible with requirements
- ✅ **Phase 5**: Epic re-testing - Smart selection, regression detection, stability scoring (3 MCP tools)
- ✅ **Phase 6**: Enhanced review triggers - 7 quality-based conditions (removed periodic trigger)
- ✅ **Phase 7**: Project completion review - Spec parser, requirement matcher, Claude review, Web UI dashboard
- ✅ **Phase 8 (60%)**: Prompt improvement aggregation - Recommendation extraction and proposal generation
- ✅ **Total**: 7 database migrations, 13 new files for Phase 7, ~2,500 lines of new code

**January 8-9, 2026 - v2.0.0 Feature Completion**:
- ✅ **REST API Complete**: 17 endpoints implemented with comprehensive validation
- ✅ **Input Validation Framework**: Pydantic models with 52 tests (100% passing)
- ✅ **Verification System Tested**: 40 tests added for task/epic validation
- ✅ **Documentation Updates**: 11 docs updated, verification-system.md created (850+ lines)
- ✅ **Database Schema**: Migrations 013-016 for verification system
- ✅ **Test Suite**: ~212 total tests, 72 core tests passing, 70% coverage achieved

**January 7, 2026 - v2.0.0 Architecture Reorganization**:
- ✅ **Complete folder reorganization**: All server code moved to `server/`
- ✅ **44 Python files** reorganized into 11 clean modules
- ✅ **61 files updated** with new import paths
- ✅ **No circular dependencies**: Clear module boundaries established
- ✅ **Git history preserved**: Used git mv for all tracked files

**January 5, 2026 - v1.4.0 Production Hardening**:
- ✅ Database retry logic with exponential backoff (30 tests)
- ✅ Complete intervention system with database persistence (15 tests)
- ✅ Session checkpointing and recovery system (19 tests)
- ✅ Structured logging with JSON/dev formatters (19 tests)
- ✅ Error hierarchy with 30+ error types (36 tests)
- ✅ 119 new tests (100% pass rate)

**December 29, 2025 - v1.2.0 Release**:
- ✅ **Browser Automation**: Full browser testing with agent-browser
- ✅ **Visual Verification**: Screenshots and page snapshots for testing web applications
- ✅ **Codebase Cleanup**: Removed experimental files from browser automation development

**December 27, 2025 - v1.1.0 Release**:
- ✅ **Version 1.1.0**: Database schema improvements, migration scripts removed
- ✅ **Fresh Install Required**: Schema changes require clean database installation
- ✅ **Migration Scripts Removed**: All migration-related scripts and directories cleaned up
- ⚠️ **Breaking Change**: Existing v1.0.0 databases cannot be migrated - fresh install required

**December 24, 2025**:
- ✅ **Prompt Improvements Restored**: Phase 4 of Review System re-enabled in feature branch
- ✅ **Backend Components**: Restored `prompt_improvement_analyzer.py` and API routes
- ✅ **Web UI Pages**: Restored `/prompt-improvements` dashboard and detail views
- ✅ **Integration Complete**: Connected with existing Review System (Phases 1-3)

**December 2025**:
- ✅ Review system Phases 1-3 complete (quick checks, deep reviews, UI dashboard)
- ✅ Prompt Improvement System (Phase 4) - Archived for post-release refactoring
- ✅ PostgreSQL migration complete (UUID-based, async, connection pooling)
- ✅ API-first platform with Next.js Web UI
- ✅ Project completion tracking with celebration UI
- ✅ Coding prompt improvements (browser verification enforcement)
- 🚀 **YokeFlow Transition**: Rebranding and repository migration in progress
- ✅ **Code Organization**: Refactored to `core/` and `review/` modules for better structure
- ✅ **Pre-Release Cleanup**: Experimental features archived, TODO split into pre/post-release

**Key Evolution**:
- Shell scripts → MCP (protocol-based task management)
- JSONL + TXT dual logging (human + machine readable)
- Autonomous Coding → **YokeFlow** (production-ready platform)

## Philosophy

**Greenfield + Brownfield Development**: Builds new applications from scratch OR modifies existing codebases.

**Greenfield Workflow**: Create `app_spec.txt` → Initialize roadmap → Review → Autonomous coding → Completion verification

**Brownfield Workflow**: Import codebase → Analyze → Write `change_spec.md` → Scoped roadmap → Modify on feature branch → Verify

**Core Principle**: One-shot success. Improve the agent system itself rather than fixing generated apps.

## Release Status

**Current State**: Production Ready - v2.4.0

**v2.4 Release Highlights**:
- ✅ **Simplified Initialization**: Single-agent initializer with parallel MCP tool calls (replaces multi-worker expansion)
- ✅ **Local-Only Mode**: Removed Docker sandbox; all sessions run locally
- ✅ **MCP Pre-flight Check**: Auto-rebuilds stale MCP server, validates before sessions

**Previous Releases**:
- v2.3: Parallel expansion (removed in v2.4 in favor of simpler single-agent approach)
- v2.2: Brownfield support (import/modify existing codebases, 43 tests)
- v2.1: Quality system (8 phases), 60+ API endpoints, 20+ MCP tools
- v2.0: REST API, verification system, production hardening, clean architecture

**Post-Release Roadmap**:
- See `YOKEFLOW_FUTURE_PLAN.md` for planned enhancements
- GitHub push/PR automation, non-UI project support, E2B integration, and more

---

**For detailed documentation, see `docs/` directory. Originally forked from Anthropic's autonomous coding demo, now evolved into YokeFlow with extensive enhancements.**
