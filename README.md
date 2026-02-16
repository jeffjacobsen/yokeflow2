# YokeFlow 2 - Autonomous AI Development Platform

Build complete applications using Claude across multiple autonomous sessions.

## Overview

YokeFlow 2 is an autonomous coding platform that uses Claude to build applications from specifications.

**Status**: Production Ready - v2.3.0 (February 2026) ✅

**Core Features:**
- ✅ **Parallel expansion** - Up to 4 workers expand epics concurrently (~4x faster initialization) ⭐ NEW v2.3
- ✅ **MCP pre-flight check** - Auto-detects stale builds, rebuilds before sessions start ⭐ NEW v2.3
- ✅ **Brownfield support** - Import existing codebases, analyze, and modify on feature branches
- ✅ **Autonomous multi-session development** - Opus plans, Sonnet implements
- ✅ **REST API (60+ endpoints)** - Complete control with comprehensive validation
- ✅ **Input validation framework** - 20 Pydantic models with 66 tests
- ✅ **Verification system** - Automated test generation & epic validation
- ✅ **Quality system (6 phases + 2 partial)** - Test tracking, epic re-testing, prompt improvements
- ✅ **Web UI** - Real-time monitoring with Next.js + TypeScript
- ✅ **PostgreSQL database** - Async operations with retry logic (21 tables, 19 views)
- ✅ **Docker sandbox** - Secure execution with Playwright browser automation
- ✅ **MCP Integration (20+ tools)** - Enhanced task management with quality tools
- ✅ **Production hardening** - Session checkpointing, intervention system, database retry logic
- ✅ **Enterprise ready** - 70% test coverage (533+ tests), structured logging, error hierarchy

## What's New in v2.3 (February 2026)

**Parallel Expansion** — initialize projects ~4x faster:

- **Parallel workers**: After Session 0 creates epics, up to 4 concurrent workers expand them into tasks and tests
- **Auto-scaling**: Worker count auto-scales based on epic count (~6 epics/worker)
- **Advisory lock concurrency**: PostgreSQL `pg_advisory_xact_lock` prevents duplicate session races
- **MCP pre-flight check**: Validates MCP server build exists, detects stale builds, auto-rebuilds
- **Real-time UI**: WebSocket events for expansion progress, live session tracking
- **Expansion session labels**: "Expansion Worker N" in History, Logs, and Current Session views
- **59 new tests**: 46 parallel expansion + 13 MCP pre-flight (533 total)

**Key Files:**
- `server/agent/orchestrator.py` - Parallel expansion in `_run_parallel_expansion()` and `_run_expansion_worker()`
- `server/database/operations.py` - `create_expansion_session()` with advisory lock
- `server/client/claude.py` - `verify_mcp_server()` pre-flight check
- `prompts/expansion_prompt.md` - Expansion worker prompt

**Configuration** (`.yokeflow.yaml`):
```yaml
parallel:
  parallel_expansion: true    # Enable/disable (default: true)
  max_expansion_workers: 4    # Max concurrent workers (default: 4)
```

## What's New in v2.2 (February 2026)

**Brownfield Support** — import and modify existing codebases:

- **Codebase import**: Clone from GitHub (public + private) or copy from local paths
- **Intelligent analysis**: Auto-detects 20+ languages, 15+ frameworks, test systems, CI platforms
- **Scoped roadmaps**: Brownfield initializer creates epics/tasks only for requested changes
- **Regression safety**: Coding preamble enforces understanding before modifying, existing test runs
- **Feature branches**: All modifications on `yokeflow/` branches with one-click rollback
- **Full Web UI**: "Import Codebase" mode on project creation page
- **43 new tests**: Comprehensive coverage for import, orchestration, and validation

See [YOKEFLOW_FUTURE_PLAN.md](YOKEFLOW_FUTURE_PLAN.md) for remaining roadmap (GitHub push/PR automation, non-UI project support).

## What's New in v2.1 (February 2026)

**Comprehensive Quality System** implemented across 8 phases:

- **Phase 1-2**: Test execution tracking - Error messages, execution time, retry counts, flaky test detection
- **Phase 3**: Epic test blocking - Strict/autonomous modes, critical epic patterns
- **Phase 5**: Epic re-testing - Smart selection, regression detection (catches breaks within 2 epics), stability scoring
- **Phase 6**: Enhanced review triggers - 7 quality-based conditions (removed periodic trigger)
- **Phase 7** (⚠️ disabled): Project completion review - Implemented but needs enhancement (see [YOKEFLOW_FUTURE_PLAN.md](YOKEFLOW_FUTURE_PLAN.md))
- **Phase 8** (partial): Prompt improvement aggregation - Recommendation extraction (60% complete)

See [QUALITY_SYSTEM_SUMMARY.md](QUALITY_SYSTEM_SUMMARY.md) for complete implementation details.

## Getting Started

See [QUICKSTART.md](QUICKSTART.md) for setup instructions.

## Requirements

- Node.js 20+
- Python 3.9+
- Docker
- PostgreSQL (via Docker)


## How It Works

**Greenfield** (new projects):
1. **Session 0 (Planning)**: Reads `app_spec.txt` → Creates epics in database → Runs `init.sh`
2. **Parallel Expansion**: Up to 4 workers expand epics into tasks and tests concurrently
3. **Sessions 1+ (Coding)**: Gets next task → Implements → Tests → Commits → Auto-continues

**Brownfield** (existing codebases):
1. **Import**: Clone from GitHub or copy from local path → Analyze codebase → Create feature branch
2. **Session 0 (Planning)**: Explores existing code → Reads `change_spec.md` → Creates scoped epics
3. **Parallel Expansion**: Workers expand epics into modification tasks with regression tests
4. **Sessions 1+ (Coding)**: Gets next task → Modifies existing code → Regression tests → Commits

The system uses a hierarchical task structure:
- Epics (high-level features)
- Tasks (specific implementations)
- Tests (validation criteria)

## Configuration

Configure via `.yokeflow.yaml`:

```yaml
models:
  initializer: claude-opus-4-5-20251101
  coding: claude-sonnet-4-5-20250929
  review: claude-sonnet-4-5-20250929           # ⭐ NEW v2.1
  prompt_improvement: claude-opus-4-5-20251101 # ⭐ NEW v2.1

timing:
  auto_continue_delay: 3

# ⭐ NEW v2.3: Parallel Expansion
parallel:
  parallel_expansion: true    # Enable parallel epic expansion (default: true)
  max_expansion_workers: 4    # Max concurrent workers (default: 4, auto-scales)

# ⭐ NEW v2.1: Epic Testing Configuration
epic_testing:
  mode: autonomous  # or "strict"
  critical_epics:
    - Authentication
    - Payment

# ⭐ NEW v2.1: Epic Re-testing Configuration
epic_retesting:
  enabled: true
  trigger_frequency: 2  # Re-test every 2 completed epics

docker:
  enabled: true
```

Environment variables in `.env`:
```bash
CLAUDE_CODE_OAUTH_TOKEN=your_token_here
DATABASE_URL=postgresql://agent:agent_dev_password@localhost:5432/yokeflow
```

## Architecture

YokeFlow 2 uses a clean, modular architecture with all server code under `server/`:

```
server/
├── agent/               # Session orchestration & lifecycle
│   ├── orchestrator.py  # Session lifecycle + parallel expansion
│   ├── codebase_import.py  # Codebase import & analysis ⭐ v2.2
│   ├── agent.py         # Agent loop and session logic
│   ├── session_manager.py  # Intervention system
│   ├── checkpoint.py    # Session checkpointing
│   └── quality_detector.py  # Quality pattern detection
├── api/                 # REST API & WebSocket
│   ├── app.py           # FastAPI application (60+ endpoints)
│   ├── validation.py    # Pydantic validation models (19 models)
│   └── routes/          # API route modules
│       └── prompt_improvements.py  # ⭐ v2.1
├── database/            # Database layer
│   ├── operations.py    # PostgreSQL operations (async)
│   ├── connection.py    # Connection pooling
│   └── retry.py         # Retry logic with exponential backoff
├── verification/        # Testing & validation
│   ├── task_verifier.py  # Task verification (11 tests)
│   ├── test_generator.py  # Test generation (15 tests)
│   ├── epic_validator.py  # Epic validation (14 tests)
│   └── integration.py   # MCP tool interception
├── quality/             # Quality & review system ⭐ v2.1 Enhanced
│   ├── metrics.py       # Quick checks (Phase 1)
│   ├── reviews.py       # Deep reviews (Phase 2)
│   ├── integration.py   # Quality integration (Phase 6)
│   ├── completion_analyzer.py  # Completion reviews (Phase 7)
│   ├── spec_parser.py   # Specification parser (Phase 7)
│   ├── requirement_matcher.py  # Requirement matching (Phase 7)
│   ├── epic_retest_manager.py  # Epic re-testing (Phase 5)
│   ├── test_compliance_analyzer.py  # Test compliance
│   └── prompt_analyzer.py  # Prompt improvements (Phase 8)
├── client/              # External service clients
│   ├── claude.py        # Claude SDK client
│   ├── playwright.py    # Browser automation (Playwright)
│   └── prompts.py       # Prompt loading
├── sandbox/             # Docker management
│   ├── manager.py       # Docker sandbox management
│   └── hooks.py         # Sandbox hooks
└── utils/               # Shared utilities
    ├── config.py        # Configuration management
    ├── logging.py       # Structured logging
    ├── errors.py        # Error hierarchy (30+ types)
    ├── security.py      # Blocklist validation
    ├── observability.py # Session logging
    └── metrics_collector.py  # Metrics collection ⭐ v2.1
```

**Key Components:**

- **REST API**: 60+ endpoints for complete platform control (health, sessions, tasks, epics, quality, completion reviews, interventions, containers)
- **Verification System**: Automated test generation for 5 test types (unit, API, browser, integration, E2E)
- **Quality System (v2.1)**: 6-phase system (+ 2 partial) with test tracking, epic re-testing, prompt improvements
- **Production Features**: Database retry logic, session checkpointing, intervention system, structured logging
- **MCP Integration**: 20+ tools for task management, quality monitoring, and epic re-testing

## Generated Project Structure

```
generations/my_project/
├── app_spec.txt              # Your specification
├── init.sh                   # Generated setup script
├── claude-progress.md        # Session notes
├── logs/                     # Session logs (JSONL + TXT)
└── [application files]       # Generated code
```

## Running Generated Applications

```bash
cd generations/my_project
./init.sh
# Or: npm install && npm run dev
```

## Browser Automation

YokeFlow uses different browser automation approaches optimized for each environment:

- **Docker Mode**: Uses [agent-browser](https://agent-browser.dev) - AI-optimized CLI with accessibility-first approach
- **Local Mode**: Uses Playwright MCP - Full-featured browser automation with rich API

This dual approach provides simple commands in containers while maintaining full capabilities for local development.

## Testing

YokeFlow has a comprehensive test suite with 70% coverage:

```bash
# Run fast tests (< 30 seconds)
python scripts/test_quick.py

# Or use pytest directly
pytest -m "not slow"

# Run with coverage report
pytest --cov=server --cov-report=html --cov-report=term-missing
```

**Test Status** (February 2026):
- ✅ **533+ total tests** across all files (46 parallel expansion, 13 MCP pre-flight, 43 brownfield)
- ✅ **70% coverage achieved** (target met)
- ✅ **Production ready** test infrastructure

For detailed testing information, see:
- [docs/testing-guide.md](docs/testing-guide.md) - Developer guide
- [tests/README.md](tests/README.md) - Test descriptions

## What's New in v2.0

YokeFlow 2.0 represents a major milestone with complete platform functionality:

### REST API (January 8, 2026)
- ✅ **17 endpoints implemented** with comprehensive validation
- ✅ **89% test coverage** (17/19 tests passing, 2 auth tests deferred)
- ✅ **Interactive documentation** at `/docs` (Swagger UI)
- **Key endpoints**: Health checks, session management, task operations, epic progress, quality reviews

### Input Validation Framework (January 8, 2026)
- ✅ **19 Pydantic models** for type-safe validation
- ✅ **52 tests** (100% passing) covering all validation scenarios
- ✅ **Clear error messages** for invalid inputs
- ✅ **Sensible defaults** for configuration
- **Benefits**: Runtime type safety, automatic OpenAPI schema generation

### Verification System (January 8-9, 2026)
- ✅ **Automated test generation** for 5 test types (unit, API, browser, integration, E2E)
- ✅ **Task verification** with retry logic (up to 3 attempts)
- ✅ **Epic validation** with integration testing
- ✅ **40 tests passing** (task_verifier: 11, test_generator: 15, epic_validator: 14)
- ✅ **850+ line guide** in [docs/verification-system.md](docs/verification-system.md)

### Architecture Reorganization (January 7, 2026)
- ✅ **All server code** moved to `server/` module
- ✅ **44 Python files** reorganized into 11 clean modules
- ✅ **No circular dependencies** - clear module boundaries
- ✅ **61 files updated** with new import paths

### Production Hardening (January 5, 2026)
- ✅ **Database retry logic** with exponential backoff (30 tests)
- ✅ **Session checkpointing** and recovery system (19 tests)
- ✅ **Intervention system** with database persistence (15 tests)
- ✅ **Structured logging** with JSON/dev formatters (19 tests)
- ✅ **Error hierarchy** with 30+ error types (36 tests)

## Documentation

### Getting Started
- [QUICKSTART.md](QUICKSTART.md) - 5-minute setup guide
- [CLAUDE.md](CLAUDE.md) - Quick reference for Claude Code

### Developer Guides
- [docs/developer-guide.md](docs/developer-guide.md) - Comprehensive technical guide
- [docs/testing-guide.md](docs/testing-guide.md) - Testing practices and tools
- [docs/configuration.md](docs/configuration.md) - Configuration reference

### API & Integration
- [docs/api-usage.md](docs/api-usage.md) - Complete API endpoint reference
- [docs/mcp-usage.md](docs/mcp-usage.md) - MCP tools documentation

### Systems
- [docs/quality-system.md](docs/quality-system.md) - Automated testing
- [docs/input-validation.md](docs/input-validation.md) - Validation framework
- [docs/docker-sandbox-implementation.md](docs/docker-sandbox-implementation.md) - Docker integration

### Database
- [docs/postgres-setup.md](docs/postgres-setup.md) - PostgreSQL setup and schema

### Operations
- [docs/deployment-guide.md](docs/deployment-guide.md) - Production deployment
- [scripts/README.md](scripts/README.md) - Utility scripts reference

## Roadmap

See [YOKEFLOW_REFACTORING_PLAN.md](YOKEFLOW_REFACTORING_PLAN.md) for:
- P0/P1/P2 priorities and estimates
- Remaining work (P1: ~30h, P2: ~20h)

## Contributing

YokeFlow is open for contributions! Areas of interest:
- Authentication system implementation
- GitHub push/PR automation for brownfield projects
- Non-UI project support (APIs, libraries, CLI tools)
- E2B sandbox integration
- Performance optimizations
- Test coverage improvements

## License

MIT License - See LICENSE file for details

## Acknowledgments

Originally forked from Anthropic's autonomous coding demo. Evolved into YokeFlow with extensive enhancements:
- Brownfield support (import and modify existing codebases)
- PostgreSQL database with async operations
- REST API with comprehensive validation
- Verification system with automated testing
- Production hardening features
- Web UI with real-time monitoring
- Quality review system
- Docker sandbox integration

**For support or questions, see [CLAUDE.md](CLAUDE.md) Troubleshooting section or open an issue.**

---

**Built with Claude by Anthropic** 🚀

