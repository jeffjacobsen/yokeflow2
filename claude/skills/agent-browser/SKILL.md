---
name: agent-browser
description: Browser automation CLI for AI agents. Use when you need to interact with websites, including navigating pages, filling forms, clicking buttons, taking screenshots, extracting data, or testing web apps.
---

# Browser Automation with agent-browser

## Core Workflow

Every browser screenshot follows this pattern:

1. **Navigate**: `agent-browser open <url>`
2. **Screenshot**: `agent-browser screenshot`

Every browser automation follows this pattern:

1. **Navigate**: `agent-browser open <url>`
2. **Snapshot**: `agent-browser snapshot -i` (get element refs like `@e1`, `@e2`)
3. **Interact**: Use refs to click, fill, select
4. **Re-snapshot**: After navigation or DOM changes, get fresh refs

```bash
agent-browser open https://example.com/form
agent-browser snapshot -i
# Output: @e1 [input type="email"], @e2 [input type="password"], @e3 [button] "Submit"

agent-browser fill @e1 "user@example.com"
agent-browser fill @e2 "password123"
agent-browser click @e3
agent-browser wait --load networkidle
agent-browser snapshot -i  # Check result
```

## Command Chaining

Commands can be chained with `&&` in a single shell invocation. The browser persists between commands via a background daemon.

```bash
# Chain open + wait + snapshot in one call
agent-browser open https://example.com && agent-browser wait --load networkidle && agent-browser snapshot -i

# Chain multiple interactions
agent-browser fill @e1 "user@example.com" && agent-browser fill @e2 "password123" && agent-browser click @e3
```

**When to chain:** Use `&&` when you don't need to read the output of an intermediate command before proceeding. Run commands separately when you need to parse the output first (e.g., snapshot to discover refs, then interact using those refs).

## Commands

### Navigation
```bash
agent-browser open <url>              # Navigate to URL
agent-browser close                   # Close browser
```

### Snapshot (get element refs)
```bash
agent-browser snapshot -i             # Interactive elements with refs (recommended)
agent-browser snapshot -i -C          # Include cursor-interactive elements (divs with onclick)
agent-browser snapshot -s "#selector" # Scope to CSS selector
```

### Interaction (use @refs from snapshot)
```bash
agent-browser click @e1               # Click element
agent-browser fill @e2 "text"         # Clear and type text
agent-browser type @e2 "text"         # Type without clearing
agent-browser select @e1 "option"     # Select dropdown option
agent-browser check @e1               # Check checkbox
agent-browser press Enter             # Press key
agent-browser scroll down 500         # Scroll page
```

### Get Information
```bash
agent-browser get text @e1            # Get element text
agent-browser get url                 # Get current URL
agent-browser get title               # Get page title
```

### Wait
```bash
agent-browser wait @e1                # Wait for element
agent-browser wait --load networkidle # Wait for network idle
agent-browser wait --url "**/page"    # Wait for URL pattern
agent-browser wait 2000               # Wait milliseconds
```

### Screenshots

**IMPORTANT: `agent-browser screenshot` ignores path arguments and saves to a temp directory.** You must capture the output to find the actual file path, then copy it to the desired location.

```bash
# Take screenshot and copy to desired location (uses xargs to avoid zsh parse issues with $())
agent-browser screenshot 2>&1 | grep -o '/[^ ]*\.png' | head -1 | xargs -I{} mv {} yokeflow/screenshots/task_10_login_form.png

# Full-page screenshot
agent-browser screenshot --full 2>&1 | grep -o '/[^ ]*\.png' | head -1 | xargs -I{} mv {} yokeflow/screenshots/task_10_full_page.png

# Verify it was saved
ls -la yokeflow/screenshots/task_10_login_form.png
```

### Diff (compare page states)
```bash
agent-browser diff snapshot                          # Compare current vs last snapshot
agent-browser diff snapshot --baseline before.txt    # Compare current vs saved file
```

## Ref Lifecycle (Important)

Refs (`@e1`, `@e2`, etc.) are invalidated when the page changes. Always re-snapshot after:

- Clicking links or buttons that navigate
- Form submissions
- Dynamic content loading (dropdowns, modals)

```bash
agent-browser click @e5              # Navigates to new page
agent-browser snapshot -i            # MUST re-snapshot
agent-browser click @e1              # Use new refs
```

## JavaScript Evaluation

Use `eval` for JavaScript in the browser.

**🚨 `eval` already runs inside `page.evaluate()` — do NOT wrap your code in `page.evaluate()` yourself.** This is the most common eval error. Writing `agent-browser eval 'page.evaluate(() => document.title)'` double-wraps and causes "Illegal return statement" or "Invalid or unexpected token" errors.

```bash
# ✅ CORRECT — eval handles page.evaluate internally
agent-browser eval 'document.title'

# ❌ WRONG — double-wraps in page.evaluate, causes SyntaxError
agent-browser eval 'page.evaluate(() => document.title)'
```

**Shell quoting rules:**
- **Single property**: Use single quotes — `agent-browser eval 'document.title'`
- **Multiple properties**: Run separate eval commands, one per value
- **Complex JS** (nested quotes, template literals, arrow functions): Use `--stdin` with heredoc
- **NEVER** use double quotes around eval expressions — they break on single quotes, `!`, and `$()`

```bash
# Single value — use single quotes
agent-browser eval 'document.title'
agent-browser eval 'document.querySelector("h1").textContent'

# Multiple values — run separate commands (NOT string concatenation)
agent-browser eval 'document.title'
agent-browser eval 'document.querySelector("h1").textContent'
agent-browser eval 'document.querySelector("button").textContent'

# Complex JS — use --stdin with heredoc
agent-browser eval --stdin <<'EVALEOF'
JSON.stringify(
  Array.from(document.querySelectorAll("img"))
    .filter(i => !i.alt)
    .map(i => ({ src: i.src.split("/").pop(), width: i.width }))
)
EVALEOF
```

### Tailwind Slash Classes in Selectors

Tailwind classes with `/` (e.g., `border-red-500/20`, `bg-black/50`) break `querySelector` because `/` is a CSS selector special character.

```bash
# ❌ SyntaxError: not a valid selector
agent-browser eval 'document.querySelector(".border-red-500/20")'

# ✅ Escape the slash
agent-browser eval 'document.querySelector(".border-red-500\\/20")'

# ✅ Or use attribute contains selector
agent-browser eval 'document.querySelector("[class*=\"border-red-500\"]")'
```

### Console Error Checking

Check for JavaScript errors after navigation or interaction:

```bash
# Check for console errors (returns array of error messages)
agent-browser eval --stdin <<'EVALEOF'
JSON.stringify(
  performance.getEntriesByType("resource")
    .filter(r => r.responseStatus >= 400)
    .map(r => r.name + " → " + r.responseStatus)
)
EVALEOF

# Quick DOM error check — look for React error boundaries or error text
agent-browser eval 'document.querySelector("[data-error], .error, #error")?.textContent || "no errors"'
```

## Timeouts and Slow Pages

Default timeout is 60 seconds. For slow pages, use explicit waits:

```bash
agent-browser wait --load networkidle        # Wait for network to settle
agent-browser wait "#content"                # Wait for specific element
agent-browser wait --fn "document.readyState === 'complete'"  # JS condition
```

## Cleanup

Always close the browser when done:

```bash
agent-browser close
```

If a previous session wasn't closed properly, `agent-browser close` cleans up stale daemons.
