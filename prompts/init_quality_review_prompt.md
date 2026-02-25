# Initialization Quality Review Prompt

You are reviewing the quality of a YokeFlow project initialization (Session 0).

Session 0 reads the specification and creates a plan: epics (high-level features), tasks (specific implementations), and tests (validation criteria). Your job is to assess whether this plan adequately covers the original specification.

**Important**: You are reviewing the PLAN, not actual code. The code has not been written yet. You are checking whether the initializer created a comprehensive breakdown that, if implemented, would satisfy the specification.

## Original Specification

{spec_text}

## Plan Summary

**Project Metadata:**
- Project Name: {project_name}
- Total Epics: {epic_count}
- Total Tasks: {task_count}
- Completed Tasks: {completed_task_count}

**Spec Requirement Coverage:**
- Total Requirements Identified: {requirements_total}
- Requirements Covered by Plan: {requirements_met} ({coverage_percentage}%)
- Requirements Missing from Plan: {requirements_missing}
- Requirements Partially Covered: {requirements_partial}
- Extra Features (beyond spec): {requirements_extra}

**Test Coverage:**
{test_coverage_summary}

## Detailed Requirements Analysis

{requirements_table}

## Your Task

Provide a quality review of this initialization with the following sections:

### 1. Executive Summary (2-3 sentences)

Brief assessment:
- Does the plan cover the specification adequately?
- Are there critical gaps that would result in an incomplete implementation?
- Is the test coverage sufficient?

### 2. Spec Coverage Assessment

- **Well Covered**: Which requirement areas have strong epic/task coverage?
- **Gaps**: Which spec requirements are missing from the plan?
- **Critical Missing**: Any high-priority requirements not addressed?
- **Extra Features**: Are planned extras valuable or scope creep?

### 3. Test Coverage Assessment

- Are tasks adequately covered by tests?
- Are there epics with poor test coverage that need attention?
- Is the test-to-task ratio reasonable?

### 4. Plan Structure Quality

- Is the epic/task breakdown logical and well-organized?
- Are tasks appropriately sized (not too large, not too granular)?
- Does the task ordering make sense for implementation?

### 5. Recommendations

- **Ready to Start Coding?** Yes / No / With Changes
  - If yes: Any suggestions for the coding sessions?
  - If no: What should be added or changed in the plan?
- **Priority Additions** (if any):
  1. [Most important missing item]
  2. [Second priority]
  3. etc.

### 6. Final Verdict

Choose one:
- **COMPLETE**: Plan covers the specification well. Ready to proceed with coding.
- **NEEDS_WORK**: Plan mostly covers the spec but has gaps that should be addressed first.
- **FAILED**: Plan has significant gaps and should be re-initialized or manually corrected.

## Response Format

Structure your response in clear markdown with the sections above. Be concise and actionable.
