# Improvement Ideas

## Priority 1: Brownfield End-to-End Testing (4-6h)

**Status**: Feature implemented (v2.2) but not tested in a real workflow

The brownfield pipeline — import codebase, analyze, create scoped roadmap, implement changes on a feature branch — has 43 unit/integration tests but has not been validated end-to-end with a real project.

**Testing Plan**:
- Import a real GitHub repository and verify analysis output
- Run Session 0 and confirm scoped epics/tasks match change spec
- Run coding sessions and verify changes stay on feature branch
- Test rollback functionality
- Validate regression test safety (existing tests run before/after changes)

**Key Files**:
- `server/agent/codebase_import.py` — Import & analysis engine
- `server/agent/orchestrator.py` — `create_brownfield_project()`, `rollback_brownfield_changes()`
- `prompts/initializer_prompt_brownfield.md`, `prompts/coding_preamble_brownfield.md`

---

## Priority 2: GitHub Push & PR Integration (6-8h)

**Goal**: Complete the brownfield workflow with automated push and PR creation

**Features**:
- Push brownfield changes to remote from Web UI
- Auto-generate PR descriptions from completed tasks/epics
- `gh pr create` integration
- API endpoints: `/api/projects/{id}/push`, `/api/projects/{id}/create-pr`
- Web UI buttons for push and PR creation

---

## Priority 3: Session Checkpoint Integration (4-6h)

**Status**: Infrastructure complete (`server/agent/checkpoint.py`, 420+ lines, 19 tests, DB migration 012) but not fully wired into the orchestrator for automatic use.

**Remaining Integration**:
- Auto-create checkpoints at task and epic completion
- Resume from checkpoint after orchestrator crash or error
- Wire into epic test blocking (quality system)

---

# Priority 5: Non-UI Project Support (15-18h)

**Goal**: Support backends, APIs, libraries, CLI tools, and data processing applications. Smarter test generation based on task type. Skip browser tests for non-UI code, generate performance tests for critical paths, mock generation for external dependencies.

### 1: Project Type Detection (3-4h)
Detect project type from spec or codebase. Support REST/GraphQL/gRPC APIs, Python libraries, npm packages, CLI tools, data pipelines, batch processors.

### 2: Non-UI Testing Strategies (8-10h)
API endpoint testing, unit test generation for libraries, CLI command testing, integration test generation, performance testing for data pipelines, contract testing for APIs.

### 3: Browser-Independent Verification (4h)
Adapt verification system for non-UI code. HTTP client testing, database operation verification, file I/O verification, service health checks.

---

## Priority 6: AI & Agent Improvements (10-15h)

**Enhancements**:
- Better error recovery and debugging
- Improved code quality (reduce verbose code)
- Context management for long sessions
- Multi-file refactoring capabilities
- Intelligent test case generation
- Framework/library version selection
- Design pattern recognition and application

**Research Areas**:
- RAG integration for framework docs
- Codebase embedding for better context
- Automated code review improvements

---

## Lower Priority Enhancements

### Resource Management (10-12h)
Dynamic connection pool sizing, concurrent session limits, memory caps, automatic cleanup policies, rate limiting, resource monitoring and alerts.

### Performance Monitoring (8-10h)
Operation timing, token/cost tracking per session, database query performance, API response times, session benchmarks. Real-time dashboard, regression detection, historical trends.

### Health Check System (6-8h)
Enhanced `/health/detailed` endpoint, pool metrics, automated health checks (every 60s), alerting, self-healing, uptime tracking.

### Advanced Spec Features (8-10h)
Multiple spec files with dependency management, template bundles for common project types, spec versioning/diff, interactive spec builder in Web UI.

### Advanced Code Review (8-10h)
Automated code review on every task, security vulnerability detection, performance suggestions, code smell identification, best practices enforcement.

### Deployment Automation (10-12h)
One-click deploy to Vercel, Netlify, Railway, Heroku, AWS. Environment variable management, database provisioning, domain/SSL configuration, rollback.

### Task Manager Integration (6-8h)
Sync with Jira, Linear, GitHub Projects, Trello, Asana. Bidirectional updates, status/comment synchronization.

### Real-time Collaboration (12-15h)
Live session viewing, real-time log streaming, collaborative spec editing, chat/comments per project, notification system (webhooks, email, Slack).

### Agent Specialization (10-12h)
Specialized agents per domain: frontend, backend, database, DevOps, testing, security. Better code quality per domain and faster task completion.

### Context-Aware Testing (6-8h)


### Analytics & Monitoring (14-20h)
Project analytics (completion rate, time to complete, code quality trends, cost breakdown). Session metrics (success rate, duration, token usage, errors, retries). Quality trends (coverage, review findings, technical debt).

