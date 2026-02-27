# YokeFlow 2 - Quick Start Guide

> **Upgrading from an earlier version?** See [UPDATE-REQUIRED.md](UPDATE-REQUIRED.md) to replace your old database.

## Prerequisites

1. **Node.js 20+ and Python 3.9+**
   ```bash
   node --version   # Should show v20.x.x or newer
   python --version # Should show 3.9 or newer
   ```

2. **PostgreSQL Database** (via Docker)
   ```bash
   docker compose up -d
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
   # macOS
   brew install agent-browser
   agent-browser install
   ```

7. **Authentication Token**
   ```bash
   npm install -g @anthropic-ai/claude-code
   claude setup-token

   cp .env.example .env
   # Edit .env and set CLAUDE_CODE_OAUTH_TOKEN
   ```

## Starting the Platform

**Terminal 1 - Start API Server:**
```bash
python server/api/start.py
```

**Terminal 2 - Start Web UI:**
```bash
cd web-ui
npm run dev
```

Then open http://localhost:3010 in your browser.

## Verifying Everything Works

```bash
# API health
curl http://localhost:8010/health/detailed

# Projects endpoint
curl http://localhost:8010/api/projects
# Should return: []

# Database
psql postgresql://agent:agent_dev_password@localhost:5432/yokeflow -c "SELECT 1;"

# MCP server built
ls mcp-task-manager/dist/index.js

# Web UI
# Open http://localhost:3010

# Swagger API docs
# Open http://localhost:8010/docs
```

## Common Issues

**"Database connection error"** -- PostgreSQL not running. Start it with `docker compose up -d` and initialize with `python scripts/init_database.py --docker`.

**"No API authentication configured"** -- Missing `CLAUDE_CODE_OAUTH_TOKEN` in `.env`. Run `claude setup-token`, then add the token to your `.env` file.

**MCP server errors** -- Rebuild with `cd mcp-task-manager && npm run build`.

## Using YokeFlow

1. **Create a project** -- Click "Create New Project" in the Web UI and upload a spec file (see `example-specs/` for examples)
2. **Initialize** -- Click "Initialize Project" to create the roadmap (uses Opus)
3. **Start coding** -- Click "Start Coding Sessions" to begin autonomous implementation (uses Sonnet)
4. **Monitor** -- Watch progress in the UI; sessions auto-continue until all tasks are complete

See [README.md](README.md) for more details.
