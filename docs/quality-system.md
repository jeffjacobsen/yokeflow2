# Quality System

YokeFlow's quality system monitors coding sessions, scores quality in real-time, and triggers AI-powered deep reviews when issues are detected.

---

## Components

### Metrics Collection

The `MetricsCollector` (`server/utils/metrics_collector.py`) tracks session activity in real-time:

- **Tool usage** — counts and categorization
- **Error patterns** — repeated errors, recovery attempts
- **Task type classification** — UI, API, CONFIG, DATABASE, INTEGRATION
- **Verification tracking** — whether the right test method was used for each task type
- **Adherence violations** — prompt compliance issues
- **Session progression** — hourly performance trends

At session end, metrics are stored in the `sessions.metrics` JSONB column.

### Quality Scoring

Quality is scored 0–10 based on:

- **Error rate** — high error rates reduce the score (up to -5)
- **Verification appropriateness** — mismatched verification methods (up to -3)
- **Browser verification** — UI tasks should use browser testing (up to -2)
- **Adherence violations** — prompt compliance issues (up to -2)

Scoring logic is in `server/quality/metrics.py`.

### Deep Reviews

AI-powered reviews are triggered automatically when a session shows quality issues:

- Quality score below 7
- Error rate above 10%
- 30+ errors in a session
- Score/error mismatch (high score despite many errors)
- 5+ adherence violations
- Low verification rate (below 50%)
- Repeated errors (same error 3+ times)

Reviews are stored in the `session_deep_reviews` table and include specific recommendations. The trigger logic is in `server/utils/observability.py`.

### Test Tracking

Tests are created during initialization (Session 0) with requirements and success criteria. During coding sessions:

- Agents verify tasks using MCP tools (`update_test_result`, `update_epic_test_result`)
- Pass/fail status, verification notes, and execution time are recorded
- Results are stored in `task_tests` and `epic_tests` tables

### Completion Reviews

AI-powered verification that a project meets its original specification:

- Specification parser extracts requirements from the spec file
- Requirement matcher maps requirements to epics, tasks, and tests
- Claude generates an overall score (1–100), coverage percentage, and recommendation
- Results stored in `project_completion_reviews` and `completion_requirements` tables

Triggered via API: `POST /api/projects/{id}/completion-review`

### Prompt Improvements

Cross-project analysis that identifies patterns in deep reviews and generates concrete prompt improvement proposals:

- Extracts common recommendations by theme from deep reviews
- Generates proposals with confidence scores
- Web UI dashboard for viewing and managing proposals
- Proposals can be applied directly to prompt files

See `server/quality/prompt_analyzer.py` and `server/api/routes/prompt_improvements.py`.

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `sessions` | Session records with `metrics` JSONB column |
| `task_tests` | Task-level test requirements and results |
| `epic_tests` | Epic-level test requirements and results |
| `session_deep_reviews` | AI review results and recommendations |
| `project_completion_reviews` | Project completion verification |
| `completion_requirements` | Individual requirement tracking |
| `prompt_improvement_analyses` | Extracted recommendations |
| `prompt_proposals` | Consolidated improvement proposals |

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/sessions/{id}/quality-review` | Trigger quality review |
| `GET /api/projects/{id}/quality-metrics` | Quality metrics summary |
| `GET /api/projects/{id}/deep-reviews` | List deep reviews |
| `GET /api/projects/{id}/review-stats` | Review statistics |
| `POST /api/projects/{id}/trigger-reviews` | Batch trigger reviews |
| `GET /api/projects/{id}/completion-review` | Get latest completion review |
| `POST /api/projects/{id}/completion-review` | Trigger completion review |

See [api-usage.md](api-usage.md) for the complete API reference.

## MCP Tools

- `get_task_tests` — returns test requirements for a task
- `get_epic_tests` — returns test requirements for an epic
- `update_test_result` — updates test with pass/fail and verification notes
- `update_epic_test_result` — updates epic test results

## Key Files

| File | Purpose |
|------|---------|
| `server/utils/metrics_collector.py` | Real-time session metrics |
| `server/quality/metrics.py` | Quality scoring |
| `server/quality/reviews.py` | Deep review system |
| `server/quality/integration.py` | Quality system integration |
| `server/quality/spec_parser.py` | Specification parsing |
| `server/quality/prompt_analyzer.py` | Prompt improvement analysis |
| `server/utils/observability.py` | Session logging and review triggers |
