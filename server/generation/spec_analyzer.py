"""
Spec Pre-Analysis Module
=========================

Optional pre-analysis of specification files using a fast/cheap model.
Generates a condensed summary, feature list, and suggested epic structure
that is injected into the initializer prompt to improve planning quality.

Follows the brownfield codebase_analysis pattern:
  analyze -> store in DB -> inject into prompt.
"""

import json
import os
import re
from typing import Dict, Any
from pathlib import Path
from dotenv import load_dotenv

from anthropic import AsyncAnthropic
from server.utils.logging import get_logger

# Load environment variables
_project_root = Path(__file__).parent.parent.parent
load_dotenv(dotenv_path=_project_root / ".env")

logger = get_logger(__name__)

ANALYSIS_PROMPT = """You are analyzing an application specification to help an AI agent create a development roadmap.

Read the specification below and produce a structured analysis in JSON format with these fields:

1. "summary": A 2-3 sentence condensed description of what the application does.
2. "key_features": A list of 10-20 distinct features/capabilities described in the spec.
3. "technical_requirements": A list of specific technical requirements (languages, frameworks, APIs, databases, etc.).
4. "suggested_epics": A list of 15-25 high-level epic suggestions, each with "name" and "rationale" fields. Order by implementation priority (foundational first).
5. "complexity_assessment": One of "small" (< 15 epics), "medium" (15-20 epics), or "large" (20+ epics).
6. "key_risks": A list of 3-5 technical risks or challenges identified in the spec.

Return ONLY valid JSON. No markdown code fences, no explanation text.

## Specification

{spec_content}"""


async def analyze_spec(
    spec_content: str,
    model: str = "claude-haiku-4-5-20251001",
) -> Dict[str, Any]:
    """
    Analyze specification content using a fast/cheap Claude model.

    Args:
        spec_content: Concatenated specification text.
        model: Claude model to use (default: Haiku for cost efficiency).

    Returns:
        Dict with analysis results (summary, features, epics, etc.).

    Raises:
        ValueError: If API call fails or response is not valid JSON.
    """
    api_key = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
    if not api_key:
        raise ValueError("CLAUDE_CODE_OAUTH_TOKEN not configured for spec analysis")

    client = AsyncAnthropic(api_key=api_key)
    prompt = ANALYSIS_PROMPT.format(spec_content=spec_content)

    logger.info(f"Running spec pre-analysis with {model} ({len(spec_content)} chars)")

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    # Parse JSON response
    try:
        analysis = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: extract JSON from markdown code fences
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            raise ValueError(f"Spec analysis returned invalid JSON: {text[:200]}")

    # Ensure required fields have defaults
    required_lists = ["key_features", "technical_requirements", "suggested_epics", "key_risks"]
    for field in required_lists:
        if field not in analysis:
            analysis[field] = []
    if "summary" not in analysis:
        analysis["summary"] = "Analysis incomplete"
    if "complexity_assessment" not in analysis:
        analysis["complexity_assessment"] = "medium"

    logger.info(
        f"Spec analysis complete: {len(analysis.get('key_features', []))} features, "
        f"{len(analysis.get('suggested_epics', []))} suggested epics, "
        f"complexity: {analysis.get('complexity_assessment', 'unknown')}"
    )

    return analysis
