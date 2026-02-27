# YokeFlow Quality System

**Last Updated:** February 2, 2026
**Version:** 4.0.0 (Complete Quality System with Completion Review)

---

## Overview

YokeFlow's quality system provides comprehensive session monitoring, automatic quality scoring, and deep AI-powered reviews. The system tracks detailed metrics in real-time, identifies quality issues, and provides actionable recommendations for improvement.

## Current State

### Working Features

1. **Real-time Metrics Collection (MetricsCollector v3.0)**
   - Tool usage tracking with categorization
   - Error pattern analysis with recovery attempts
   - Browser operation detection (agent-browser)
   - Task type classification (UI, API, CONFIG, DATABASE, INTEGRATION)
   - Prompt adherence violation detection
   - Session progression tracking (hourly metrics)
   - Verification method matching (right test for right task)

2. **Hybrid Testing System**
   - Requirements-based verification instead of rigid test code
   - Test creators generate requirements and success criteria
   - Agents verify using appropriate methods
   - Verification notes provide accountability

3. **Deep Review System**
   - Automatic triggers (every 5 sessions or quality < 7)
   - Claude-powered analysis with enhanced context
   - Specific prompt improvement recommendations
   - Database storage in `session_deep_reviews` table

4. **Quality Scoring**
   - Pre-calculated at session end
   - Stored in `sessions.metrics` JSONB column
   - Instant retrieval without log parsing

### Partially Implemented

1. **Test Execution Tracking**
   - Basic pass/fail recorded but no error details
   - No retry tracking or execution time recording

### Recently Completed (February 2026)

**Test Execution Tracking** (January 31, 2026)
- Both `task_tests` and `epic_tests` use `passes` (boolean) for consistent pass/fail tracking
- `execution_time_ms` for performance monitoring
- MCP tools: `update_task_test_result` and `update_epic_test_result`

**Test Viewer UI** (February 2, 2026)
- Epic and task tests visible with requirements in Web UI
- Show pass/fail status with verification notes
- Fixed database queries for requirements-based testing
- Tested and verified with browser automation

**Enhanced Review Triggers** (February 2, 2026)
- Removed periodic 5-session interval trigger
- Added 7 quality-based trigger conditions:
  1. Low quality score (< 7/10)
  2. High error rate (> 10%)
  3. High error count (30+)
  4. Score/error mismatch (20+ errors with score >= 8)
  5. High adherence violations (5+ violations)
  6. Low verification rate (< 50% of tasks verified)
  7. Repeated errors (same error 3+ times)

**Project Completion Review** (February 2, 2026 - **Disabled**)
- **Status**: Implemented but disabled (see YOKEFLOW_FUTURE_PLAN.md for enhancement plans)
- **Issue**: Compares spec to epics/tasks/tests (the *plan*), not the actual working *implementation*
- **Better Use**: Post-initialization plan review rather than post-completion verification
- Specification parser extracts requirements from `app_spec.txt` (450 lines, 25 tests)
- Hybrid requirement matcher (keyword + semantic matching, 550 lines) - now includes test data!
- Completion analyzer with Claude review generation (400 lines)
- Database schema (2 tables, 4 views, 5 indexes)
- REST API (5 endpoints) - manually accessible at `POST /api/projects/{id}/completion-review`
- Web UI dashboard exists but not integrated (`CompletionReviewDashboard.tsx`)
- Overall score (1-100), coverage percentage, and recommendation (complete/needs_work/failed)
- **Future**: Move to post-Session 0 for plan approval OR enhance to verify actual implementation

**Prompt Improvement Aggregation** (60% complete)
- Steps 1-2 complete: recommendation extraction and proposal generation
- Aggregates common recommendations by theme (8 themes)
- Calculates confidence scores based on evidence
- Web UI dashboard for viewing and managing proposals
- Deferred: Prompt versioning and A/B testing

### Deferred to Future

1. **Test Coverage Editing** - UI shows tests but can't edit (see YOKEFLOW_FUTURE_PLAN.md)
2. **Test Failure Dashboards** - Backend tracking complete, UI visualization deferred
3. **Checkpoint Integration** - Ready (checkpoint.py exists) but broader than quality scope
4. **Notification Integration** - Infrastructure ready (notifications.py) but enhancement only
5. **Prompt Versioning & A/B Testing** - (4-7 hours, deferred)

## Architecture

### Real-time Collection (Every Session)

```python
# MetricsCollector tracks everything during session
class MetricsCollector:
    # Basic metrics
    - tool_use_count, tool_errors, error_rate

    # Enhanced v3.0 metrics
    - verification_analysis: Task verification rates and methods used
    - error_patterns: Repeated errors with recovery attempts
    - adherence_violations: Prompt compliance issues
    - session_progression: Hourly performance trends
```

### Quality Analysis

```python
# At session end, metrics are stored in database
{
    "metrics_version": "3.0",
    "quality_score": 8,
    "tool_use_count": 150,
    "error_rate": 0.05,
    "task_types": {
        "123": {
            "type": "UI",
            "verification_method": "browser",
            "verification_appropriate": true
        }
    },
    "error_patterns": {
        "file_not_found_package.json": {
            "count": 3,
            "repeated": true,
            "avg_recovery_attempts": 2.5
        }
    },
    "adherence_violations": []
}
```

### Deep Reviews (Selective)

When triggered, the review agent receives comprehensive context:

```
## Task Type Analysis
- UI: 5 tasks
- API: 3 tasks
- CONFIG: 2 tasks

## Verification Method Matching
- Appropriate: 8/10
- Mismatched: Task 123 (UI): Used curl, expected browser

## Error Pattern Analysis
- file_not_found: 3 occurrences, avg 2.5 recovery attempts

## Prompt Adherence Issues
- Wrong Bash Command: 2 violations
- Workspace Prefix: 1 violation

## Session Progression Trends
- Hour 1: 4 tasks, 2 errors
- Hour 2: 3 tasks, 5 errors (degrading)
```

## Database Schema

### Active Tables

```sql
-- Core tables
projects                       -- Project configuration including test modes
sessions                       -- Session records with metrics JSONB
epics                         -- Epic definitions
tasks                         -- Task definitions
task_tests                    -- Test requirements (not code)
epic_tests                    -- Epic-level test requirements

-- Quality tables
session_deep_reviews          -- AI review results

-- Completion review tables
project_completion_reviews   -- Project completion verification
completion_requirements      -- Individual requirement tracking

-- Prompt improvement tables
prompt_improvement_analyses  -- Extracted recommendations
prompt_proposals             -- Consolidated improvement proposals
```

### Database Cleanup (January 31, 2026)

**Removed 34 database objects** (16 tables + 18 views):
- Unused verification tables (duplicates/unused)
- Quality gates (not implemented)
- Epic dependencies (not implemented)
- Duplicate generated_tests tables
- 18 unused views with zero references

**Current schema**: 16 tables (clean foundation)

## Quality Scoring Formula

```python
def calculate_quality_score(metrics: Dict) -> int:
    """
    Calculate 0-10 quality score based on multiple factors.
    """
    score = 10.0

    # Error rate impact (up to -5 points)
    error_rate = metrics.get('error_rate', 0)
    if error_rate > 0.1:  # >10% errors
        score -= 5
    elif error_rate > 0.05:  # >5% errors
        score -= 3
    elif error_rate > 0.02:  # >2% errors
        score -= 1

    # Verification appropriateness (up to -3 points)
    verification = metrics.get('verification_analysis', {})
    inappropriate = verification.get('inappropriate_verifications', 0)
    if inappropriate > 5:
        score -= 3
    elif inappropriate > 2:
        score -= 2
    elif inappropriate > 0:
        score -= 1

    # Browser verification for UI tasks (up to -2 points)
    task_types = metrics.get('task_types', {})
    ui_tasks = sum(1 for t in task_types.values() if t.get('type') == 'UI')
    ui_verified = sum(1 for t in task_types.values()
                     if t.get('type') == 'UI' and t.get('verification_method') == 'browser')
    if ui_tasks > 0 and ui_verified / ui_tasks < 0.5:
        score -= 2

    # Adherence violations (up to -2 points)
    violations = metrics.get('adherence_summary', {}).get('total_violations', 0)
    if violations > 10:
        score -= 2
    elif violations > 5:
        score -= 1

    return max(1, min(10, round(score)))
```

## MCP Tools

### Testing Tools
- `get_task_tests` - Returns test requirements for a task
- `get_epic_tests` - Returns test requirements for an epic
- `update_test_result` - Updates test with pass/fail, verification notes, error details
- `update_epic_test_result` - Updates epic test results, records failures automatically

### Quality Tools (Internal)
- `task_status` - Includes quality metrics in response
- Session events automatically trigger metrics collection

## Configuration

### Environment Variables
```bash
# Review configuration
DEFAULT_REVIEW_MODEL=claude-4-6
REVIEW_TRIGGER_INTERVAL=5  # Sessions between reviews
REVIEW_QUALITY_THRESHOLD=7  # Trigger if quality < this

```

### Project Settings
```sql
-- In projects table
quality_gates_enabled: boolean
auto_review_enabled: boolean
```

## API Endpoints

### Quality Metrics
- `GET /api/sessions/{id}/metrics` - Get session metrics
- `GET /api/sessions/{id}/quality` - Get quality score and analysis

### Reviews
- `POST /api/sessions/{id}/review` - Trigger deep review
- `GET /api/sessions/{id}/reviews` - Get review history
- `GET /api/projects/{id}/quality-trends` - Quality over time

### Completion Reviews
- `GET /api/projects/{id}/completion-review` - Get latest completion review
- `POST /api/projects/{id}/completion-review` - Manually trigger completion review
- `GET /api/completion-reviews` - List all reviews with filters
- `GET /api/completion-reviews/{review_id}/requirements` - Get requirements by section
- `GET /api/completion-reviews/{review_id}/section-summary` - Get section statistics

## Future Enhancements

See [YOKEFLOW_FUTURE_PLAN.md](../YOKEFLOW_FUTURE_PLAN.md) for planned enhancements:

**UI Enhancements** (Quality System section):
1. **Test Execution UI**: Error messages, performance graphs, flaky test detection
2. **Epic Test Failure UI**: Failure history dashboards, pattern visualization
3. **Notification Integration**: Webhooks, email, SMS for test failures
4. **Test Editor**: Edit test requirements and coverage analysis display
5. **Completion Review Enhancements**: Continuous tracking, spec evolution, AI-powered rework

**Completion Review Future Enhancements**:
1. Continuous requirement tracking during development (8-10h)
2. Spec evolution detection and version control (6-8h)
3. AI-powered rework task generation (10-12h)
4. Multi-spec support for versioned requirements (4-6h)
5. Machine learning improvements for matching accuracy (15-20h)

**Prompt Versioning & A/B Testing**: (4-7h, deferred)

## Troubleshooting

### Common Issues

**Quality scores seem wrong**
- Check `metrics_version` in stored metrics
- Verify MetricsCollector is tracking all events
- Review scoring formula weights

**Reviews not triggering**
- Check `REVIEW_TRIGGER_INTERVAL` setting
- Verify `auto_review_enabled` in project
- Check for review errors in logs

**Tests marked passed without verification**
- Check agent is calling `get_task_tests`
- Verify `verification_notes` being provided
- Review prompts for testing instructions

## Development Notes

### Adding New Metrics
1. Add tracking to `MetricsCollector.__init__`
2. Update tracking in relevant methods
3. Include in `get_summary()` output
4. Update `metrics_version` constant
5. Add to review context if needed

### Modifying Quality Score
1. Update `calculate_quality_score()` in `server/quality/metrics.py`
2. Test with various metric combinations
3. Verify scores align with expectations
4. Update documentation

### Database Migrations
- Use numbered migration files
- Always backup before schema changes
- Test rollback procedures
- Update this documentation

---

For implementation details and code examples, see the source files in `server/quality/` and `server/utils/metrics_collector.py`.
