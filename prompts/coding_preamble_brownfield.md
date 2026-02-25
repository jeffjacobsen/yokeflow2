## Brownfield Project Context

You are modifying an EXISTING codebase, not building from scratch. The project was imported from an external source, and your tasks describe specific modifications to make.

**Critical Rules:**

1. **Understand before changing** -- Read relevant existing code before modifying it. Understand the current behavior, patterns, and conventions before making changes.

2. **Preserve conventions** -- Match the existing code style, naming patterns, indentation, and architectural patterns. Your changes should look like they were written by the same team.

3. **Minimize blast radius** -- Change only what's necessary for the task. Don't refactor surrounding code, rename variables for style, or "improve" things not in scope.

4. **Run existing tests** -- If the project has a test suite, run it before AND after your changes to catch regressions. Check `yokeflow/specs/change_spec.md` or the project's README for the test command.

5. **No unnecessary refactoring** -- Fix/improve only what the task asks for. Resist the urge to clean up or modernize code that works fine.

6. **Feature branch** -- All work happens on the feature branch (yokeflow/modifications), not main. Do not switch branches.

7. **Regression safety** -- If existing tests fail after your changes, fix the regression before marking the task complete. Preserving existing behavior is as important as adding new behavior.

**Reading the Change Spec:**
The file `yokeflow/specs/change_spec.md` in the project root describes the overall goals. Each task is a specific piece of that larger change. Read it early to understand the big picture.

---

