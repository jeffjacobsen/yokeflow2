# Completion Review Prompt

You are reviewing whether a YokeFlow-generated project actually implements what was requested in the original specification.

Unlike the initialization quality review (which checks the plan), you are reviewing **actual code**. The project has been built across multiple coding sessions. Your job is to assess whether the generated code fulfills the specification requirements.

## Original Specification

{spec_text}

## Code Inventory

{code_inventory}

## Test Results

{test_results}

## Requirement-to-Code Matching

The following table shows each specification requirement and the code artifacts that appear to implement it. A match does NOT guarantee correctness — use your judgment.

{requirements_table}

## Your Task

Provide a completion review with the following sections:

### 1. Executive Summary (2-3 sentences)

Brief assessment:
- Does the generated code implement the specification?
- Are there critical features missing from the code?
- Do the test results support that the implementation works?

### 2. Implementation Coverage

- **Implemented**: Which requirements have clear code evidence (matching files, functions, routes, components)?
- **Missing**: Which requirements have no matching code artifacts?
- **Uncertain**: Which requirements have partial matches that need manual verification?

### 3. Test Verification

- Are tests passing for the core features?
- Are there implemented features with failing tests?
- Are there requirements with no test coverage at all?

### 4. Code Quality Observations

- Does the project structure look reasonable for the spec?
- Are there obvious gaps (e.g., spec asks for auth but no auth-related code exists)?
- Any structural concerns (missing error handling, no database when spec requires one)?

### 5. Missing Features

List specific requirements from the spec that appear to be unimplemented:
1. [Requirement] — [Why it appears missing]
2. etc.

If all requirements appear implemented, say so.

### 6. Final Verdict

Choose one:
- **COMPLETE**: The code implements the specification. Tests are passing. Ready for review/deployment.
- **NEEDS_WORK**: Most of the spec is implemented but there are notable gaps or failing tests.
- **FAILED**: Significant portions of the specification are not implemented.

## Response Format

Structure your response in clear markdown with the sections above. Be concise and evidence-based — cite specific files, routes, or test results when possible.
