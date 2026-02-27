# YokeFlow 2 - Autonomous AI Development Platform

Build complete applications using Claude Agent SDK across multiple autonomous sessions.

## Overview

YokeFlow 2 is an autonomous coding platform that uses Claude to build applications from specifications.


## Getting Started

See [QUICKSTART.md](QUICKSTART.md) for setup instructions.

## Requirements

- Node.js 20+
- Python 3.9+
- PostgreSQL (via Docker Compose)


## How It Works

The system uses a hierarchical task structure:
- Epics (high-level features)
- Tasks (specific implementations)
- Tests (validation criteria)

1. **Session 0 (Initialization)**: Reads spec from `yokeflow/specs/` → Creates epics, tasks, and tests
2. **Sessions 1+ (Coding)**: Gets next task → Implements → Tests → Commits → Auto-continues

**Brownfield** (existing codebases):
1. **Import**: Clone from GitHub or copy from local path → Analyze codebase → Create feature branch
2. **Session 0 (Initialization)**: Explores existing code → Reads `yokeflow/specs/change_spec.md` → Creates scoped epics, tasks, and tests
3. **Sessions 1+ (Coding)**: Gets next task → Modifies existing code → Regression tests → Commits



## Configuration

Configure via `.yokeflow.yaml`:

```yaml
models:
  initializer: claude-opus-4-6
  coding: claude-sonnet-4-6
  review: claude-sonnet-4-6          # ⭐ NEW v2.1
  prompt_improvement: claude-opus-4-6 # ⭐ NEW v2.1

timing:
  auto_continue_delay: 3
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
│   ├── orchestrator.py  # Session lifecycle
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
│   ├── spec_parser.py   # Specification parser (Phase 7)
│   ├── test_compliance_analyzer.py  # Test compliance
│   └── prompt_analyzer.py  # Prompt improvements (Phase 8)
├── client/              # External service clients
│   ├── claude.py        # Claude SDK client
│   └── prompts.py       # Prompt loading
└── utils/               # Shared utilities
    ├── config.py        # Configuration management
    ├── logging.py       # Structured logging
    ├── errors.py        # Error hierarchy (30+ types)
    ├── security.py      # Blocklist validation
    ├── observability.py # Session logging
    └── metrics_collector.py  # Metrics collection ⭐ v2.1
```

**Key Components:**

- **REST API**: 60+ endpoints for complete platform control (health, sessions, tasks, epics, quality, completion reviews, interventions)
- **Verification System**: Automated test generation for 5 test types (unit, API, browser, integration, E2E)
- **Quality System (v2.1)**: 6-phase system (+ 2 partial) with test tracking, epic re-testing, prompt improvements
- **Production Features**: Database retry logic, session checkpointing, intervention system, structured logging
- **MCP Integration**: 20+ tools for task management, quality monitoring, and epic re-testing

## Generated Project Structure

```
projects/my_project/
├── init.sh                   # Generated setup script
├── yokeflow/                 # YokeFlow metadata (separate from app code)
│   ├── specs/                # Specification files (original names preserved)
│   ├── logs/                 # Session logs (JSONL + TXT)
│   ├── agent-progress.md     # Cross-session context
│   └── screenshots/          # Browser verification screenshots
└── [application files]       # Generated code
```

## Browser Automation

YokeFlow uses [agent-browser](https://github.com/vercel-labs/agent-browser) for browser testing during coding sessions. Install it as a prerequisite:

```bash
# macOS
brew install agent-browser
agent-browser install
```

## Testing


```bash
# Run fast tests (< 30 seconds)
python scripts/test_quick.py

# Or use pytest directly
pytest -m "not slow"

# Run with coverage report
pytest --cov=server --cov-report=html --cov-report=term-missing
```

For detailed testing information, see:
- [docs/testing-guide.md](docs/testing-guide.md) - Developer guide
- [tests/README.md](tests/README.md) - Test descriptions


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

### Database
- [docs/postgres-setup.md](docs/postgres-setup.md) - PostgreSQL setup and schema

### Operations
- [docs/deployment-guide.md](docs/deployment-guide.md) - Production deployment
- [scripts/README.md](scripts/README.md) - Utility scripts reference

## Roadmap

See [IMPROVEMENT-IDEAS.md](IMPROVEMENT-IDEAS.md)

## License

MIT License

## Acknowledgments

Originally forked from Anthropic's autonomous coding demo - https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding

AI Spec Generation by: https://github.com/imagicrafter

---

**Built with Claude by Anthropic** 🚀

