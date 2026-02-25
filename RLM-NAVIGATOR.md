# RLM Navigator + YokeFlow: Integration Analysis

## What RLM Navigator Does

A token-efficient codebase navigation MCP server that enforces a **tree → map → drill** workflow instead of reading full files. It uses tree-sitter AST parsing to extract file skeletons (signatures + docstrings only, no bodies), and only reads full implementations when you "drill" into a specific symbol.

Simulation on the YokeFlow codebase showed **96% token reduction** (269K → 11K tokens) for a search task, and the REPL grep approach showed near-100% reduction.

**MCP Tools (10 total):**
- Navigation: `get_status`, `rlm_tree`, `rlm_map`, `rlm_drill`, `rlm_search`
- REPL: `rlm_repl_init`, `rlm_repl_exec`, `rlm_repl_status`, `rlm_repl_reset`, `rlm_repl_export`

**Source:** `/Users/jeff/code/rlm-navigator`

---

## Where It Would Add Value in YokeFlow

### 1. Brownfield Coding Sessions (HIGH value)

The killer use case. When a Sonnet coding agent modifies an imported codebase (potentially thousands of files), it currently reads full files to understand context. RLM Navigator would let it:
- `rlm_tree` to understand project structure (~200 tokens vs reading directories)
- `rlm_map` to see what functions/classes exist in a file (~100 tokens vs 2,000+ for full read)
- `rlm_drill` only the specific symbol it needs to modify
- `rlm_search` to find where things are used across the codebase

For a 50K LOC imported codebase, this could mean **5-10x token savings per session**, translating directly to lower API costs.

### 2. Greenfield Coding Sessions (MODERATE value)

As the generated project grows (Sessions 5+), the agent needs to understand what earlier sessions built. Skeletons would help it navigate without reading every file. Less impactful in early sessions when the codebase is small.

### 3. Brownfield Session 0 - Initializer (MODERATE value)

The brownfield initializer agent explores the imported codebase to create scoped epics. The `codebase_import.py` does a fast filesystem-level analysis, but the Claude agent itself reads files during Session 0 to understand architecture. RLM would make that exploration more efficient.

### 4. Greenfield Session 0 (LOW value)

The initializer reads a spec file and creates epics — no codebase to navigate.

---

## Integration Feasibility

Integration is **mechanically straightforward**. In `server/client/claude.py`, MCP servers are a simple dict:

```python
mcp_servers = {
    "task-manager": { "command": "node", "args": [...], "env": mcp_env },
    # Adding RLM Navigator would be:
    "rlm-navigator": { "command": "node", "args": [...], "env": {"RLM_ROOT": str(project_dir)} }
}
```

---

## Challenges

| Challenge | Severity | Notes |
|-----------|----------|-------|
| **Daemon lifecycle** | Medium | RLM requires a running Python daemon per project. YokeFlow would need to start/stop it with each session. |
| **Dependency footprint** | Low | tree-sitter + watchdog are lightweight, but another thing to install |
| **Prompt engineering** | Medium | Coding agents need to learn the tree→map→drill workflow. `prompts/coding_prompt.md` would need updates. |
| **Greenfield cold start** | Low | Early sessions have little code — RLM adds overhead with minimal savings. Could conditionally enable only after Session 2+. |
| **Two MCP servers** | Low | Claude SDK already supports multiple MCP servers cleanly |

---

## Recommended Approach

1. **Start with brownfield only** — highest ROI, largest codebases
2. **Add daemon management** to the orchestrator (start before session, stop after)
3. **Update brownfield coding prompt** to teach the tree→map→drill workflow
4. **Conditionally enable** for greenfield after Session 2+ (when there's enough code to benefit)
5. **Make it configurable** in `.yokeflow.yaml` so users can opt in/out

---

## Verdict

**Yes, there's real value — particularly for brownfield projects and later greenfield sessions.** The token savings are significant (5-10x for navigation) and translate directly to lower API costs. The integration is mechanically clean since YokeFlow already uses MCP. The biggest practical hurdle is daemon lifecycle management, but the pattern already exists with the MCP task-manager pre-flight check.

---

*Analysis date: February 20, 2026*
