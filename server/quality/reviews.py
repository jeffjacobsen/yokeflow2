"""
Review Client - Automated Deep Session Analysis (Phase 2)
==========================================================

YokeFlow's Claude-powered session review system that runs automatically to
analyze session quality and suggest prompt improvements.

This module integrates with the orchestrator to provide:
1. Automated trigger after every 5 sessions or when quality drops below 7
2. Deep analysis of session logs using Claude
3. Concrete prompt improvement suggestions
4. Trend analysis across multiple sessions
5. Storage of review results in database

Architecture:
- Called by orchestrator.py after session completion
- Stores results in session_deep_reviews table
- Non-blocking: runs asynchronously, doesn't slow down sessions

Usage:
    from server.quality.reviews import run_deep_review

    # Trigger deep review for a session
    await run_deep_review(
        session_id=session_uuid,
        project_path=Path("projects/my-project"),
        model="claude-sonnet-4-6"
    )
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from uuid import UUID
from collections import defaultdict

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

from server.database.connection import DatabaseManager


logger = logging.getLogger(__name__)


def _format_duration(start_time: str, end_time: str) -> str:
    """Format duration between two ISO timestamps."""
    try:
        from datetime import datetime
        start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        duration = (end - start).total_seconds()

        if duration < 60:
            return f"{duration:.0f}s"
        elif duration < 3600:
            return f"{duration/60:.1f}m"
        else:
            return f"{duration/3600:.1f}h"
    except:
        return "unknown"


def create_review_client(model: str) -> ClaudeSDKClient:
    """
    Create Claude SDK client for review sessions.

    IMPORTANT: This client prevents tool use by:
    - Setting mcp_servers={} (no tools available)
    - System prompt explicitly instructs text-only response
    - max_turns=1 (single response, no follow-up)

    Args:
        model: Claude model to use for review

    Returns:
        Configured ClaudeSDKClient for review
    """
    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt=(
                "You are a code review expert analyzing YokeFlow coding agent sessions. "
                "ALL necessary data is provided in the user message - you have everything you need. "
                "Provide your analysis as pure Markdown text. "
                "DO NOT attempt to read files, run commands, or use any tools. "
                "Respond with a comprehensive review report following the requested format."
            ),
            permission_mode="bypassPermissions",
            mcp_servers={},  # No MCP servers - no tools available
            max_turns=1,  # Single-turn only
            max_buffer_size=10485760,  # 10MB buffer
        )
    )


async def run_deep_review(
    session_id: UUID,
    project_path: Path,
    model: str = None
) -> Dict[str, Any]:
    """
    Run deep review on a completed session using Claude.

    This is the main entry point for automated deep reviews (Phase 2).

    Steps:
    1. Load session logs (JSONL + TXT)
    2. Extract metrics using review_metrics
    3. Create context for Claude (prompt + metrics + logs)
    4. Call Claude for analysis
    5. Store results in database

    Args:
        session_id: UUID of the session to review
        project_path: Path to project directory
        model: Claude model to use for review

    Returns:
        Dict with review results:
        {
            'check_id': UUID,
            'overall_rating': int (1-10),
            'critical_issues': [str],
            'warnings': [str],
            'review_text': str (markdown)
        }

    Raises:
        FileNotFoundError: If session logs not found
        RuntimeError: If Claude SDK authentication not configured
    """
    # Use DEFAULT_REVIEW_MODEL from env if model not specified
    if model is None:
        model = os.getenv('DEFAULT_REVIEW_MODEL', 'claude-sonnet-4-6')

    logger.info(f"Starting deep review for session {session_id} using model {model}")

    # Get session info from database
    async with DatabaseManager() as db:
        async with db.acquire() as conn:
            session = await conn.fetchrow(
                "SELECT * FROM sessions WHERE id = $1",
                session_id
            )

            if not session:
                raise ValueError(f"Session not found: {session_id}")

            session_number = session['session_number']
            session_type = session['type']
            project_id = session['project_id']

            session_dict = dict(session)
            # Parse metrics JSONB field (asyncpg returns it as a string)
            if 'metrics' in session_dict and isinstance(session_dict['metrics'], str):
                try:
                    session_dict['metrics'] = json.loads(session_dict['metrics'])
                except (json.JSONDecodeError, TypeError):
                    session_dict['metrics'] = {}
            session_metrics = session_dict.get('metrics', {})


    # Find session logs
    from server.utils.project_paths import resolve_logs_dir
    logs_dir = resolve_logs_dir(project_path)
    jsonl_pattern = f"session_{session_number:03d}_*.jsonl"
    txt_pattern = f"session_{session_number:03d}_*.txt"

    jsonl_files = list(logs_dir.glob(jsonl_pattern))
    txt_files = list(logs_dir.glob(txt_pattern))

    if not jsonl_files:
        raise FileNotFoundError(f"No JSONL log found for session {session_number}")

    jsonl_path = jsonl_files[0]
    txt_path = txt_files[0] if txt_files else None

    # logger.info(f"Analyzing logs: {jsonl_path.name}")

    # Use metrics from database (collected in real-time by MetricsCollector)
    # No need to parse JSONL files anymore
    metrics = session_metrics.copy()  # Use the real-time collected metrics

    # Add test compliance analysis
    from server.quality.test_compliance_analyzer import analyze_test_compliance
    try:
        test_compliance = await analyze_test_compliance(session_id, jsonl_path)
        metrics['test_compliance'] = test_compliance
    except Exception as e:
        logger.warning(f"Test compliance analysis failed: {e}")
        metrics['test_compliance'] = None

    # Use the configured review model (from environment or default)
    # The model in enhanced_data is the agent's model, not the review model
    model = os.getenv('DEFAULT_REVIEW_MODEL', 'claude-sonnet-4-6')

    # Create review context with all data
    context = _create_review_context(
        project_path=project_path,
        session_number=session_number,
        session_type=session_type,
        session_metrics=metrics,  # metrics already contains session_metrics.copy()
        test_compliance=metrics.get('test_compliance')
    )

    # Temporary: Save context to file for review
    # with open('review_context.txt', 'w') as f:
    #    f.write(context)

    # Load review prompt from external file
    # The client is configured with mcp_servers={} and max_turns=1, so no tool use will occur
    review_prompt_path = Path(__file__).parent.parent.parent / "prompts" / "review_prompt.md"

    if not review_prompt_path.exists():
        raise FileNotFoundError(
            f"Review prompt file not found at {review_prompt_path}. "
            "This file is required for deep reviews. Please ensure the prompts/ directory "
            "contains review_prompt.md"
        )

    # logger.info(f"Loading review prompt from {review_prompt_path}")
    with open(review_prompt_path, 'r') as f:
        review_base_prompt = f.read()

    # Construct full prompt with context
    full_prompt = f"""{review_base_prompt}

---

# REVIEW DATA FOR SESSION {session_number}

{context}

---

## YOUR TASK

Analyze this session using the framework above. All necessary data is provided - DO NOT attempt to use tools.

Provide a comprehensive review focusing on:

1. **Session Quality Rating (1-10)** - Based on browser verification ({metrics.get('browser_verifications', 0)} total browser operations using agent-browser), error rate, task completion
2. **Browser Verification Analysis** - Critical quality indicator (r=0.98 correlation)
3. **Error Pattern Analysis** - What types, were they preventable, recovery efficiency
4. **Prompt Adherence** - Which steps followed well, which skipped
5. **Concrete Prompt Improvements** - Specific changes to `coding_prompt.md`

**IMPORTANT:** End with structured RECOMMENDATIONS section (High/Medium/Low Priority) with specific, actionable changes.

Focus on **systematic improvements** that help ALL future sessions, not fixes for this specific application.
"""

    # Create review client
    client = create_review_client(model)

    # logger.info(f"Calling Claude SDK ({model}) for deep analysis...")

    # Call Claude using Agent SDK
    try:
        async with client:
            # Send review prompt
            await client.query(full_prompt)

            # Collect response text (only TextBlocks, ignore ToolUseBlocks)
            review_text = ""
            message_count = 0
            text_block_count = 0
            tool_use_attempts = 0

            async for msg in client.receive_response():
                message_count += 1
                msg_type = type(msg).__name__

                # Handle AssistantMessage
                if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                    for block in msg.content:
                        block_type = type(block).__name__

                        if block_type == "TextBlock" and hasattr(block, "text"):
                            text_block_count += 1
                            block_text = block.text
                            review_text += block_text
                        elif block_type == "ToolUseBlock":
                            tool_use_attempts += 1
                            logger.warning(f"Claude attempted to use a tool despite instruction not to (attempt #{tool_use_attempts})")
                            # Continue collecting text - don't stop on tool use

        logger.info(f"Review complete: {message_count} messages, {text_block_count} text blocks, {len(review_text)} total chars")

        if tool_use_attempts > 0:
            logger.warning(f"Claude attempted {tool_use_attempts} tool uses despite mcp_servers={{}} and explicit instruction not to")

    except Exception as e:
        logger.error(f"Claude SDK call failed: {e}")
        raise

    # Extract executive summary for structured storage
    review_summary = _extract_executive_summary(review_text)

    # Extract rating from review if present (default to 5 if not found)
    # Prefer rating from executive summary, fall back to general extraction
    overall_rating = review_summary.get('rating') or _extract_rating_from_review(review_text) or 5

    # Parse recommendations from review text (now returns structured dicts)
    prompt_improvements = _parse_recommendations(review_text)

    # Store in database
    async with DatabaseManager() as db:
        check_id = await db.store_deep_review(
            session_id=session_id,
            metrics=metrics,
            overall_rating=overall_rating,
            review_text=review_text,
            prompt_improvements=prompt_improvements,  # List of structured recommendation dicts
            review_summary=review_summary,  # Extracted from Executive Summary section
            review_version="2.1",
            model=model  # Model extracted from JSONL
        )

    # logger.info(f"Deep review stored: {check_id}")

    return {
        'check_id': check_id,
        'overall_rating': overall_rating,
        'review_text': review_text
    }




def _create_review_context(
    project_path: Path,
    session_number: int,
    session_type: str,
    session_metrics: Dict[str, Any],
    test_compliance: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create optimized context for Claude review.

    REFACTORED Dec 25, 2025: Now uses enhanced JSONL data instead of TXT log excerpt.
    This provides 8x token reduction with better signal-to-noise ratio.

    Provides all relevant information about the session for analysis.
    """
    # Get data from new metrics structure
    command_analysis = session_metrics.get('command_analysis', {})
    error_analysis = session_metrics.get('error_analysis', {})
    browser_operations = session_metrics.get('browser_operations', {})

    context = f"""# Review Context for Session

## Session Metadata
- Session: {session_number} ({session_type})
- Model: {session_metrics.get('model', 'unknown')}
- Duration: {session_metrics.get('duration_seconds', 0):.0f}s

## Session Metrics (from database)
"""
    # Format session metrics as bullet list for better readability
    for key, value in session_metrics.items():
        # Skip model since we already included it above
        if key == 'model':
            continue

        # Format the key to be more readable (e.g., tool_calls_count -> Tool Calls)
        readable_key = key.replace('_', ' ').title()

        # Format values appropriately
        if isinstance(value, float):
            if key == 'error_rate':
                formatted_value = f"{value:.1%}"
            else:
                formatted_value = f"{value:.2f}"
        elif isinstance(value, int):
            formatted_value = f"{value:,}"
        else:
            formatted_value = str(value)

        context += f"\n- **{readable_key}:** {formatted_value}"

    context += f"\n\n## Command Usage Analysis\n"

    # Show bash command patterns instead of tool counts
    # command_analysis already extracted at the top of function
    bash_commands = command_analysis.get('bash_commands', {})
    command_patterns = command_analysis.get('command_patterns', {})
    
    if bash_commands:
        context += "\n### Bash Commands (Top 10)\n"
        sorted_commands = sorted(bash_commands.items(), key=lambda x: x[1], reverse=True)
        for cmd, count in sorted_commands[:10]:
            context += f"\n- {cmd}: {count}"
    
    if command_patterns:
        context += "\n\n### Command Patterns\n"
        for pattern, count in command_patterns.items():
            if count > 0:
                readable_pattern = pattern.replace('_', ' ').title()
                context += f"\n- {readable_pattern}: {count}"

    context += f"\n\n## Error Analysis\n"
    context += f"**Total errors: {session_metrics.get('errors_count', 0)} ({session_metrics.get('error_rate', 0):.1%} rate)**\n"

    # Format detailed error information from new structure
    command_errors = error_analysis.get('command_errors', [])
    if command_errors:
        for i, err in enumerate(command_errors[-5:], 1):  # Last 5 errors
            context += f"\n### Error {i} ({err.get('category', 'unknown')})"
            context += f"\n- Task: {err.get('task_id', 'none')}"
            context += f"\n- Message: {err.get('message', '')[:200]}..."
    else:
        context += "\n- No errors detected"

    # NEW: Task Type Classification and Verification Matching
    task_types = session_metrics.get('task_types', {})
    if task_types:
        context += f"\n\n## Task Type Analysis (Critical for Quality Rating)\n"

        # Count task types
        type_counts = defaultdict(int)
        for task_data in task_types.values():
            type_counts[task_data.get('type', 'UNKNOWN')] += 1

        context += "### Task Types Worked On\n"
        for task_type, count in type_counts.items():
            context += f"- {task_type}: {count} tasks\n"

        # Verification appropriateness
        verification_analysis = session_metrics.get('verification_analysis', {})
        if verification_analysis:
            context += "\n### Verification Method Matching\n"
            context += f"- Appropriate verifications: {verification_analysis.get('appropriate_verifications', 0)}\n"
            context += f"- Inappropriate verifications: {verification_analysis.get('inappropriate_verifications', 0)}\n"
            context += f"- Unverified tasks: {verification_analysis.get('unverified_tasks', 0)}\n"
            context += f"- Verification rate: {verification_analysis.get('verification_rate', 0):.1%}\n"

        # List mismatched verifications for review
        mismatched = []
        for task_id, task_data in task_types.items():
            if not task_data.get('verification_appropriate', False) and task_data.get('verification_method') != 'none':
                mismatched.append(f"Task {task_id} ({task_data['type']}): Used {task_data['verification_method']}, expected {task_data.get('expected_verification', 'any')}")

        if mismatched:
            context += "\n### Mismatched Verifications (Wrong test for task type)\n"
            for mismatch in mismatched[:5]:  # First 5
                context += f"- {mismatch}\n"

    # NEW: Error Patterns with Recovery Analysis
    error_patterns = error_analysis.get('error_patterns', {})
    if error_patterns:
        context += f"\n\n## Error Pattern Analysis\n"
        for pattern_key, pattern_data in list(error_patterns.items())[:5]:  # Top 5 patterns
            if pattern_data['count'] > 1:  # Only show repeated errors
                context += f"\n### {pattern_key.replace('_', ' ').title()}\n"
                context += f"- Occurrences: {pattern_data['count']}\n"
                context += f"- Average recovery attempts: {pattern_data.get('avg_recovery_attempts', 0):.1f}\n"
                if pattern_data.get('examples'):
                    context += f"- Example: {pattern_data['examples'][0][:150]}...\n"

    # NEW: Prompt Adherence Violations
    adherence_summary = session_metrics.get('adherence_summary', {})
    if adherence_summary and adherence_summary.get('total_violations', 0) > 0:
        context += f"\n\n## Prompt Adherence Issues\n"
        context += f"**Total violations: {adherence_summary['total_violations']}**\n"

        violation_types = adherence_summary.get('violation_types', {})
        if violation_types:
            context += "\n### Violation Types\n"
            for vtype, count in violation_types.items():
                readable_type = vtype.replace('_', ' ').title()
                context += f"- {readable_type}: {count} occurrences\n"

        # Show specific examples
        violations = session_metrics.get('adherence_violations', [])
        if violations:
            context += "\n### Specific Violations (First 3)\n"
            for violation in violations[:3]:
                context += f"- **{violation['type']}**: {violation['context'][:100]}...\n"
                context += f"  Impact: {violation['impact']}\n"

    # NEW: Session Progression Metrics
    session_progression = session_metrics.get('session_progression', {})
    if session_progression and session_progression.get('hourly_metrics'):
        context += f"\n\n## Session Progression Trends\n"
        context += f"- Tasks per hour: {session_progression.get('tasks_per_hour', 0):.1f}\n"
        context += f"- Errors per hour: {session_progression.get('errors_per_hour', 0):.1f}\n"

        hourly_metrics = session_progression['hourly_metrics']
        if len(hourly_metrics) > 1:
            context += "\n### Hourly Trends\n"
            for metric in hourly_metrics[-3:]:  # Last 3 hours
                context += f"- Hour {metric['hour']}: {metric['tasks_completed']} tasks, {metric['errors_count']} errors, {metric.get('verification_rate', 0):.0%} verification rate\n"

    # Task Completion Timeline (existing, but moved after new sections)
    context += f"\n\n## Task Completion Timeline\n"
    context += f"- Tasks started: {session_metrics.get('test_metrics', {}).get('tasks_started', 0)}\n"
    context += f"- Tasks completed: {session_metrics.get('test_metrics', {}).get('tasks_completed', 0)}\n"
    context += f"- Tests retrieved: {session_metrics.get('test_metrics', {}).get('tests_retrieved', 0)}\n"
    context += f"- Tests passed: {session_metrics.get('test_metrics', {}).get('tests_passed', 0)}\n"

    # Session Event Timeline - simplified
    context += f"\n\n## Session Summary\n"
    context += f"- Session duration: {session_metrics.get('duration_seconds', 0):.0f}s\n"
    context += f"- Total tool uses: {session_metrics.get('tool_use_count', 0)}\n"
    context += f"- Quality score: {session_metrics.get('quality_score', 'N/A')}\n"

    # Test Compliance Analysis (if available)
    if test_compliance:
        context += f"\n\n## Test Compliance Analysis\n"
        context += f"**Compliance Score: {test_compliance.get('compliance_score', 0)}/100**\n\n"

        # Test workflow metrics
        test_metrics = test_compliance.get('metrics', {}).get('test_workflow', {})
        if test_metrics:
            context += "### Testing Workflow\n"
            context += f"- Tasks completed: {test_metrics.get('tasks_completed', 0)}\n"
            context += f"- Tasks properly tested: {test_metrics.get('tasks_tested_properly', 0)}\n"
            context += f"- Tasks without test retrieval: {len(test_metrics.get('tasks_without_tests', []))}\n"
            context += f"- Verification notes provided: {test_metrics.get('verification_notes_provided', 0)}\n"

        # Critical issues
        issues = test_compliance.get('issues', [])
        high_issues = [i for i in issues if i.get('severity') == 'high']
        if high_issues:
            context += "\n### Critical Testing Issues\n"
            for issue in high_issues[:5]:
                context += f"- **{issue['type']}**: {issue.get('message', '')}\n"

        # Top recommendations
        recommendations = test_compliance.get('recommendations', [])
        if recommendations:
            context += "\n### Test-Related Prompt Improvements Needed\n"
            for rec in recommendations[:3]:
                context += f"- **[{rec['priority'].upper()}]** {rec['title']}: {rec['prompt_change']}\n"

    return context


def _parse_recommendations(review_text: str) -> List[Dict[str, Any]]:
    """
    Parse structured recommendations from Claude's review text.

    First looks for structured JSON data, then falls back to markdown parsing.
    Returns a list of structured recommendation dictionaries for JSONB storage.

    Returns:
        List of dicts with keys: title, priority, theme, problem,
        current_text, proposed_text, impact, confidence, evidence
    """
    import re
    import json

    # First, try to extract structured JSON from the response
    json_match = re.search(r'```json\s*\n(\{.*?"structured_recommendations".*?\})\s*\n```',
                          review_text, re.DOTALL)

    if json_match:
        try:
            json_data = json.loads(json_match.group(1))
            if 'structured_recommendations' in json_data:
                # logger.info(f"Extracted {len(json_data['structured_recommendations'])} structured recommendations from JSON")
                return json_data['structured_recommendations']
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse structured JSON recommendations: {e}")

    # Fallback: Parse from markdown RECOMMENDATIONS section
    logger.info("No structured JSON found")
    recommendations = []
    return recommendations


def _extract_executive_summary(review_text: str) -> Dict[str, Any]:
    """
    Extract the Executive Summary section from review text.

    Returns structured summary data for the review_summary JSONB field:
    {
        'rating': int,
        'one_line': str,
        'summary': str
    }
    """
    import re

    # Find the Executive Summary section (rating may be integer or decimal like 8.5)
    summary_match = re.search(
        r'## Executive Summary\s*\n\*\*Session Rating: (\d+(?:\.\d+)?)/10\*\* - (.+?)\n\n(.+?)(?=\n##|\Z)',
        review_text,
        re.DOTALL
    )

    if summary_match:
        rating = round(float(summary_match.group(1)))
        one_line = summary_match.group(2).strip()
        summary_text = summary_match.group(3).strip()

        return {
            'rating': rating,
            'one_line': one_line,
            'summary': summary_text
        }

    return {}


def _extract_rating_from_review(review_text: str) -> Optional[int]:
    """
    Extract numerical rating from review text.

    Looks for patterns like "Rating: 8/10" or "Quality: 7/10".
    """
    import re

    # Common patterns (support decimal ratings like 8.5/10)
    patterns = [
        r'Rating:\s*(\d+(?:\.\d+)?)/10',
        r'Quality:\s*(\d+(?:\.\d+)?)/10',
        r'Overall Rating:\s*(\d+(?:\.\d+)?)/10',
        r'Session Quality Rating:\s*(\d+(?:\.\d+)?)/10'
    ]

    for pattern in patterns:
        match = re.search(pattern, review_text, re.IGNORECASE)
        if match:
            rating = round(float(match.group(1)))
            if 1 <= rating <= 10:
                return rating

    return None


# Example usage and testing
if __name__ == "__main__":
    import sys

    # Test with a specific session
    if len(sys.argv) < 3:
        print("Usage: python review_client.py <project_path> <session_number>")
        sys.exit(1)

    project_path = Path(sys.argv[1])
    session_number = int(sys.argv[2])

    async def test_review():
        # Find session by number
        async with DatabaseManager() as db:
            async with db.acquire() as conn:
                session = await conn.fetchrow(
                    """
                    SELECT s.* FROM sessions s
                    JOIN projects p ON s.project_id = p.id
                    WHERE p.name = $1 AND s.session_number = $2
                    """,
                    project_path.name,
                    session_number
                )

                if not session:
                    print(f"Session {session_number} not found for project {project_path.name}")
                    sys.exit(1)

                session_id = session['id']

        # Run deep review
        result = await run_deep_review(
            session_id=session_id,
            project_path=project_path
        )

        print("\n" + "="*80)
        print(f"Deep Review Complete - Session {session_number}")
        print("="*80)
        print(f"\nQuality Rating: {result['overall_rating']}/10")
        print(f"\nCritical Issues: {len(result['critical_issues'])}")
        for issue in result['critical_issues']:
            print(f"  {issue}")
        print(f"\nFull review stored in database (check_id: {result['check_id']})")
        print("="*80)

    # Run async test
    asyncio.run(test_review())
