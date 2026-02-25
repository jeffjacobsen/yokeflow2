# RLM Navigator — Recursive Codebase Navigation Skill

## Purpose
Navigate codebases with minimal token usage by treating source files as hierarchical trees of AST skeletons. Never read full files when signatures suffice.

## Workflow — ALWAYS follow this order:

### 1. Health Check
```
get_status
```
If offline, tell the user to start the daemon:
```
python daemon/rlm_daemon.py --root <project_path>
```

### 2. Explore Structure (never use `ls`, `find`, or `Glob`)
```
rlm_tree path="" max_depth=3
```
See directory layout, file sizes, detected languages. Narrow down to relevant subdirectories.

### 3. Read Signatures (never `cat` or `Read` full files)
```
rlm_map path="src/main.py"
```
See function/class/method signatures + docstrings. Bodies are replaced with `...`.
This tells you WHAT exists without consuming tokens on HOW.

### 4. Surgical Drill (only when you need implementation details)
```
rlm_drill path="src/main.py" symbol="process_data"
```
Reads ONLY the lines of the specific symbol. This is the only time implementation code is loaded.

### 5. Search Across Files
```
rlm_search query="authenticate" path="src/"
```
Find where a symbol is defined across multiple files without reading any of them.

## Rules

- **NEVER read a full file** unless the file is under 50 lines or you've confirmed via `rlm_map` that you need the entire thing.
- **NEVER use `ls`, `find`, `Glob`** for directory exploration — use `rlm_tree`.
- **Map before drill** — always `rlm_map` a file before `rlm_drill` into it.
- **Minimize drill calls** — only drill symbols you actually need to understand or modify.
- **Batch your thinking** — after mapping, decide ALL symbols you need, then drill them in sequence.
- **Prefer skeleton references** — when discussing code, reference signatures from `rlm_map` output rather than drilling just to quote code.

## When NOT to use RLM

- Files you're about to edit entirely (use Read tool directly)
- Config files under 20 lines (just read them)
- Files you've already drilled into this conversation (they're in context)

## Sub-Agent Delegation

For large directories with many files, delegate to the `rlm-subcall` agent:
- Give it the `rlm_tree` output and your query
- It will identify which files are relevant
- You then `rlm_map` only those files

## REPL-Assisted Analysis

For multi-step analysis that builds on previous findings:

### Setup
```
rlm_repl_init
```
Initializes a stateful Python REPL with helpers: `peek()`, `grep()`, `chunk_indices()`, `write_chunks()`, `add_buffer()`.

### Explore with Helpers
```
rlm_repl_exec code="print(grep('TODO|FIXME|HACK', 'src/'))"
```
Use `peek()` to read specific line ranges, `grep()` for regex search across files.

### Accumulate Findings
```
rlm_repl_exec code="add_buffer('auth_flow', 'Step 1: Token validated in middleware.py:45')"
rlm_repl_exec code="add_buffer('auth_flow', 'Step 2: User loaded in auth.py:92')"
```
Use `add_buffer(key, text)` to collect findings across multiple exec calls.

### Export Results
```
rlm_repl_export
```
Retrieves all accumulated buffers for synthesis.

### Rules
- Initialize REPL at the start of complex analysis sessions
- Use buffers to collect findings rather than relying on context window
- Variables persist between `rlm_repl_exec` calls — assign intermediate results
- Reset with `rlm_repl_reset` when switching to unrelated analysis

## Chunk-Delegate-Synthesize Workflow

For large files or cross-file analysis, use the chunk-delegate pattern:

### 1. Chunk via REPL
```
rlm_repl_exec code="paths = write_chunks('src/large_module.py', size=200, overlap=20); print(paths)"
```
Splits the file into manageable chunks written to `.claude/rlm_state/chunks/`.

### 2. Delegate Each Chunk
Send each chunk to the `rlm-subcall` sub-agent with:
- The chunk content (from `peek()` or the chunk file)
- The user's query
- A `chunk_id` (e.g., `"large_module.py:chunk_0"`)

### 3. Follow Suggested Queries
The sub-agent returns `suggested_next_queries` — these are actionable RLM tool calls. Execute the highest-priority ones to fill in gaps identified in the `missing` field.

### 4. Synthesize
When a sub-agent returns `answer_if_complete` (non-null), or when all chunks have been analyzed, synthesize the collected `relevant` items and buffer contents into a final answer.

### When to Use This Workflow
- Files over 500 lines that need thorough analysis
- Cross-file analysis spanning 5+ files
- Architecture understanding tasks ("how does X work end-to-end?")
- When a single `rlm_map` + `rlm_drill` cycle is insufficient
