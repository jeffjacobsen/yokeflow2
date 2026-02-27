# YokeFlow 2 - Autonomous AI Development Platform

Build complete applications using Claude Agent SDK across multiple autonomous sessions.

## Overview

YokeFlow 2 is an autonomous coding platform that uses Claude to build applications from specifications.


## Project Status

This project is archived. No additional changes are planned.

YokeFlow 2 was originally forked from Anthropic's [autonomous coding demo](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding) and uses the Claude Agent SDK to orchestrate multi-session development.

Anthropic has made conflicting statements about whether the Agent SDK can be used with MAX subscriptions. Additionally, recent improvements to Claude Code — not yet available in the SDK — make it significantly better at coding in long sessions. For these reasons, development has been paused in favor of waiting for the SDK to catch up.

For this final release, documentation has been improved and updated, and partially implemented features have been removed. The release has been tested with multiple projects on a Mac Mini with no errors and should be fully functional.

**Notes:**
- Projects are created in the local `projects/` folder. The option to create them in a Docker container has been removed. Running YokeFlow 2 itself inside a Docker container is recommended if isolation is desired.
- YokeFlow was designed to create new projects (greenfield). Support for importing existing projects (brownfield) was added but has not been thoroughly tested. It may be useful for adding features to an existing codebase, but bug fixing is not an intended use case.

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
  review: claude-sonnet-4-6
  prompt_improvement: claude-opus-4-6

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
│   ├── codebase_import.py  # Codebase import & analysis (brownfield)
│   ├── agent.py         # Agent loop and session logic
│   ├── checkpoint.py    # Session checkpointing
│   └── models.py        # Orchestrator data models
├── api/                 # REST API & WebSocket
│   ├── app.py           # FastAPI application (60+ endpoints)
│   ├── validation.py    # Pydantic validation models
│   └── routes/          # API route modules
├── database/            # Database layer
│   ├── operations.py    # PostgreSQL operations (async)
│   ├── connection.py    # Connection pooling
│   └── retry.py         # Retry logic with exponential backoff
├── quality/             # Quality & review system
│   ├── reviews.py       # Deep reviews
│   ├── integration.py   # Quality integration
│   ├── spec_parser.py   # Specification parser
│   ├── test_compliance_analyzer.py  # Test compliance
│   └── prompt_analyzer.py  # Prompt improvements
├── client/              # External service clients
│   ├── claude.py        # Claude SDK client
│   └── prompts.py       # Prompt loading
├── generation/          # Spec generation
├── coverage/            # Test coverage analysis
└── utils/               # Shared utilities
    ├── config.py        # Configuration management
    ├── logging.py       # Structured logging
    ├── errors.py        # Error hierarchy (30+ types)
    ├── security.py      # Blocklist validation
    └── observability.py # Session logging
```

**Key Components:**

- **REST API**: 60+ endpoints for complete platform control (health, sessions, tasks, epics, quality, completion reviews)
- **Quality System**: Test tracking, epic re-testing, prompt improvements
- **Production Features**: Database retry logic, session checkpointing, structured logging
- **MCP Integration**: 20 tools for task management and epic re-testing

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
# Run all tests (~1 second)
pytest

# Or use the helper script
python scripts/test_quick.py

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
- [docs/postgres-setup.md](docs/postgres-setup.md) - PostgreSQL setup and schema

### Operations
- [docs/deployment-guide.md](docs/deployment-guide.md) - Production deployment

## Roadmap

See [IMPROVEMENT-IDEAS.md](IMPROVEMENT-IDEAS.md)

## License

MIT License

## Acknowledgments

AI Spec Generation by: https://github.com/imagicrafter

---

**Built with Claude by Anthropic**
