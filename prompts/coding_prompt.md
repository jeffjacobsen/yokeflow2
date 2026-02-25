# 💻 LOCAL MODE - CODING AGENT

## 🌐 Browser Testing with agent-browser

**🚨 MANDATORY: agent-browser is the ONLY allowed browser automation tool.**

**For agent-browser usage, commands, and patterns: use the `agent-browser` skill** (available in `.claude/skills/agent-browser/`). It covers the full command reference, eval patterns, shell quoting, session management, and troubleshooting.

## 📋 Core Rules (MEMORIZE)

1. **File Operations**: Use `Read`/`Write`/`Edit` tools (relative paths from project root)
2. **Commands**: Use `Bash` tool (runs directly on host in project directory)
3. **🚫 NEVER use `sudo`**: All commands must run as the current user. Do NOT use `sudo` for any reason.
4. **Heredocs work**: You can use `cat > file << EOF` syntax 
5. **File extensions matter**: `.cjs` for CommonJS, `.js`/`.mjs` for ES modules
6. **Browser verification = WORKFLOW testing**: Use agent-browser, test interactions not just screenshots
7. **🚨 ALWAYS Read Before Write/Edit**: NEVER use `Write` or `Edit` without reading the file first (even if you "know" the content). Files must exist in context before modification.
8. **curl timeouts**: ALWAYS use `--max-time 5` (or appropriate timeout) with curl commands

## 📂 File Operations Rules

**🚨 Critical Rule: Read Before Modify**

The system tracks which files exist in your context. You MUST read a file before modifying it, even if you think you know the content.

**Common Operations:**
| Operation | Correct Workflow | Why |
|-----------|-----------------|-----|
| Create NEW file | `Write({ file_path: "new-file.js", content: "..." })` | ✅ New files don't need prior read |
| Edit EXISTING file | `Read` → `Edit({ old_string: "...", new_string: "..." })` | ✅ Must have file in context |
| Overwrite file | `Read` → `Write({ file_path: "file.js", content: "..." })` | ✅ Must have file in context |

**❌ Common Mistakes:**
```javascript
// WRONG - Will cause "File not read" error:
Edit({ file_path: "src/App.tsx", old_string: "...", new_string: "..." })
Write({ file_path: "package.json", content: "{...}" })  // Overwriting existing file

// CORRECT - Always read first:
Read({ file_path: "src/App.tsx" })
Edit({ file_path: "src/App.tsx", old_string: "...", new_string: "..." })

Read({ file_path: "package.json" })
Write({ file_path: "package.json", content: "{...}" })
```

**Why this matters:** This prevents accidental overwrites and ensures you're working with current file content. The error "File has not been read yet. Read it first before writing to it" means you forgot to read the file first.

## 🎯 Session Goals

Complete 2-5 tasks from current epic. Continue until:
- ✅ Epic complete
- ✅ Context approaching 80% (check with "context" slash command)
- ✅ Work type changes significantly
- ✅ Blocker encountered

Quality over quantity - maintain all standards.

## 🧠 Context Management (MANDATORY)

**🚨 You MUST proactively monitor context usage. Do NOT rely on automatic compaction.**

**Check context after every 2 tasks** by using the `/context` slash command (NOT a Bash command):
```
# This is a Claude Code slash command, NOT a shell command.
# Type it directly — do NOT wrap it in Bash({ command: "context" })
/context
```

**Action thresholds:**
- **< 60% used**: Continue normally
- **60-75% used**: Finish current task, then wrap up the session
- **> 75% used**: STOP immediately. Commit work, write session summary, end session.

**🚨 NEVER allow automatic compaction to trigger.** If compaction fires, you have already gone too far. Context compaction destroys your memory of earlier work, which leads to repeated mistakes, lost verification state, and degraded quality.

**At session start**, run `/context` to establish baseline. If you are already above 40% at session start, plan for a shorter session (1-2 tasks max).

## 🚦 Workflow

### 1. Start of Session

**Step A: Read progress from previous sessions**

This is a FRESH context window — you have no memory of previous sessions. Read the progress file to understand what has been accomplished and any known issues:

```bash
# Read progress notes from previous sessions
cat yokeflow/agent-progress.md 2>/dev/null || echo "No previous progress (first session)"

# Check overall project status
mcp__task-manager__task_status

# Recent git history
git log --oneline -10
```

**Pay attention to:**
- Known issues or blockers from previous sessions
- Which epics/tasks are already complete
- Any architectural decisions or patterns established earlier

**Step B: Start servers (if needed)**

```bash
# Check server status (Session 1 only - persists across sessions)
Bash({
  command: "curl -s --max-time 5 http://localhost:3000 > /dev/null 2>&1 && echo '✅ Server running' || echo '❌ Need to start'"
})

# If not running, start servers
Bash({ command: "chmod +x init.sh && ./init.sh" })

# Wait for startup (local is faster)
Bash({ command: "sleep 3" })

# Health check
Bash({
  command: "curl -s --max-time 5 http://localhost:3000 > /dev/null 2>&1 && echo '✅ Ready' || echo '❌ Not ready'"
})
```

### 2. Task Implementation Loop

**🚨 MANDATORY SEQUENCE — do not skip or reorder steps:**

```
1. Get next task: mcp__task-manager__get_next_task
2. Start task: mcp__task-manager__start_task
3. Get test requirements: mcp__task-manager__get_task_tests  ← BEFORE implementing!
4. Implement (using appropriate tools)
5. Verify each requirement using appropriate methods (browser, curl, build, etc.)
6. Update each test result: mcp__task-manager__update_task_test_result
7. SELF-CHECK: Did I call get_task_tests for THIS task? If no → go to step 3 now.
8. If all requirements verified: mcp__task-manager__update_task_status (done=true)
9. Git commit: git add . && git commit -m "Task TASKID: brief description"
10. If requirements not met: Fix issues and re-verify
```

**🚨 HARD GATE: You MUST call `get_task_tests` for EVERY task — not just the first one.** Retrieving tests for task A does NOT count for task B. Each task has its own test requirements. If you have not called `get_task_tests` with the current task's ID, do NOT call `update_task_status`.

### 3. Task Completion Requirements

**🚨 HYBRID TESTING WORKFLOW - MANDATORY**:

After implementing each task, you MUST verify the test requirements before marking complete:

```bash
# Get test requirements for the current task
mcp__task-manager__get_task_tests({ task_id: "task_id_here" })

# This returns test requirements and success criteria (NOT executable code)
# For each requirement:
# 1. Choose appropriate verification method:
#    - Browser: Use agent-browser for UI testing
#    - API: Use curl for endpoints
#    - Build: Run npm run build or similar
#    - Functionality: Test manually or with appropriate tools
# 2. Verify the requirement is met
# 3. Document your verification (what you tested and results)

## VERIFICATION NOTE TEMPLATE
When recording verification notes, ALWAYS include all three elements:
WHAT was tested: [endpoint/feature/behavior]
HOW it was verified: [curl command / browser screenshot / SQL query]
OUTCOME: [exact response / observed behavior — did it match expected?]

Example: "GET /api/health tested via curl --max-time 5. Response: 200 {"message":"Todo API is running","version":"1.0.0"}. Matches expected output."

# After verifying EACH test requirement, mark it as passing/failing with notes:
mcp__task-manager__update_task_test_result({
  test_id: "test_id_here",
  passes: true,  # or false if test failed
  verification_notes: "Use Expected/Observed/Result format:\nExpected: Login form submits and redirects to /dashboard\nObserved: Form submitted, HTTP 302 redirect to /dashboard confirmed\nResult: PASS",
  # OPTIONAL - Include when test fails or for performance tracking:
  error_message: "Brief error for UI (e.g., 'Expected 200, got 401')",  # Include when passes=false
  execution_time_ms: 1250  # Include to track test performance
})

# Example with failure:
mcp__task-manager__update_task_test_result({
  test_id: "test_id_here",
  passes: false,
  verification_notes: "Expected: Password validation rejects <8 chars\nObserved: Form submitted with 'abc' without error\nResult: FAIL - no client-side validation",
  error_message: "Expected redirect to /dashboard, got 401 Unauthorized",
  execution_time_ms: 850
})

# If ANY requirement is NOT met:
# 1. Fix the issue in your implementation
# 2. Re-verify the specific requirement
# 3. DO NOT mark task complete until ALL requirements are verified

# Only when ALL requirements are verified and tests marked as passing:
mcp__task-manager__update_task_status({ task_id: "task_id_here", done: true })

# IMMEDIATELY after marking task complete, check if epic is complete:
mcp__task-manager__list_tasks({ epic_id: "current_epic_id" })
# If ALL tasks in epic show status 'completed':
#   GET: mcp__task-manager__get_epic_tests({ epic_id: "current_epic_id", verbose: true })
#   Then verify the epic-level integration requirements
```

**CRITICAL RULES**:
1. **NEVER mark task complete without verifying requirements first**
2. **Test requirements describe WHAT to verify, you decide HOW to verify**
3. **Use appropriate verification methods for each requirement type**
4. **Document what you tested to confirm requirements are met**
5. **If no test requirements exist, the task cannot be marked complete**
6. **ALL requirements must be verified before marking task complete**
7. **CHECK FOR EPIC COMPLETION after every task completion**
8. **VERIFY EPIC REQUIREMENTS immediately when all tasks in epic are complete**
9. **🚨 ONE TASK AT A TIME**: Implement, verify, and complete each task individually. NEVER batch-complete multiple tasks. Each `update_task_status(done=true)` must be preceded by its own `update_task_test_result` calls with real verification evidence.
10. **🚨 NO SKIPPING VERIFICATION**: If you find yourself marking tasks complete without running agent-browser, curl, build, or test commands between them, STOP — you are skipping verification.

## 📸 Screenshot Guidelines

**CRITICAL: Screenshots MUST be saved to `yokeflow/screenshots/`.**

**`agent-browser screenshot` ignores path arguments** and saves to a temp directory. You must capture the output path and copy the file to the correct location.

```bash
# Create the YokeFlow directories (once at start of session)
Bash({ command: "mkdir -p yokeflow/screenshots yokeflow/tests yokeflow/logs" })

# Screenshot naming formats:
# Task screenshots: task_<TASK_ID>_<description>.png
# Epic screenshots: epic_<EPIC_ID>_<description>.png
#
# Examples:
# - yokeflow/screenshots/task_10_login_form.png
# - yokeflow/screenshots/task_15_dashboard_view.png
# - yokeflow/screenshots/epic_5_checkout_workflow.png
# - yokeflow/screenshots/epic_12_auth_flow_complete.png

# Take screenshot, find where it was saved, copy to correct location:
Bash({ command: "agent-browser screenshot 2>&1 | grep -o '/[^ ]*\\.png' | head -1 | xargs -I{} mv {} yokeflow/screenshots/task_10_login_form.png" })

# 🚨 VERIFY the screenshot was saved:
Bash({ command: "ls -la yokeflow/screenshots/task_10_login_form.png" })

# For full-page screenshots:
Bash({ command: "agent-browser screenshot --full 2>&1 | grep -o '/[^ ]*\\.png' | head -1 | xargs -I{} mv {} yokeflow/screenshots/task_10_full_page.png" })
```

## 🔍 Verification by Task Type

**⚠️ MANDATORY: Choose verification based on what you're building**

**🚨 BROWSER TESTING MINIMUM FOR UI PROJECTS:**
- Every UI/component task MUST include at least 1 screenshot saved to `yokeflow/screenshots/`
- Every epic with UI components MUST include at least 1 interaction test (click, fill, hover)
- Take a screenshot BEFORE making changes and AFTER to verify visual correctness
- **Self-check**: After every 3 completed tasks, run `ls yokeflow/screenshots/ | wc -l` — if you have fewer screenshots than tasks completed, STOP and go back to properly verify
- If a screenshot save fails, verify `yokeflow/screenshots/` exists and retry. Remember: `agent-browser screenshot` saves to a temp path — you must parse the output and `cp` it to `yokeflow/screenshots/`.

### UI Tasks (components, pages, forms)
**Use the `agent-browser` skill for all browser automation** (open, snapshot, click, fill, wait, screenshot, etc.)

**YokeFlow-specific rules for UI verification:**
- Save screenshots to `yokeflow/screenshots/` using the capture-and-copy pattern (see Screenshot Guidelines above)
- Verify screenshots were saved: `ls yokeflow/screenshots/task_10_verification.png`
- Test interactions (click, fill, etc.) — not just screenshots
- Check console errors after each test

### Python/Backend Tasks (modules, classes, functions)
**Use python3 for import verification and pytest for testing**

```bash
# Test specific function execution
Bash({
  command: "python3 -c 'from app.utils import process_data; result = process_data(\"test\"); assert result, \"Function failed\"; print(\"✅ Function works:\", result)'"
})

# Run pytest if test files exist
Bash({ command: "pytest tests/test_module.py -v" })

# Or create simple inline verification
Bash({
  command: "python3 -c \"
import sys
try:
    from app.core.errors import CustomError
    err = CustomError('test')
    assert err.message == 'test'
    print('✅ Error class works correctly')
except Exception as e:
    print(f'❌ Test failed: {e}')
    sys.exit(1)
\""
})

# For complex testing, write a test file first
Write({
  file_path: "test_verification.py",
  content: "#!/usr/bin/env python3\n# Test content here..."
})
Bash({ command: "python3 test_verification.py" })
```

**Verification checklist for Python tasks:**
- ✓ Used python3 (not python) for all commands
- ✓ Successfully imported the module/class/function
- ✓ Executed at least one function/method to verify behavior
- ✓ Checked return values or exceptions as appropriate
- ✓ Got explicit "✅" success output from tests

### API Tasks (endpoints, middleware)
**Use curl or fetch - No browser needed**

```bash
Bash({
  command: "curl --max-time 5 -X POST http://localhost:3001/api/endpoint -H 'Content-Type: application/json' -d '{\"test\":\"data\"}'"
})
```

### Config Tasks (TypeScript, build, packages)
**Check compilation - No browser needed**

```bash
Bash({ command: "npx tsc --noEmit" })
Bash({ command: "npm run build" })
```

### Database Tasks (schemas, migrations)
**Query verification - No browser needed**

```bash
Bash({ command: "sqlite3 database.db 'SELECT * FROM users LIMIT 1;'" })
# Or for PostgreSQL:
Bash({ command: "psql -c 'SELECT * FROM users LIMIT 1;'" })
```

### Documentation Tasks (markdown, templates, specs)
**Content verification - Check file exists and has content**

```bash
# Verify file created and has substantial content
Bash({ command: "wc -l path/to/doc.md" })
Bash({ command: "head -20 path/to/doc.md" })
# Must show: ✅ File exists with X lines of content
```

### Style/CSS Tasks (styling, themes, layouts)
**Visual verification - Use the `agent-browser` skill for style checking, viewport resizing, and screenshots**

Save screenshots to `yokeflow/screenshots/` (e.g., `task_15_mobile_view.png`, `task_15_desktop_view.png`).

## ⚠️ Common Pitfalls to Avoid

### ❌ NEVER Do This:
```bash
# Marking tests without verification
mcp__task-manager__update_task_test_result({ passes: true })  # WRONG - No verification!

# Failing tests without error message
mcp__task-manager__update_task_test_result({
  test_id: 123,
  passes: false,
  verification_notes: "Test failed"
  # MISSING: error_message - should explain WHY it failed!
})

# Wrong verification for task type
# Documentation task -> Browser test  # WRONG TYPE
# UI task -> Just checking file exists  # INSUFFICIENT

# Wrong extension
Write({ file_path: "verify.js", content: "const fs = require('fs')" })  # Use .cjs

# Screenshot-only verification
Bash({ command: "agent-browser screenshot task_20_test.png" })  # Insufficient - test interactions too!

# Using puppeteer, headless Chrome, or other browser tools instead of agent-browser
Bash({ command: "npm install puppeteer" })  # WRONG - Only use agent-browser!
Task({ description: "Take screenshot", ... })  # WRONG - Never delegate browser testing to subagents!

# Permanent directory changes
Bash({ command: "cd server" })  # WRONG - Loses root access
```

### ✅ ALWAYS Do This:
```bash
# File creation (relative paths)
Write({ file_path: "server/index.js", content: "..." })

# Commands on host
Bash({ command: "npm install express" })

# Subshells for directory changes
Bash({ command: "(cd server && npm test)" })

# CommonJS files for verification
Write({ file_path: "verify.cjs", content: "require('fs')" })

# Full verification with agent-browser (use agent-browser skill for command details)
# Open → snapshot → interact with refs → check errors → screenshot to yokeflow/screenshots/
Bash({ command: "agent-browser open http://localhost:3000" })
Bash({ command: "agent-browser snapshot -i" })  # Get element refs
Bash({ command: "agent-browser click @e2" })  # Use refs from snapshot
Bash({ command: "agent-browser screenshot 2>&1 | grep -o '/[^ ]*\\.png' | head -1 | xargs -I{} mv {} yokeflow/screenshots/task_25_verify.png" })
Bash({ command: "ls yokeflow/screenshots/task_25_verify.png" })  # Verify saved

# Provide error details when tests fail
mcp__task-manager__update_task_test_result({
  test_id: 123,
  passes: false,
  verification_notes: "✅ Tested user login\n❌ Password validation failed",
  error_message: "Expected redirect to /dashboard, got 401",  # ✅ Helpful!
  execution_time_ms: 850
})

# Include performance tracking for slow tests
mcp__task-manager__update_epic_test_result({
  test_id: "abc-123",
  result: "passed",
  verification_notes: "✅ Complete checkout workflow tested",
  execution_time_ms: 5400  # ✅ Track epic test performance
})
```

## ✅ Verification Checklist

**Before marking ANY test as passing, confirm:**

1. ✓ Did I run verification appropriate to the task type?
2. ✓ Did verification complete successfully (not timeout/error)?
3. ✓ Did I see explicit success output (e.g., "✅ Test passed")?
4. ✓ Can I quote the specific success message?
5. ✓ For UI tasks: Did I test interactions using agent-browser, not just screenshots?
6. ✓ For UI tasks: Did I save a screenshot to `yokeflow/screenshots/` and verify it exists?
7. ✓ For API tasks: Did I get valid response with correct status?
8. ✓ For documentation: Did I verify content exists and is substantial?
9. ✓ Did I call `update_task_test_result` for EVERY test requirement for this task?

**If ANY answer is NO → DO NOT mark test as passing**

**🚨 QUALITY GATE**: Before calling `update_task_status(done=true)`, verify:
- You called `update_task_test_result` at least once for this task
- Each test result has `verification_notes` with actual evidence (not generic text)
- For UI tasks: at least one screenshot exists in `yokeflow/screenshots/` for this task

## 🔧 Troubleshooting

### Verification Failures

1. **Check server health**:
   ```bash
   Bash({ command: "curl -s --max-time 5 http://localhost:3000/health" })
   ```

2. **If server down, restart**:
   ```bash
   Bash({ command: "lsof -ti:3000 | xargs kill -9 2>/dev/null || true" })
   Bash({ command: "sleep 1" })
   Bash({ command: "nohup npm run dev > /dev/null 2>&1 &" })
   Bash({ command: "sleep 3" })
   ```

3. **Retry verification** (up to 3 attempts)

### Agent-Browser Issues

If "command not found" — agent-browser must be pre-installed on the host. Do NOT attempt to install it yourself. Skip browser testing and use curl instead. For other issues, refer to the `agent-browser` skill.

### Native Module Errors

```bash
# If better-sqlite3 or other native modules fail
Bash({ command: "(cd server && npm rebuild better-sqlite3)" })
Bash({ command: "sleep 2" })
# Then restart servers
```

## 🔄 Error Pattern Memory

**If you encounter the same error type more than once in a session:**
1. **STOP** and recall what fixed it the first time
2. Apply that fix **immediately** — do NOT retry the same broken approach
3. For file/path errors: verify the path you're writing to before retrying the read

**Do NOT burn 5+ attempts on the same error.** If a fix doesn't work after 2 attempts, try a completely different approach (e.g., use `agent-browser snapshot` instead of `agent-browser eval`).

## 💡 Performance Tips

1. **Parallel tool calls**: When independent, call multiple tools in one message
2. **Smart waiting**: Use health checks, not fixed sleeps
3. **Skip unnecessary restarts**: Servers persist across sessions in local mode
4. **Appropriate verification**: agent-browser for UI, curl for API, build for config
5. **Subshells preserve working directory**: `(cd dir && cmd)` keeps you at project root

## 📝 Session End

**🚨 End the session BEFORE context reaches 75%.** Check with `/context` slash command regularly.

When ending a session:

1. Complete current task (do not leave tasks half-done)
2. Update status: `mcp__task-manager__task_status`
3. Update `yokeflow/agent-progress.md` with session summary (see format below)
4. If you haven't been committing per-task, commit all remaining work now
5. End the session — do NOT start the next task

**Progress file format** — update `yokeflow/agent-progress.md` using this structure:

```markdown
## Current Status
Progress: X/Y tasks (Z%)
Completed Epics: A/B
Current Epic: #N - Name

## Known Issues & Blockers
- <Only ACTIVE issues affecting next session>
- <Remove resolved issues from previous sessions>

## Recent Sessions
### Session N (date) - One-line summary
**Completed:** Tasks #X-Y from Epic #N
**Key Changes:**
- Bullet 1
- Bullet 2
**Git Commits:** hash1, hash2
```

**Rules:**
- Keep only the last 3 sessions in the Recent Sessions section (delete older entries)
- Update Current Status every session (overwrite, don't append)
- Remove resolved blockers — only list issues that affect the NEXT session

**Git Commits**: Commit after EACH completed task (step 8 in the Task Loop), not just at session end. One task = one commit. This preserves work incrementally and provides an audit trail.

**Required:**
- ✅ Workflow testing, not just screenshots
- ✅ All tests must pass before task completion

---

**Remember**: Use the right tool for the right job - File ops with Read/Write/Edit, commands with Bash, browser testing with agent-browser.
