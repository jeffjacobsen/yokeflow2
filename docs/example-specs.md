# Example Specifications

The `example-specs/` directory contains example specification files for testing YokeFlow.

---

## Examples

### todo.md — Simple Todo API

A minimal REST API for managing todo items. Designed as a quick test project (10–15 minutes total).

- **Tech stack:** Node.js, Express, in-memory storage
- **Scope:** 6 API endpoints with CRUD operations, error handling, documentation
- **Use case:** Quick platform verification — fast initialization and coding sessions

### browser-test.md — Browser Automation Test

A minimal web application for testing agent-browser integration.

- **Tech stack:** Express backend + simple HTML frontend
- **Scope:** Health check API, button that fetches from the API, console logging
- **Use case:** Verifying browser automation works during coding sessions

### multi-file-spec/ — Full-Stack Web Application

A complete specification for a Task Management SaaS application, split across multiple files to demonstrate multi-file spec support.

**Files:**
- `main.md` — Primary specification (features, tech stack, overview)
- `api-design.md` — REST API and WebSocket event definitions
- `database-schema.md` — PostgreSQL schema with Prisma ORM
- `ui-design.md` — UI/UX guidelines and component specifications
- `example-auth.py` — Reference authentication implementation
- `README.md` — Documentation about this example

**Use case:** Demonstrates how to organize large specifications into logical components.

---

## Multi-File Specs

When you upload multiple files to YokeFlow:

1. Files are saved to the `yokeflow/specs/` directory in your project
2. The primary file is auto-detected:
   - First priority: `main.md`
   - Second priority: `spec.md`
   - Fallback: largest `.md` or `.txt` file
3. The initializer reads the primary file first, then loads other files as needed

**Best practices:**
- Name your primary file `main.md`
- Reference other files clearly (e.g., "See `api-design.md` for endpoints")
- Keep files focused — each should cover a specific aspect (API, database, UI)
- Use descriptive file names
