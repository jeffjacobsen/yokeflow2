# YokeFlow 2 - Quick Start Guide

Get up and running with YokeFlow 2's refactored architecture in 5 minutes.

## What's New in YokeFlow 2.0

- **REST API Complete**: 17 endpoints with comprehensive validation (89% test coverage)
- **Input Validation**: Pydantic framework ensuring type safety and clear error messages
- **Verification System**: Automated test generation for task completion and epic validation
- **Reorganized Architecture**: All server code under `server/` with clear module separation
- **Production Hardening**: Database retry logic, session checkpointing, intervention system
- **Enhanced Testing**: 70% coverage achieved with 212 total tests

## Project Structure

```
server/
├── agent/        # Session orchestration & lifecycle
├── api/          # REST API & WebSocket endpoints
├── database/     # PostgreSQL operations & retry logic
├── quality/      # Review system & quality gates
├── verification/ # Task & epic validation
├── client/       # Claude SDK & prompt clients
└── utils/        # Shared utilities & config
```

## Prerequisites

1. **Node.js 20+ and Python 3.9+**
   ```bash
   node --version  # Should show v20.x.x or newer
   python --version  # Should show 3.9 or newer
   ```

2. **PostgreSQL Database** (via Docker)
   ```bash
   docker-compose up -d
   python scripts/init_database.py --docker
   ```

3. **Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **MCP Task Manager** (TypeScript)
   ```bash
   cd mcp-task-manager
   npm install
   npm run build
   cd ..
   ```

5. **Next.js Web UI**
   ```bash
   cd web-ui
   cp .env.local.example .env.local
   npm install
   cd ..
   ```

6. **Agent-Browser** (browser testing for coding sessions)
   ```bash
   # macOS (recommended)
   brew install agent-browser
   agent-browser install

   # Or via npm (requires write access to global node_modules)
   # npm install -g agent-browser && agent-browser install
   ```

7. **Authentication Token**
   ```bash
   # Install Claude Code CLI
   npm install -g @anthropic-ai/claude-code

   # Set up Claude Code token
   claude setup-token

   # Copy environment template and add your token
   cp .env.example .env
   # Edit .env and set CLAUDE_CODE_OAUTH_TOKEN
   ```

## Starting the Platform

**Terminal 1 - Start API Server:**
```bash
# Using wrapper script (recommended)
python server/api/start.py

# OR using uvicorn directly
uvicorn server.api.app:app --host 0.0.0.0 --port 8010

# For development with auto-reload
uvicorn server.api.app:app --host 0.0.0.0 --port 8010 --reload
```

**Terminal 2 - Start Web UI:**
```bash
cd web-ui
npm run dev
```

**Terminal 3 - Start Docker Watchdog (Recommended):**
```bash
# Prevents Docker crashes from stopping your sessions
./scripts/docker-watchdog.sh &

# It will:
# - Check Docker every 30 seconds
# - Auto-restart if Docker crashes
# - Restart PostgreSQL container
# - Log all events to docker-watchdog.log
```

**Why run the watchdog?**
- Docker Desktop can crash even when Mac doesn't sleep
- Prevents "Database connection error" mid-session
- Auto-recovers without human intervention
- Essential for long-running coding sessions

Then open http://localhost:3010 in your browser.

## Common Issues

### Issue: "API server not responding at localhost:8010"

**Problem:** You ran the API file directly instead of using uvicorn

**Solution:** Use uvicorn to start the server:
```bash
# Correct way to start the API
uvicorn server.api.app:app --host 0.0.0.0 --port 8010 --reload

# Or use the wrapper script
python server/api/start.py
```

### Issue: "Database connection error"

**Problem:** PostgreSQL not running

**Solution:**
```bash
# Start PostgreSQL
docker-compose up -d

# Verify it's running
docker ps | grep postgres

# Initialize schema
python scripts/init_database.py --docker
```

### Issue: "No API authentication configured"

**Problem:** Missing CLAUDE_CODE_OAUTH_TOKEN in .env

**Solution:**
```bash
# Get your token
claude setup-token

# Add to .env
cp .env.example .env
# Edit .env and add your token
```

### Issue: "Import errors after update"

**Problem:** Old import paths from api/, core/, or review/ folders

**Solution:** All code has been moved to server/:
```python
# Old imports (no longer work)
from core.agent import Agent
from api.main import app
from review.review_client import ReviewClient

# New imports (correct)
from server.agent.agent import SessionManager
from server.api.app import app
from server.quality.reviews import ReviewClient
```

## Verifying Everything Works

1. **Check API Health:**
   ```bash
   curl http://localhost:8010/health
   # Should return JSON with status and component checks
   ```

2. **Check API Detailed Health:**
   ```bash
   curl http://localhost:8010/health/detailed
   # Should return JSON with database, mcp_server, disk, sessions status
   ```

3. **Check API Projects Endpoint:**
   ```bash
   curl http://localhost:8010/api/projects
   # Should return: []  (empty array if no projects yet)
   ```

4. **Check Database:**
   ```bash
   psql postgresql://agent:agent_dev_password@localhost:5432/yokeflow -c "SELECT 1;"
   # Should return: 1
   ```

5. **Check MCP Server:**
   ```bash
   ls mcp-task-manager/build/index.js
   # File should exist after npm run build
   ```

6. **Check Web UI:**
   Open http://localhost:3010 - you should see the YokeFlow dashboard

7. **Check API Documentation:**
   Open http://localhost:8010/docs - interactive Swagger UI for all 17+ endpoints

## Next Steps

1. **Create Your First Project:**
   - Click "Create New Project" in the Web UI
   - Upload a spec file (or use specs/app_spec.txt as example)
   - Click "Initialize Project" to create the roadmap

2. **Start Coding:**
   - After initialization completes, click "Start Coding Sessions"
   - Watch real-time progress in the UI
   - Sessions will auto-continue until all tasks are complete

3. **Monitor Progress:**
   - View session logs in the "Logs" tab
   - Check progress cards for completion stats
   - Stop sessions anytime with "Stop Sessions" button

## Documentation

- [README.md](README.md) - Full platform overview
- [CLAUDE.md](CLAUDE.md) - Quick reference guide
- [YOKEFLOW_REFACTORING_PLAN.md](YOKEFLOW_REFACTORING_PLAN.md) - Roadmap and improvements
- [docs/developer-guide.md](docs/developer-guide.md) - Comprehensive technical guide
- [docs/api-usage.md](docs/api-usage.md) - Complete API endpoint reference
- [docs/verification-system.md](docs/verification-system.md) - Automated testing framework (850+ lines)
- [docs/input-validation.md](docs/input-validation.md) - Validation framework guide

## Getting Help

- Check [CLAUDE.md](CLAUDE.md) Troubleshooting section
- Review logs in `projects/[project]/yokeflow/logs/`
- Open an issue on GitHub

## Pro Tips

1. **Use Opus for initialization, Sonnet for coding** (default behavior)
2. **Reset projects without re-initializing:**
   ```bash
   python scripts/reset_project.py --project my_project
   ```
   - Resets to state after initialization but before coding started
   - Saves 10-20 minutes by preserving the complete roadmap
3. **Monitor with utility scripts:**
   ```bash
   python scripts/task_status.py my_project
   ```
4. **Clean up stuck sessions:**
   ```bash
   python scripts/cleanup_sessions.py --project my_project
   ```
5. **Review session quality:**
   - Use the Web UI Quality Dashboard (automatic deep reviews)
   - Access via project detail page → Quality tab

---

**Ready to build!** 🚀
