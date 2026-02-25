# Context Priming Command

Read these files to understand YokeFlow 2, an autonomous AI development platform:

## Essential Context

1. **CLAUDE.md** - Quick reference overview (START HERE!)
   - What YokeFlow is and its purpose
   - v2.0 features and architecture
   - Key components and workflows
   - Troubleshooting guide

2. **README.md** - Complete platform overview
   - v2.0 feature highlights
   - Installation and setup
   - Architecture details
   - What's new in v2.0

3. **QUICKSTART.md** - 5-minute setup guide
   - Prerequisites and installation
   - Starting the platform
   - Common issues and solutions

## After Reading

You should understand:

### YokeFlow v2.0 Platform
- ✅ **Purpose**: Autonomous AI development platform using Claude
- ✅ **Architecture**:
  - FastAPI REST API (17+ endpoints, 89% test coverage)
  - Next.js Web UI (TypeScript/React, real-time monitoring)
  - PostgreSQL database (async operations, retry logic)
  - MCP (Model Context Protocol) task management
  - agent-browser for browser testing
  - Automated verification system (test generation)

### Core Features
- ✅ **Two-Phase Workflow**:
  - Session 0 (Opus): Creates roadmap (epics → tasks → tests)
  - Sessions 1+ (Sonnet): Implements features with verification
- ✅ **Production Hardening**: Database retry logic, session checkpointing, intervention system
- ✅ **Quality System**: Automated reviews, metrics, trend tracking
- ✅ **Test Coverage**: 70% (212 tests), comprehensive test suite
- ✅ **Input Validation**: Pydantic framework (19 models, 52 tests)

### File Organization
- **server/**: All server code (agent, api, database, verification, quality, utils)
- **web-ui/**: Next.js frontend
- **mcp-task-manager/**: MCP server (TypeScript)
- **schema/postgresql/**: Database schema (consolidated)
- **docs/**: Comprehensive documentation
- **tests/**: Test suited

## Quick Commands

```bash
# Start API
uvicorn server.api.app:app --host 0.0.0.0 --port 8010 --reload

# Start Web UI
cd web-ui && npm run dev

# Initialize database
python scripts/init_database.py --docker
```

