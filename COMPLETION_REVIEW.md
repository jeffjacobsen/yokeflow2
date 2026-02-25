# True Completion Review — Implementation Plan

*Created: February 24, 2026*
*Status: Not yet implemented*
*Reference: YOKEFLOW_FUTURE_PLAN.md Priority 1*

## Problem

No review currently verifies that the **actual generated code** implements what was requested in the spec. The init quality review (runs after Session 0) only checks whether the **plan** covers the spec — it never looks at code.

## Goal

After all coding sessions complete and the project is marked done, scan the actual generated project directory, collect test results from the DB, and verify: **"Does this code implement the spec?"**

## Existing Infrastructure (Reuse As-Is)

- `server/quality/spec_parser.py` — Parses spec into structured requirements (used by the new reviewer)
- `project_completion_reviews` / `completion_requirements` DB tables — No unique constraint on project_id; multiple reviews per project already supported
- `GET/POST /api/projects/{id}/completion-review` API endpoints — Already functional
- `CompletionReviewDashboard.tsx` — Shows score, coverage, requirements breakdown
- `db.store_completion_review()` / `db.get_completion_review()` — Store/fetch reviews

## Removed Files (Not Needed)

- `completion_analyzer.py` and `requirement_matcher.py` were deleted — they only matched spec requirements to epic/task **names** (plan-vs-spec), not actual code. The completion review needs fundamentally different logic that lives in the new `implementation_reviewer.py`.

The init quality review stays untouched. The completion review stores into the same table (latest review wins via `v_latest_completion_review` view).

## Trigger Point

`server/agent/orchestrator.py` lines ~799-823 already detect project completion (`completed_tasks >= total_tasks`) and call `mark_project_complete()`. There's a TODO comment at line ~813 for this exact feature.

---

## New Files

| File | Purpose | Est. Lines |
|---|---|---|
| `server/quality/code_analyzer.py` | Scan project files, build code inventory | ~350 |
| `server/quality/test_result_collector.py` | Gather test pass/fail evidence from DB | ~150 |
| `server/quality/implementation_reviewer.py` | Orchestrate the review (code + tests + Claude) | ~400 |
| `prompts/completion_review_prompt.md` | Claude prompt for implementation verification | ~80 |
| `tests/test_code_analyzer.py` | Tests for file scanning | ~250 |
| `tests/test_implementation_reviewer.py` | Tests for review orchestration | ~200 |

## Modified Files

| File | Change |
|---|---|
| `server/quality/integration.py` | Add `run_completion_review()` method |
| `server/agent/orchestrator.py` | Call completion review where the TODO comment is (line ~813) |
| `server/api/app.py` | Update POST endpoint to run `ImplementationReviewer` |
| `web-ui/src/components/CompletionReviewDashboard.tsx` | Show code evidence (files matched, test results) |

---

## Implementation Steps

### Step 1: Code Analyzer (`server/quality/code_analyzer.py`)

Scan `projects/<name>/` and build a structured inventory of what was actually built.

**Behavior:**
- Walk directory tree, skip `node_modules/`, `yokeflow/`, `.git/`, `__pycache__/`
- Identify source files by extension (`.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.sql`, `.html`, `.css`)
- Count files per language, total lines of code
- Regex extraction per file:
  - **Functions/methods**: `def name(`, `function name(`, `const name =`, arrow functions
  - **Classes**: `class Name`, React class components
  - **Routes/endpoints**: `app.get('/path'`, `router.post(`, `@app.route(`, Next.js `app/` pages
  - **React components**: `function ComponentName(`, `export default function`
  - **Database models**: `CREATE TABLE`, `class Model(Base)`, Prisma `model`
  - **Exports**: `module.exports`, `export default`, `export { }`

**Output:**
```python
@dataclass
class CodeArtifact:
    name: str           # e.g. "getUserById"
    artifact_type: str  # "function", "class", "route", "component", "model"
    file_path: str      # relative to project root
    line_number: int
    language: str       # "python", "javascript", "typescript"
    details: str        # e.g. "GET /api/users/:id" for routes

@dataclass
class CodeInventory:
    project_path: str
    files: List[dict]          # {path, language, lines}
    artifacts: List[CodeArtifact]
    summary: dict              # {total_files, total_lines, languages, route_count, component_count, ...}
```

### Step 2: Test Result Collector (`server/quality/test_result_collector.py`)

Query the database for actual test execution outcomes.

**Behavior:**
- Fetch all tests for the project grouped by task/epic
- Check `tests.status` field (passed/failed/pending/skipped)
- Check `task_verifications` for verification results
- Build per-task summary: "3/3 tests passed", "1/2 tests failed"

**Output:**
```python
@dataclass
class TaskTestEvidence:
    task_id: int
    task_name: str
    epic_id: int
    tests_passed: int
    tests_failed: int
    tests_pending: int
    test_details: List[dict]  # {test_name, status, error_message}

@dataclass
class TestEvidence:
    total_tests: int
    passed: int
    failed: int
    pending: int
    pass_rate: float           # 0.0-1.0
    by_task: List[TaskTestEvidence]
    by_epic: dict              # epic_id -> {passed, failed, pending}
```

### Step 3: Implementation Reviewer (`server/quality/implementation_reviewer.py`)

Orchestrate the full completion review.

**Flow:**
1. Parse spec with existing `SpecParser` → requirements
2. Run `CodeAnalyzer` on project directory → code inventory
3. Run `TestResultCollector` → test evidence
4. For each spec requirement:
   - Keyword-match against code artifacts (file names, function names, route paths, component names)
   - Check if matched tasks' tests passed
   - Assign confidence score
5. Call Claude with `completion_review_prompt.md`:
   - Spec text
   - Code inventory summary
   - Test results summary
   - Requirement-to-code matching table
6. Calculate score:
   - **40% code presence** — do matching code artifacts exist?
   - **30% test pass rate** — did related tests actually pass?
   - **30% Claude assessment** — does Claude think the code implements the spec?
7. Store via `db.store_completion_review()` — same table/shape as init review

**Output:** Same dict shape as what `store_completion_review()` expects so all downstream code (DB storage, API, UI) works unchanged. The `implementation_notes` field on each requirement match carries the code evidence (which files/functions matched).

### Step 4: Completion Review Prompt (`prompts/completion_review_prompt.md`)

Claude prompt for evaluating implementation completeness.

**Receives:**
- Original specification (truncated to 5000 chars)
- Code inventory: file count, languages, routes, components, models
- Test results: pass rate, failures, per-epic breakdown
- Requirement matching table: each requirement with matched code artifacts and test status

**Asks Claude to evaluate:**
1. Executive Summary (2-3 sentences)
2. Implementation Coverage — which requirements are implemented, which are missing
3. Test Verification — are tests passing for implemented features
4. Code Quality Observations — structural issues, missing error handling, etc.
5. Missing Features — what the spec asked for but code doesn't have
6. Final Verdict: COMPLETE / NEEDS_WORK / FAILED

### Step 5: Wire into Orchestrator

**`server/agent/orchestrator.py`** — Replace the TODO at line ~813:
```python
if total_tasks > 0 and completed_tasks >= total_tasks:
    logger.info(f"Project complete! All {total_tasks} tasks done.")
    await db.mark_project_complete(project_id)
    # Run true completion review
    await self.quality.run_completion_review(project_id, db)
```

**`server/quality/integration.py`** — Add method:
```python
async def run_completion_review(self, project_id: str, db) -> Optional[str]:
    """Run implementation-vs-spec verification after project completion."""
    reviewer = ImplementationReviewer()
    review = await reviewer.review_implementation(project_id, db)
    review_id = await db.store_completion_review(project_id, review)
    return review_id
```

Non-blocking — exceptions logged but don't break the flow.

### Step 6: Update API

**`server/api/app.py`** — Update `POST /api/projects/{id}/completion-review`:
- Check if project has `completed_at` set
- If completed: run `ImplementationReviewer` (code-vs-spec)
- If not completed: return 400 error (completion review requires a finished project)

### Step 7: Update Web UI

**`CompletionReviewDashboard.tsx`** — Enhancements:
- Show "Code Evidence" section in requirement details: which files/functions matched
- Show test pass/fail badges per requirement (green check / red X)
- Add code inventory summary card at top: X files, Y routes, Z components, N lines of code
- Existing score/coverage/section breakdown works unchanged

### Step 8: Tests

**`tests/test_code_analyzer.py`:**
- Test file walking with exclusion patterns
- Test function/class/route/component regex extraction per language
- Test with mock project directory structure
- Test edge cases: empty project, binary files, deeply nested dirs

**`tests/test_implementation_reviewer.py`:**
- Test full review flow with mocked CodeAnalyzer, TestResultCollector, SpecParser
- Test scoring calculation
- Test Claude prompt generation
- Test result shape matches what DB/API expect

---

## Estimated Effort: 12-16h

| Step | Effort |
|---|---|
| 1. Code Analyzer | 3-4h |
| 2. Test Result Collector | 1-2h |
| 3. Implementation Reviewer | 3-4h |
| 4. Completion Review Prompt | 1h |
| 5. Orchestrator Integration | 30min |
| 6. API Update | 30min |
| 7. UI Update | 1-2h |
| 8. Tests | 2-3h |

## Key Design Decisions

1. **Same DB table** — No schema migration needed. The completion review stores into `project_completion_reviews` just like the init review. The latest review (by `created_at`) is the one shown.

2. **Same output shape** — `ImplementationReviewer` returns the dict structure that `store_completion_review()` expects, so the API and UI work without changes.

3. **Code evidence in `implementation_notes`** — Each requirement match has an `implementation_notes` text field in the DB. The reviewer fills this with matched file paths, function names, and test results.

4. **Regex-based analysis, not AST** — Full AST parsing is fragile across languages. Regex patterns for common constructs (function defs, route declarations, component exports) are good enough for requirement matching.

5. **Claude as final judge** — The code/test matching provides structured evidence, but Claude makes the holistic assessment. This handles edge cases that keyword matching can't.

6. **Non-blocking** — Same pattern as init review. If the completion review fails, the project is still marked complete.
