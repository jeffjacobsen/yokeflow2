# Improvement Ideas

## Brownfield End-to-End Testing

The brownfield pipeline (import codebase, analyze, create scoped roadmap, implement changes on a feature branch) has unit tests but has not been validated end-to-end with a real project.

- Import a real GitHub repository and verify analysis output
- Run Session 0 and confirm scoped epics/tasks match change spec
- Run coding sessions and verify changes stay on feature branch
- Test rollback functionality
- Validate regression test safety (existing tests run before/after changes)

Key files: `server/agent/codebase_import.py`, `server/agent/orchestrator.py`, `prompts/initializer_prompt_brownfield.md`, `prompts/coding_preamble_brownfield.md`

---

## GitHub Push & PR Integration

Complete the brownfield workflow with automated push and PR creation. Push changes to remote from Web UI, auto-generate PR descriptions from completed tasks/epics, `gh pr create` integration.

---

## Session Checkpoint Integration

Infrastructure is complete (`server/agent/checkpoint.py`, database table `session_checkpoints`) but not fully wired into the orchestrator for automatic use. Remaining: auto-create checkpoints at task/epic completion, resume from checkpoint after crash.

---

## Non-UI Project Support

Support backends, APIs, libraries, CLI tools, and data processing applications. Smarter test generation based on task type — skip browser tests for non-UI code, generate API/unit/integration tests instead.

- Project type detection from spec or codebase
- Non-UI testing strategies (API endpoint testing, CLI testing, contract testing)
- Browser-independent verification

---

## AI & Agent Improvements

- Better error recovery and debugging
- Context management for long sessions
- Multi-file refactoring capabilities
- Intelligent test case generation
- Framework/library version selection

---

## Other Ideas

- **Resource Management**: Dynamic connection pool sizing, concurrent session limits, automatic cleanup
- **Performance Monitoring**: Token/cost tracking per session, database query performance, session benchmarks
- **Advanced Spec Features**: Multiple spec files with dependencies, template bundles, interactive spec builder
- **Deployment Automation**: One-click deploy to Vercel/Netlify/Railway, environment management, database provisioning
- **Task Manager Integration**: Sync with Jira, Linear, GitHub Projects
- **Real-time Collaboration**: Live session viewing, real-time log streaming, collaborative spec editing
- **Agent Specialization**: Specialized agents per domain (frontend, backend, database, DevOps, testing)
- **Analytics**: Project completion rate, time to complete, code quality trends, cost breakdown
