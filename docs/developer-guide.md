# Developer Guide

This guide provides technical details for developers who want to understand, customize, or extend YokeFlow.

**Version**: 2.1.0

## What's New in v2.1

YokeFlow 2.1 introduces a comprehensive quality system across 8 phases:

**Phase 0**: Database cleanup - Removed 34 unused objects
**Phase 1**: Test execution tracking - Error messages, execution time, retry counts
**Phase 2**: Epic test failure tracking - 22-field history, flaky test detection
**Phase 3**: Epic test blocking - Strict/autonomous modes, orchestrator integration
**Phase 4.1**: Test viewer UI - Epic/task tests visible with requirements
**Phase 5**: Epic re-testing - Smart selection, regression detection, stability scoring
**Phase 6**: Enhanced review triggers - 7 quality-based conditions
**Phase 7**: Project completion review - Spec parser, requirement matcher, Claude review
**Phase 8**: Prompt improvement aggregation - Recommendation extraction (60% complete)

**Key Additions:**
- 5 new MCP tools (20+ total)
- 5 new REST API endpoint groups (60+ total endpoints)
- 7 database migrations (017-020+)
- 4 new configuration sections in `.yokeflow.yaml`
- ~5,000+ lines of new code

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Core Components](#core-components)
- [Quality System (v2.1)](#quality-system-v21)
- [MCP Integration](#mcp-integration)
- [Database Schema](#database-schema)
- [Security System](#security-system)
- [Observability](#observability)
- [Extending the System](#extending-the-system)
- [Testing](#testing)
- [Development Workflow](#development-workflow)
- [Verification System](#verification-system)
- [Performance Considerations](#performance-considerations)
- [Deployment](#deployment)

---

## Architecture Overview

### System Components

**API-First Architecture:**
```
┌─────────────────┐
│   Web Browser   │
└────────┬────────┘
         │ HTTP/WebSocket
         ▼
┌─────────────────────┐
│  Next.js Web UI     │  TypeScript/React (port 3010)
│  - Project mgmt     │
│  - Real-time updates│
│  - Env editor       │
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
         │                          │
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
└─────────────────────────────────┘
       │
       ├────────────────┬─────────────┐
       │                │             │
       ▼                ▼             ▼
┌──────────────┐  ┌─────────┐  ┌──────────────┐
│ MCP Servers  │  │Security │  │Observability │
│ task-manager │  │Blocklist│  │Session Logs  │
│              │  │         │  │              │
└──────┬───────┘  └─────────┘  └──────────────┘
       │
       ▼
┌─────────────────────────┐
│ PostgreSQL Database     │
│ (centralized, all       │
│  projects)              │
└─────────────────────────┘
```


### Data Flow

**Initialization Flow:**
```
User → yokeflow.py → agent.py → orchestrator.py
  ↓
Create project in PostgreSQL database
  ↓
Copy app_spec.txt to project directory
  ↓
Create MCP client with task-manager server (PostgreSQL connection)
  ↓
Load initializer_prompt.md
  ↓
Agent creates epics → expands into tasks → adds tests (in PostgreSQL)
  ↓
Auto-stop (complete roadmap ready)
```

**Coding Flow:**
```
User → yokeflow.py → agent.py
  ↓
Load MCP client with task-manager server
  ↓
Load coding_prompt.md
  ↓
Agent loop:
  1. get_next_task (MCP call)
  2. Implement feature
  3. Browser automation verification
  4. update_test_result (MCP calls)
  5. update_task_status (MCP call)
  6. Git commit
  7. Auto-continue (3s delay)
```

---

## Core Components

### server/ Directory Structure

YokeFlow v2.0 uses a clean modular structure under `server/`:

```
server/
├── agent/              # Session orchestration & lifecycle
│   ├── agent.py        # Agent loop and session logic
│   ├── orchestrator.py # Session lifecycle management
│   ├── session_manager.py # Intervention system
│   ├── checkpoint.py   # Session checkpointing
│   ├── intervention.py # Blocker detection
│   ├── quality_detector.py # Quality pattern detection ⭐ v2.1
│   └── models.py       # Data models
├── api/                # REST API & WebSocket
│   ├── app.py          # Main FastAPI application (60+ endpoints)
│   ├── auth.py         # Authentication
│   ├── validation.py   # Pydantic models (19 models) ⭐ v2.1
│   └── routes/         # API route modules
│       └── prompt_improvements.py # Prompt improvement routes ⭐ v2.1
├── client/             # External service clients
│   ├── claude.py       # Claude SDK client
│   └── prompts.py      # Prompt loading
├── database/           # Database layer
│   ├── operations.py   # PostgreSQL operations
│   ├── connection.py   # Connection pooling
│   └── retry.py        # Retry logic with exponential backoff
├── quality/            # Quality & review system ⭐ v2.1
│   ├── metrics.py      # Quality metrics (Phase 1)
│   ├── reviews.py      # Deep reviews (Phase 2)
│   ├── gates.py        # Quality gates
│   ├── integration.py  # Quality integration (Phase 6)
│   ├── spec_parser.py  # Specification parser (Phase 7)
│   ├── epic_retest_manager.py # Epic re-testing (Phase 5)
│   ├── test_compliance_analyzer.py # Test compliance
│   └── prompt_analyzer.py # Prompt improvements (Phase 4/8)
├── verification/       # Testing & validation
│   ├── task_verifier.py  # Task verification (11 tests)
│   ├── epic_validator.py # Epic validation (14 tests)
│   ├── epic_manager.py  # Epic management
│   └── test_generator.py # Test generation (15 tests)
└── utils/              # Shared utilities
    ├── config.py       # Configuration
    ├── logging.py      # Structured logging (19 tests)
    ├── errors.py       # Error hierarchy (36 tests)
    ├── security.py     # Security validation (2 tests)
    ├── observability.py # Session logging
    ├── reset.py        # Project reset
    ├── metrics_collector.py # Metrics collection ⭐ v2.1
    └── cancel_initialization.py # Cancel operations
```

**v2.1 Additions** (⭐ marked above):
- 10+ new files in `server/quality/` for comprehensive quality system
- Enhanced API with validation framework
- Quality pattern detection in agent
- Epic re-testing infrastructure
- Project completion review system
```

### server/agent/agent.py

**Purpose:** Core agent session logic

**Key Functions:**

`run_agent_session()` - Single agent session
- Creates client context
- Sends prompt
- Processes response stream
- Handles: AssistantMessage, UserMessage, SystemMessage
- Applies QuietOutputFilter for terminal display
- Logs everything via SessionLogger

`start_session()` in orchestrator.py - Session lifecycle management
- Detects first run vs continuation (checks for epics in PostgreSQL)
- Creates session logger
- Selects appropriate model (initializer vs coding)
- Loads appropriate prompt
- Calls run_agent_session()
- Auto-stops after initializer
- Auto-continues after coding sessions (3s delay)

**Session Type Detection:**
```python
# Check if project has epics in PostgreSQL
async with DatabaseManager() as db:
    epics = await db.list_epics(project_id)
    is_first_run = len(epics) == 0

if is_first_run:
    # Use initializer prompt + initializer model
    # Create project roadmap in PostgreSQL
    # Stop after completion
else:
    # Use coding prompt + coding model
    # Auto-continue with delay
```

### server/client/claude.py

**Purpose:** Claude SDK client configuration

**Key Features:**
- Loads MCP servers (task-manager, puppeteer)
- Configures `bypassPermissions` mode for autonomous operation
- Sets up security hooks (Bash blocklist)
- Passes project-specific environment variables to MCP servers

**MCP Server Configuration:**
```python
mcp_servers = {
    "task-manager": {
        "command": "node",
        "args": [str(mcp_server_path)],
        "env": {
            "DATABASE_URL": os.getenv("DATABASE_URL"),
            "PROJECT_ID": str(project_id)
        }
    },
}
```

### server/client/prompts.py

**Purpose:** Prompt loading and project setup

**Key Functions:**

`get_initializer_prompt()` - Load initializer_prompt.md

`get_coding_prompt()` - Load coding_prompt.md

`copy_spec_to_project()` - Copy app_spec.txt to project

### server/utils/security.py

**Purpose:** Bash command blocklist validation

**Blocked Command Categories:**
- File operations: rm, rmdir
- System modification: sudo, su, chown, chgrp
- Destructive operations: dd, mkfs, fdisk
- System control: reboot, shutdown, systemctl
- Package managers: apt, yum, dnf, brew
- Kernel modules: insmod, rmmod
- User management: useradd, passwd

**Special Cases:**
- `pkill` - Only allows development processes (node, npm, python, etc.)
- All other commands allowed by default

**Validation:**
```python
def validate_bash_command(command: str) -> tuple[bool, str]:
    """Returns (is_allowed, reason)"""
    # Check blocklist
    # Special handling for pkill
    # Return True/False + explanation
```

### server/utils/observability.py

**Purpose:** Session logging and output filtering

**Classes:**

`SessionLogger`:
- Dual-format logging (JSONL + TXT)
- Tracks: prompts, messages, tool use/results, thinking, errors
- Auto-increments session numbers
- Session metrics stored in PostgreSQL database

`QuietOutputFilter`:
- Controls terminal verbosity
- Quiet mode: assistant text, Bash tools, errors only
- Verbose mode: everything (tool inputs, results, thinking, system messages)

**Log Structure:**
```
projects/[project]/logs/
├── session_001_20251209_140523.jsonl  # Machine-readable
└── session_001_20251209_140523.txt    # Human-readable

Note: Session metrics stored in PostgreSQL (sessions.metrics JSONB field)
```

### server/utils/progress.py

**Purpose:** Progress tracking utilities

**Key Functions:**

`get_progress_from_db(project_dir)`:
- Queries v_progress view
- Returns dict with completion stats

`print_progress_summary(project_dir)`:
- Terminal output of current progress
- Called between sessions

### server/database/operations.py

**Purpose:** PostgreSQL database abstraction layer with async operations

**Key Features:**
- Provides `TaskDatabase` class with 20+ async methods
- Clean separation between data access and business logic
- Production-ready with asyncpg and connection pooling
- Consistent API across all modules (CLI, API, Web UI)
- UUID-based project identification
- JSONB for flexible metadata

**Key Methods:**
- `get_progress(project_id)` - Overall statistics
- `get_next_task(project_id)` - Next task to work on
- `list_epics(project_id)` - Epic queries
- `list_tasks(project_id)` - Task queries
- `create_epic()`, `create_task()` - Create operations
- `update_task_status()`, `update_test_result()` - Update operations

**Usage Example:**
```python
from core.database_connection import DatabaseManager

async with DatabaseManager() as db:
    progress = await db.get_progress(project_id)
    next_task = await db.get_next_task(project_id)
    await db.update_task_status(task_id=5, done=True)
```

### server/agent/orchestrator.py

**Purpose:** Agent orchestration service for API-driven control

**Key Features:**
- Decouples session management from CLI
- Enables API-driven control of agent sessions
- Foundation for job queue integration (Celery/Redis)
- Makes the system more modular and testable

**Classes:**

`AgentOrchestrator`:
- `create_project()` - Initialize new project
- `start_session()` - Begin agent session
- `get_session_info()` - Query session status
- `list_sessions()` - Get session history

`SessionInfo`:
- Dataclass containing session metadata
- Status, timestamps, model info, errors

**Usage Example:**
```python
from core.orchestrator import AgentOrchestrator

orchestrator = AgentOrchestrator(verbose=False)
session_info = await orchestrator.start_session(
    project_dir=Path("projects/my-project"),
    model="claude-sonnet-4-6"
)
```

---

## Quality System (v2.1)

YokeFlow 2.1 introduces a comprehensive quality system implemented across 8 phases from January 31 - February 2, 2026.

### Architecture

The quality system is distributed across multiple modules:

```
server/quality/          # 10+ Python files (~4,000+ lines)
├── metrics.py           # Quick metrics (Phase 1, zero-cost)
├── reviews.py           # Deep AI reviews (Phase 2)
├── integration.py       # Triggers & coordination (Phase 6)
├── spec_parser.py       # Parse app_spec.txt (Phase 7)
├── epic_retest_manager.py # Regression testing (Phase 5)
└── prompt_analyzer.py   # Improvement suggestions (Phase 4/8)

web-ui/src/components/   # React components
├── QualityDashboard.tsx # Phase 3 dashboard
├── CompletionReviewDashboard.tsx # Phase 7 UI
└── PromptImprovementDashboard.tsx # Phase 8 UI

mcp-task-manager/src/    # MCP tools
└── index.ts             # 5 new quality tools
```

### Phase Breakdown

**Phase 0: Database Cleanup**
- Removed 34 unused objects (16 tables, 18 views)
- Clean foundation for quality system
- Migration: `schema/postgresql/schema.sql`

**Phase 1: Test Execution Tracking**
- Added: `last_error_message`, `execution_time_ms`, `retry_count`
- MCP tools enhanced: `update_task_test_result`, `update_epic_test_result`
- Performance indexes for slow/flaky test detection
- Migration: `017_add_test_error_tracking.sql`

**Phase 2: Epic Test Failure Tracking**
- `epic_test_failures` table (22 fields, 9 indexes)
- 5 analysis views for pattern detection
- Flaky test detection (passed before, now failing)
- Migration: `018_epic_test_failure_tracking.sql`

**Phase 3: Epic Test Blocking**
- Configuration: `epic_testing.mode` (strict/autonomous)
- MCP integration: `checkEpicCompletion()` in task-manager
- Orchestrator: `SessionStatus.BLOCKED` handling
- Tests: `test_epic_test_blocking.py` (5 passing)

**Phase 4.1: Test Viewer UI**
- Epic/task tests visible in Web UI
- Requirements-based testing display
- Component: `EpicAccordion.tsx` (lines 149-181)

**Phase 5: Epic Re-testing**
- Smart selection algorithm (foundation, high-dependency, standard tiers)
- Automatic regression detection
- Stability scoring (0.00-1.00 scale)
- 3 MCP tools: `trigger_epic_retest`, `record_epic_retest_result`, `get_epic_stability_metrics`
- Migration: `019_add_epic_retesting.sql`
- Implementation: `server/quality/epic_retest_manager.py` (450+ lines)

**Phase 6: Enhanced Review Triggers**
- Removed periodic 5-session trigger
- Added 7 quality-based conditions:
  1. Low quality score (< 7/10)
  2. High error rate (> 10%)
  3. High error count (30+)
  4. Score/error mismatch
  5. High adherence violations (5+)
  6. Low verification rate (< 50%)
  7. Repeated errors (3+ same error)
- Implementation: `server/utils/observability.py:505-571`

**Phase 7: Project Completion Review**
- Specification parser: 450 lines, 25 tests, 100% coverage
- Requirement matcher: Hybrid keyword (40%) + semantic (60%) matching
- Completion analyzer: Scoring algorithm (coverage 60%, quality 20%, bonus/penalty 20%)
- 5 REST API endpoints
- Web UI: `CompletionReviewDashboard.tsx` (500 lines)
- Migration: `020_project_completion_reviews.sql`
- Automatic trigger on project completion

**Phase 8: Prompt Improvement Aggregation** (60% complete)
- Steps 8.1-8.2 complete: Recommendation extraction, proposal generation
- Database: `prompt_improvement_analyses`, `prompt_proposals`
- Web UI: `PromptImprovementDashboard.tsx`
- Step 8.3 deferred: Versioning & A/B testing (4-7h)

### Key Files

**Quality Metrics & Reviews:**
- `server/quality/metrics.py` - Quick quality checks
- `server/quality/reviews.py` - Claude-powered deep analysis
- `server/quality/integration.py` - Trigger coordination

**Completion Review:**
- `server/quality/spec_parser.py` - Parse markdown specs (25 tests)
- Completion review not yet implemented (see `COMPLETION_REVIEW.md`)

**Epic Re-testing:**
- `server/quality/epic_retest_manager.py` - Smart selection algorithm
- Configuration: `.yokeflow.yaml` → `epic_retesting` section

**Test Compliance:**
- `server/quality/test_compliance_analyzer.py` - Verify test coverage

### Usage

**Enable Quality System** (`.yokeflow.yaml`):
```yaml
review:
  min_reviews_for_analysis: 5

epic_testing:
  mode: autonomous  # or "strict"
  critical_epics:
    - Authentication
    - Payment
  auto_failure_tolerance: 3

epic_retesting:
  enabled: true
  trigger_frequency: 2  # Every 2 epics
  foundation_retest_days: 7
```

**Trigger Completion Review** (API):
```bash
curl -X POST http://localhost:8010/api/projects/PROJECT_ID/completion-review
```

**View Quality Dashboard** (Web UI):
- Navigate to project → Quality tab
- See: Quality score, test results, review history
- Completion review: Overall score, requirement breakdown, recommendations

### Benefits

- **Real-time visibility**: Session quality tracked continuously
- **Automated error tracking**: Every test failure captured with context
- **Intelligent intervention**: Context-aware blocking based on epic criticality
- **Regression detection**: Catches breaking changes within 2 epics
- **Quality-based reviews**: Triggers only when needed (7 conditions)
- **Completion verification**: Validates against original specification
- **Actionable insights**: Claude-powered recommendations for improvement

---

## MCP Integration

### MCP Server Location

```
mcp-task-manager/
├── src/
│   └── index.ts       # MCP server implementation
├── dist/
│   └── index.js       # Compiled (this is what runs)
├── package.json
└── tsconfig.json
```

### Building the MCP Server

```bash
cd mcp-task-manager
npm install
npm run build  # Compiles TypeScript to dist/index.js
```

### Available Tools (20+ total)

See [mcp-usage.md](mcp-usage.md) for complete tool reference.

**Query Tools:**
- task_status, get_next_task, list_epics, get_epic, list_tasks, list_tests, get_session_history
- `get_epic_stability_metrics` - Stability analytics ⭐ v2.1

**Update Tools:**
- update_task_status, start_task, update_test_result (legacy)
- `update_task_test_result` - With error details ⭐ v2.1
- `update_epic_test_result` - With error details ⭐ v2.1
- `record_epic_retest_result` - With regression detection ⭐ v2.1

**Create Tools:**
- create_epic, create_task, create_test, expand_epic, log_session
- `trigger_epic_retest` - Smart epic re-testing ⭐ v2.1

### Tool Implementation Pattern

```typescript
// In index.ts
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "task_status",
      description: "Get overall progress statistics",
      inputSchema: { type: "object", properties: {} }
    },
    // ... more tools
  ]
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  switch (name) {
    case "task_status":
      const stats = db.prepare(`SELECT * FROM v_progress`).get();
      return { content: [{ type: "text", text: JSON.stringify(stats) }] };

    // ... more cases
  }
});
```

### Adding a New MCP Tool

1. **Define tool in ListToolsRequestSchema handler:**
```typescript
{
  name: "my_new_tool",
  description: "What this tool does",
  inputSchema: {
    type: "object",
    properties: {
      param1: { type: "string", description: "..." },
      param2: { type: "number", description: "..." }
    },
    required: ["param1"]
  }
}
```

2. **Add case in CallToolRequestSchema handler:**
```typescript
case "my_new_tool":
  const { param1, param2 } = args;
  // Validate inputs
  // Query database
  // Return result
  return {
    content: [{
      type: "text",
      text: JSON.stringify(result)
    }]
  };
```

3. **Rebuild:**
```bash
npm run build
```

4. **Update prompts:**
Add usage instructions to `prompts/coding_prompt.md`

---

## Database Schema

YokeFlow uses PostgreSQL with UUID-based project identification. Complete schema: [schema/postgresql/schema.sql](../schema/postgresql/schema.sql)

### Core Tables (21 total)

**projects** - Project metadata
```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    spec_content TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);
```

**epics** - Feature areas (15-25 per project)
```sql
CREATE TABLE epics (
    id SERIAL PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

**tasks** - Work items (8-15 per epic)
```sql
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    epic_id INTEGER NOT NULL REFERENCES epics(id),
    description TEXT NOT NULL,
    action TEXT,
    priority INTEGER DEFAULT 0,
    done BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

**tests** - Test cases (1-3 per task)
```sql
CREATE TABLE tests (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    description TEXT NOT NULL,
    test_code TEXT,  -- Executable test code
    passed BOOLEAN,
    last_error_message TEXT,  -- ⭐ v2.1 Phase 1
    execution_time_ms INTEGER,  -- ⭐ v2.1 Phase 1
    retry_count INTEGER DEFAULT 0,  -- ⭐ v2.1 Phase 1
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

**sessions** - Work sessions
```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_number INTEGER NOT NULL,
    session_type TEXT NOT NULL,  -- initializer, coding, review
    status TEXT NOT NULL,  -- running, completed, error, blocked
    started_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMPTZ,
    metrics JSONB DEFAULT '{}'::jsonb
);
```

### Quality System Tables ⭐ v2.1

**epic_test_failures** - Test failure tracking (Phase 2)
```sql
CREATE TABLE epic_test_failures (
    id SERIAL PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    epic_id INTEGER NOT NULL REFERENCES epics(id),
    epic_test_id INTEGER NOT NULL REFERENCES epic_tests(id),
    session_id UUID REFERENCES sessions(id),
    failed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,
    error_type TEXT,  -- test_quality, implementation_gap, flaky_test
    was_passing_before BOOLEAN DEFAULT FALSE,
    is_flaky BOOLEAN DEFAULT FALSE,
    agent_retry_count INTEGER DEFAULT 0,
    -- 22 fields total, 9 indexes
);
```

**epic_retests** - Regression testing (Phase 5)
```sql
CREATE TABLE epic_retests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    epic_id INTEGER NOT NULL REFERENCES epics(id),
    trigger_reason TEXT NOT NULL,  -- epic_interval, foundation_stale, manual
    priority_tier TEXT NOT NULL,  -- foundation, high_dependency, standard
    selected_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    tested_at TIMESTAMPTZ,
    passed BOOLEAN,
    failed_test_count INTEGER DEFAULT 0,
    total_test_count INTEGER NOT NULL,
    regression_detected BOOLEAN DEFAULT FALSE,
    stability_score DECIMAL(3,2)  -- 0.00-1.00
);
```

**project_completion_reviews** - Final verification (Phase 7)
```sql
CREATE TABLE project_completion_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    overall_score INTEGER NOT NULL,  -- 1-100
    coverage_percentage DECIMAL(5,2) NOT NULL,
    recommendation TEXT NOT NULL,  -- COMPLETE, NEEDS_WORK, FAILED
    executive_summary TEXT,
    detailed_analysis JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

**session_quality_checks** - Quality metrics (Phase 1)
```sql
CREATE TABLE session_quality_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    quality_score DECIMAL(3,1),  -- 0.0-10.0
    error_count INTEGER DEFAULT 0,
    adherence_violations INTEGER DEFAULT 0,
    verification_rate DECIMAL(3,2),  -- 0.00-1.00
    issues_found TEXT[],
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

### Views (19 total)

**v_progress** - Overall project statistics
```sql
CREATE VIEW v_progress AS
SELECT
    p.id as project_id,
    COUNT(DISTINCT e.id) as total_epics,
    COUNT(DISTINCT CASE WHEN e.status = 'completed' THEN e.id END) as completed_epics,
    COUNT(DISTINCT t.id) as total_tasks,
    COUNT(DISTINCT CASE WHEN t.done = TRUE THEN t.id END) as completed_tasks,
    COUNT(test.id) as total_tests,
    COUNT(CASE WHEN test.passed = TRUE THEN test.id END) as passing_tests
FROM projects p
LEFT JOIN epics e ON e.project_id = p.id
LEFT JOIN tasks t ON t.epic_id = e.id
LEFT JOIN tests test ON test.task_id = t.id
GROUP BY p.id;
```

**v_epic_stability_metrics** - Epic stability analytics ⭐ v2.1 (Phase 5)
```sql
CREATE VIEW v_epic_stability_metrics AS
SELECT
    epic_id,
    COUNT(*) as total_retests,
    SUM(CASE WHEN passed THEN 1 ELSE 0 END) as passed_retests,
    SUM(CASE WHEN NOT passed THEN 1 ELSE 0 END) as failed_retests,
    SUM(CASE WHEN regression_detected THEN 1 ELSE 0 END) as regressions_detected,
    AVG(CASE WHEN passed THEN 1.0 ELSE 0.0 END) as avg_pass_rate,
    AVG(stability_score) as avg_stability_score
FROM epic_retests
GROUP BY epic_id;
```

**v_flaky_tests** - Identify unreliable tests ⭐ v2.1 (Phase 2)
```sql
CREATE VIEW v_flaky_tests AS
SELECT
    epic_id,
    epic_test_id,
    COUNT(*) as failure_count,
    COUNT(DISTINCT session_id) as failed_in_sessions,
    MAX(was_passing_before) as was_passing_before,
    AVG(agent_retry_count) as avg_retry_count
FROM epic_test_failures
WHERE is_flaky = TRUE
GROUP BY epic_id, epic_test_id;
```

### Migrations ⭐ v2.1

- **017**: Test execution tracking (error messages, timing, retries)
- **018**: Epic test failure tracking (22 fields, 5 views)
- **019**: Epic re-testing system (2 tables, 4 views)
- **020**: Project completion reviews (2 tables, 4 views)

See [schema/postgresql/migrations/](../schema/postgresql/migrations/) for complete migration history.
```

**v_next_task:** Next task to work on
```sql
CREATE VIEW v_next_task AS
SELECT
    t.*,
    e.name as epic_name,
    e.description as epic_description
FROM tasks t
JOIN epics e ON t.epic_id = e.id
WHERE t.done = 0
ORDER BY e.priority, t.priority
LIMIT 1;
```

**v_epic_progress:** Per-epic completion
```sql
CREATE VIEW v_epic_progress AS
SELECT
    e.*,
    COUNT(t.id) as total_tasks,
    SUM(CASE WHEN t.done = 1 THEN 1 ELSE 0 END) as completed_tasks,
    CAST(SUM(CASE WHEN t.done = 1 THEN 1 ELSE 0 END) AS FLOAT) /
        NULLIF(COUNT(t.id), 0) * 100 as completion_percentage
FROM epics e
LEFT JOIN tasks t ON e.id = t.epic_id
GROUP BY e.id;
```

**v_epics_need_expansion:** Epics with no tasks
```sql
CREATE VIEW v_epics_need_expansion AS
SELECT e.*
FROM epics e
LEFT JOIN tasks t ON e.id = t.epic_id
GROUP BY e.id
HAVING COUNT(t.id) = 0
ORDER BY e.priority;
```

### Modifying the Schema

1. Edit `schema/postgresql/schema.sql`
2. Test with a fresh database installation
3. Run `python scripts/init_database.py --docker` to apply schema

**Important:** Schema changes require a fresh database installation. Existing data cannot be migrated between versions.

---

## Security System

### Blocklist Approach

**Philosophy:** Allow everything except explicitly dangerous commands

**vs Allowlist:**
- Allowlist: Block everything, allow specific commands
- Blocklist: Allow everything, block specific commands

**Why Blocklist:**
- Development needs diverse tools
- Agent should work autonomously
- Easier to maintain (fewer commands to list)

### Implementation

File: `security.py`

```python
BLOCKED_COMMANDS = {
    "rm", "rmdir",           # File deletion
    "sudo", "su",            # Privilege escalation
    "reboot", "shutdown",    # System control
    "apt", "yum", "brew",    # Package managers
    # ... etc
}

def validate_bash_command(command: str) -> tuple[bool, str]:
    # Parse command
    # Check against blocklist
    # Special handling for pkill
    return (is_allowed, reason)
```

### Testing Security

```bash
cd tests
python test_security.py
```

Tests cover:
- Blocked commands
- Allowed commands
- pkill validation
- Edge cases

### Adding/Removing Blocked Commands

Edit `security.py`:

```python
BLOCKED_COMMANDS = {
    "rm", "rmdir",
    # Add your blocked command:
    "mycmd",
}
```

**Warning:** Be cautious when removing blocks - test thoroughly first.

---

## Observability

### Log Files

**JSONL Format** (machine-readable):
```json
{"type": "prompt", "content": "...", "timestamp": "2025-12-09T14:05:23Z"}
{"type": "assistant_text", "content": "...", "timestamp": "..."}
{"type": "tool_use", "name": "Bash", "input": {...}, "timestamp": "..."}
{"type": "tool_result", "content": "...", "is_error": false, "timestamp": "..."}
```

**TXT Format** (human-readable):
```
[14:05:23] === SESSION START ===
[14:05:23] PROMPT: (3245 chars)
[14:05:25] ASSISTANT: Let me start by...
[14:05:26] TOOL: Bash - pwd
[14:05:26] RESULT: /path/to/project
```

### QuietOutputFilter

**Quiet Mode (default):**
- Shows: Assistant text, Bash tool notifications, errors
- Hides: Tool inputs, results (unless error), thinking, system messages

**Verbose Mode (`--verbose`):**
- Shows: Everything

**Implementation:**
```python
class QuietOutputFilter:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def should_show_tool_use(self, tool_name: str) -> bool:
        if self.verbose:
            return True
        return tool_name == "Bash"  # Only Bash in quiet mode

    def should_show_tool_result(self, is_error: bool) -> bool:
        if self.verbose or is_error:
            return True
        return False
```

### Analyzing Logs

**Using analyze_logs.sh:**
```bash
./analyze_logs.sh projects/my_project

# Shows:
# - Session overview (duration, tools, errors)
# - Aggregate stats
# - Tool usage breakdown
# - Error summary
# - Blocked commands
# - Recent session preview
```

**Custom Analysis:**
```bash
# Count tool uses
jq -r 'select(.event == "tool_use") | .tool_name' logs/*.jsonl | sort | uniq -c

# Find errors
jq -r 'select(.event == "tool_result" and .is_error == true)' logs/*.jsonl

# Session durations (from individual session logs)
jq -r 'select(.event == "session_end") | .duration_seconds' logs/*.jsonl
```

**Note:** Session metrics are now stored in PostgreSQL database. Query the `sessions` table for aggregate analysis.

---

## Extending the System

### Adding Custom Prompts

1. Create new prompt file in `prompts/`
2. Add loader function to `prompts.py`:
```python
def get_my_prompt() -> str:
    return (PROMPTS_DIR / "my_prompt.md").read_text()
```
3. Call in `agent.py` when needed

### Custom MCP Server

See: [MCP Server Documentation](https://modelcontextprotocol.io/)

1. Create new MCP server (Node.js or Python)
2. Add to `client.py`:
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
3. Use tools in prompts: `mcp__my-server__tool_name`

### Custom Security Rules

**Scenario:** Want to allow `curl` only to specific domains

```python
# In security.py
ALLOWED_DOMAINS = ["api.example.com", "cdn.example.com"]

def validate_bash_command(command: str) -> tuple[bool, str]:
    parts = shlex.split(command)
    cmd = parts[0]

    if cmd == "curl":
        # Check URL in args
        for arg in parts[1:]:
            if arg.startswith("http"):
                domain = urlparse(arg).netloc
                if domain not in ALLOWED_DOMAINS:
                    return (False, f"curl blocked: domain {domain} not in allowlist")
        return (True, "")

    # ... rest of validation
```

### Web UI Customization

**Architecture:** Next.js (TypeScript/React) → FastAPI REST API → Database Abstraction Layer

**Key Directories:**
- `web-ui/src/app/` - Next.js pages and routes
- `web-ui/src/components/` - React components
- `web-ui/src/lib/` - API client and utilities
- `api/` - FastAPI backend server

**Quick changes:**

**Add new API endpoint:**
```python
# api/main.py
@app.get("/api/projects/{project_id}/my-endpoint")
async def my_endpoint(project_id: str):
    db = get_database(projects_dir / project_id)
    results = db.custom_query()
    return results
```

**Add new React component:**
```typescript
// web-ui/src/components/MyComponent.tsx
export function MyComponent({ data }: { data: MyData }) {
  return <div>{/* component code */}</div>
}
```

---

## Testing

### Test Structure

```
tests/
├── test_security.py       # Security blocklist tests
├── test_mcp.py            # MCP integration tests
├── test_mcp_direct.py     # Direct MCP tool tests
├── test_initializer.sh    # End-to-end initializer test
└── test_coding.sh         # End-to-end coding test
```

### Running Tests

**Security tests:**
```bash
cd tests
python test_security.py
```

**MCP integration:**
```bash
python test_mcp.py
```

**End-to-end:**
```bash
./test_initializer.sh my-test-project
./test_coding.sh my-test-project
```

### Writing New Tests

**Security test pattern:**
```python
def test_my_command():
    is_allowed, reason = validate_bash_command("mycmd args")
    assert is_allowed == False
    assert "blocked" in reason.lower()
```

**MCP test pattern:**
```python
async def test_my_tool():
    # Create test database
    # Initialize MCP server
    # Call tool
    # Verify results
    # Cleanup
```

---

## Development Workflow

### Making Changes

1. **Create feature branch:**
```bash
git checkout -b feature/my-enhancement
```

2. **Make changes** to relevant files

3. **Test locally:**
```bash
# Run tests
python tests/test_security.py
python tests/test_mcp.py

# Test with real project
python yokeflow.py --project-dir test-proj --max-iterations 2
```

4. **Update documentation:**
- Update this guide if architecture changes
- Update PROPOSED_ENHANCEMENTS.md if adding features
- Update relevant docs in `docs/`

5. **Commit:**
```bash
git add .
git commit -m "Description of changes"
```

6. **Create PR or merge:**
```bash
git checkout main
git merge feature/my-enhancement
```

### Best Practices

**Code Style:**
- Python: Follow PEP 8
- TypeScript: Use ESLint
- Shell scripts: Use ShellCheck

**Documentation:**
- Update docs when changing APIs
- Add inline comments for complex logic
- Keep CLAUDE.md up to date for context restoration

**Testing:**
- Test security changes thoroughly
- Test MCP changes with real database
- End-to-end test for major changes

**Git Commits:**
- Descriptive commit messages
- Group related changes
- Reference issues if applicable

---

## Common Development Tasks

### Debugging MCP Server

**Enable debug logging:**
```typescript
// In mcp-task-manager/src/index.ts
console.error("DEBUG: tool called with args:", args);
```

**View stderr:**
```bash
# MCP server logs go to stderr, visible in agent logs
grep "MCP" projects/my_project/logs/session_*.txt
```

**Test MCP server directly:**
```bash
cd tests
python test_mcp_direct.py
```

### Debugging Security Issues

**See what command was blocked:**
```bash
# Check logs
./analyze_logs.sh projects/my_project

# Look for "blocked" in JSONL
jq -r 'select(.type == "tool_result" and .is_blocked == true)' logs/*.jsonl
```

**Temporarily allow command for testing:**
```python
# In security.py, comment out the block:
BLOCKED_COMMANDS = {
    # "mycmd",  # Temporarily allowed for testing
}
```

### Debugging Database Issues

**Inspect database:**
```bash
# Connect to PostgreSQL
psql $DATABASE_URL

# View schema
\d projects
\d epics
\d tasks
\d tests

# Query progress
SELECT * FROM v_progress;
SELECT * FROM v_epic_progress;

# Exit
\q
```

**Check database connection:**
```bash
# Test connection
psql $DATABASE_URL -c "SELECT version();"

# List all projects
psql $DATABASE_URL -c "SELECT id, name, created_at FROM projects;"
```

**Reset project data (keeps schema):**
```bash
# Use reset_project.py script
python reset_project.py --project-dir my_project --yes
```

---

## Verification System (v2.0)

YokeFlow includes an automatic verification system that ensures task quality before marking them complete.

### Overview

The verification system (`server/verification/`) provides:
- **Automatic test generation** for completed tasks
- **Task verification** with retry logic (max 3 attempts)
- **Epic validation** across multiple tasks
- **Failure analysis** with suggested fixes

### Components

**server/verification/task_verifier.py** (580 lines)
- Verifies individual tasks before completion
- Generates and runs tests automatically
- Retry logic with failure analysis
- Integration with MCP tool interception

**server/verification/test_generator.py** (480 lines)
- Auto-generates tests based on task description
- Supports: unit, integration, E2E, browser, API tests
- Context-aware test creation using Claude SDK

**server/verification/epic_validator.py** (700 lines)
- Validates entire epics after all tasks complete
- Integration testing across task boundaries
- Creates rework tasks for failures
- Max 3 rework iterations

**server/verification/integration.py** (413 lines)
- Intercepts MCP `update_task_status` calls
- Runs verification before allowing completion
- Tracks file modifications per task
- Configuration-driven enable/disable

### How It Works

```python
# When agent tries to mark task complete
MCP call: update_task_status(task_id=42, done=True)
    ↓
Interception by verification system
    ↓
Generate tests for task (test_generator.py)
    ↓
Run tests (task_verifier.py)
    ↓
If pass → Allow task completion
If fail → Block completion, analyze failure, retry (max 3x)
    ↓
After all tasks in epic complete → Epic validation
```

### Configuration

Enable/disable in `.yokeflow.yaml`:

```yaml
verification:
  enabled: true                    # Enable task verification
  auto_retry: true                  # Auto-retry failed tests
  max_retries: 3                    # Max retry attempts
  test_timeout: 30                  # Timeout per test (seconds)
  generate_unit_tests: true         # Generate unit tests
  generate_api_tests: true          # Generate API tests
  generate_browser_tests: true      # Generate browser tests
  track_file_modifications: true    # Track files modified
```

### Database Tables

Verification results are persisted in PostgreSQL:

- `task_verifications` - Verification attempts and results
- `epic_validations` - Epic-level validation results
- `generated_tests` - Catalog of auto-generated tests
- `verification_history` - Audit trail

See `schema/postgresql/016_verification_system.sql` for complete schema.

### Testing

55 comprehensive tests cover the verification system:
- `test_task_verifier.py` (11 tests)
- `test_epic_validator.py` (13 tests)
- `test_test_generator.py` (15 tests)
- `test_verification_simple.py` (16 tests)

### Related Documentation

- [verification-system.md](verification-system.md) - User guide for verification features
- [configuration.md](configuration.md) - Configuration options
- [testing-guide.md](testing-guide.md) - Test suite documentation

---

## Performance Considerations

### Database Queries

**Use views for complex queries:**
- Views are pre-defined, optimized
- Better than ad-hoc queries from agent

**Add indexes if needed:**
```sql
CREATE INDEX idx_tasks_epic_id ON tasks(epic_id);
CREATE INDEX idx_tests_task_id ON tests(task_id);
```

### MCP Server

**Keep it lightweight:**
- Minimal dependencies
- Fast database queries
- No long-running operations

**Connection pooling:**
Currently uses single connection - fine for single-user.
For multi-user: implement connection pool.

### Web UI

**Status:** ✅ Production-ready (v2.0)

**Features:**
- JWT authentication with development mode
- Real-time WebSocket updates (session progress, tool uses)
- Task detail views with epic/task/test hierarchy
- Quality dashboard with session metrics
- Session logs viewer (TXT/JSONL)
- Project completion celebration banner
- Toast notifications and confirmation dialogs
- Environment variable editor

**Performance:**
- WebSocket for instant updates (no polling)
- Connection pooling implemented (10-20 connections)
- Async operations throughout

**Scaling:**
For high traffic: consider adding Redis cache for API responses.

---

## Deployment

### Local Development

Current state - works great for local development.

### Docker Deployment

**Recommended for production:**

```dockerfile
FROM python:3.11

# Install Node.js for MCP server
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
RUN apt-get install -y nodejs

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy code
COPY . /app
WORKDIR /app

# Build MCP server
RUN cd mcp-task-manager && npm install && npm run build

# Build Next.js web UI
RUN cd web-ui && npm install && npm run build

# Run API server (or agent CLI)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8010"]
# Alternative: CMD ["python", "yokeflow.py", "--project-dir", "/workspace"]
```

**Volume mounts:**
```bash
docker run -v $(pwd)/projects:/workspace yokeflow
```

### Cloud Deployment

**Current Status:** API-first architecture is complete and ready for deployment.

**Architecture:**
- FastAPI REST API server (port 8010)
- Next.js Web UI (port 3010, or static export)
- WebSocket for real-time updates
- Database abstraction layer (PostgreSQL-ready)

**Deployment Recommendations:**
- Use Digital Ocean, AWS, or similar for API server
- Deploy Next.js as static site or Node.js server
- ✅ JWT authentication implemented (production-ready)
- ✅ PostgreSQL in production (async operations, connection pooling)

See [TODO.md](../TODO.md) and [api/README.md](../api/README.md) for details.

---

## Additional Resources

### YokeFlow Documentation

**Core Documentation:**
- [CLAUDE.md](../CLAUDE.md) - Quick reference guide
- [README.md](../README.md) - Platform overview
- [QUICKSTART.md](../QUICKSTART.md) - 5-minute setup guide

**v2.1 Quality System:**
- [QUALITY_SYSTEM_SUMMARY.md](../QUALITY_SYSTEM_SUMMARY.md) - Phase-by-phase implementation (Phases 0-8)
- [docs/quality-system.md](quality-system.md) - Complete quality system documentation
- [docs/testing-guide.md](testing-guide.md) - Testing practices and tools

**API & Configuration:**
- [docs/api-usage.md](api-usage.md) - REST API reference (60+ endpoints)
- [docs/configuration.md](configuration.md) - Configuration options (`.yokeflow.yaml`)
- [docs/mcp-usage.md](mcp-usage.md) - MCP tools documentation (20+ tools)

**Database & Architecture:**
- [schema/postgresql/schema.sql](../schema/postgresql/schema.sql) - Complete database schema
- [docs/postgres-setup.md](postgres-setup.md) - PostgreSQL setup guide
- [docs/verification-system.md](verification-system.md) - Verification system guide

**Specialized Topics:**
- [docs/input-validation.md](input-validation.md) - Validation framework (19 models)
- [docs/ai-spec-generation.md](ai-spec-generation.md) - AI-powered spec generation

### External Documentation

**Core Technologies:**
- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/) - Model Context Protocol
- [Claude SDK Documentation](https://docs.anthropic.com/claude/docs/claude-code) - Claude Agent SDK
- [PostgreSQL Documentation](https://www.postgresql.org/docs/) - PostgreSQL database
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - Python web framework
- [Next.js Documentation](https://nextjs.org/docs) - React framework

**Python Libraries:**
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/) - Async PostgreSQL driver
- [Pydantic Documentation](https://docs.pydantic.dev/) - Validation library

---

**Version**: 2.1.0 | **Last Updated**: February 2, 2026
