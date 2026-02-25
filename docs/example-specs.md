# Example Specification Files

This directory contains example specification files demonstrating the multiple file upload feature in YokeFlow.

## Purpose

These examples show how to structure complex project specifications using multiple files, making them easier to organize and maintain.

---

## Examples

### 1. multi-file-spec/ - Full-Stack Web Application

**Type:** UI-based web application (suitable for browser verification)

**Description:** A complete specification for a full-stack web app with authentication, demonstrating best practices for organizing specs.

**Files:**
- `main.md` - Primary specification file (entry point)
- `api-design.md` - API endpoint definitions
- `database-schema.md` - Database schema and models
- `ui-design.md` - User interface specifications
- `example-auth.py` - Reference authentication code
- `README.md` - Documentation about this example

**Use Case:** Demonstrates how to split a large specification into logical components (main spec, API, database, UI, code examples).

**Testing Status:** Created as reference example for documentation.

---

### 2. prp-test/ - RAG Voice Agent

**Type:** Non-UI Python application (LiveKit voice agent)

**Description:** Specification for a RAG (Retrieval-Augmented Generation) voice agent using LiveKit, demonstrating how to include reference code in specifications.

**Files:**
- `rag-voice-agent.md` - Primary specification file (entry point)
- `basic_voice_assistant.py` - Example voice agent implementation
- `db_utils.py` - Database utility reference code
- `embedder.py` - Embedding generation reference code
- `ingest.py` - Document ingestion reference code
- `schema.sql` - PostgreSQL/PGVector schema

**Use Case:**
- Demonstrates including reference Python code in specifications
- Shows how to provide database schemas and utility code
- Example of non-UI application specification

**Testing Status:** ✅ Successfully tested with YokeFlow initializer
- Created 18 epics, 129 tasks, 129 tests
- Output available in `prp-test-output/` directory
- Demonstrates multi-file spec handling works correctly

**Note:** This is a non-UI application (voice agent), so it would not be suitable for the browser verification step in coding sessions. However, it successfully demonstrates that the multi-file spec feature works end-to-end for the initialization phase.

---

### 3. prp-test-output/ - Initialization Results

**Type:** Generated output from prp-test initialization

**Description:** Output directory showing what YokeFlow's initializer created from the multi-file prp-test specification.

**Contents:**
- `yokeflow/agent-progress.md` - Session 0 completion summary showing:
  - 18 epics created
  - 129 tasks generated
  - 129 test cases defined
  - Complete project structure
  - Technology stack decisions
  - Next steps for coding sessions

**Purpose:** Demonstrates successful multi-file spec processing by the initializer.

---

## Legacy Examples

### app_spec.txt
Original single-file specification example (legacy format).

### app_spec_claude_ai.txt
Another single-file specification example (legacy format).

**Note:** These single-file examples are kept for backward compatibility but the multi-file approach is now recommended for complex projects.

---

## Best Practices

Based on these examples, here are best practices for multi-file specifications:

1. **Name your primary file** `main.md` or `spec.md` (YokeFlow auto-detects this)
2. **Reference other files** in your main spec (e.g., "See api-design.md for endpoints")
3. **Include supporting files:**
   - API documentation (`.md`)
   - Database schemas (`.sql`)
   - Reference code (`.py`, `.ts`, `.js`, etc.)
   - Configuration examples (`.json`, `.yaml`)
   - UI mockups/wireframes (`.md`, `.html`)
4. **Use clear file names** that indicate purpose (e.g., `database-schema.md`, not `file2.md`)
5. **Keep files focused** - Each file should cover a specific aspect of the project
6. **Add a README** - Explain the structure if your spec has many files

---

## How Multi-File Specs Work

When you upload multiple files to YokeFlow:

1. **Files saved to `spec/` directory** in your project
2. **Primary file auto-detected:**
   - First priority: `main.md`
   - Second priority: `spec.md`
   - Fallback: Largest `.md` or `.txt` file
3. **Initializer reads primary file first**, then lazy-loads other files as needed
4. **Agent can search across files** using `grep -r "search term" spec/`

This approach:
- Saves tokens (agent only reads what it needs)
- Improves organization (logical file separation)
- Enables reuse (same schema/code across multiple specs)
- Makes specs easier to maintain and version control

---

## Creating Your Own Multi-File Spec

1. Create a directory for your spec
2. Add your primary file (name it `main.md`)
3. Add supporting files (schemas, code examples, etc.)
4. In Web UI: Select all files and upload together
5. YokeFlow handles the rest automatically!

For detailed documentation, see the [Multiple Specification Files](../README.md#multiple-specification-files) section in the main README.

---

**Last Updated:** December 24, 2025
