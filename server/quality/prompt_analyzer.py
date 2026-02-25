"""
Prompt Improvement Analyzer (Refactored)
=========================================

Analyzes deep review recommendations across sessions to generate
consolidated, evidence-backed prompt improvement proposals.

**Architecture:**
1. Query sessions with prompt_improvements from session_deep_reviews
2. Parse RECOMMENDATIONS section from review_text markdown
3. Cluster similar recommendations by theme
4. Calculate evidence metrics (frequency, sessions, quality)
5. Generate prioritized proposals with confidence scores

**Status:** Phase 2 of Review Prompt Refactoring
**Created:** December 25, 2025
"""

import asyncio
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from server.database.operations import TaskDatabase

logger = logging.getLogger(__name__)


class PromptImprovementAnalyzer:
    """
    Analyzes prompt improvement recommendations from deep reviews.

    Uses the refactored review system with session_deep_reviews table.
    """

    def __init__(self, db: TaskDatabase):
        self.db = db

    async def analyze_project(
        self,
        project_id: UUID,
        min_reviews: int = 3,
        store_in_db: bool = True,
        triggered_by: str = "manual",
        analysis_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Analyze prompt improvements for a single project.

        Args:
            project_id: Project UUID to analyze
            min_reviews: Minimum number of deep reviews required
            store_in_db: Whether to store results in database
            triggered_by: Who/what triggered the analysis
            analysis_id: Pre-created analysis ID (for background tasks)

        Returns:
            Analysis results with consolidated proposals and analysis_id if stored
        """
        logger.info(f"Starting prompt improvement analysis for project {project_id}")

        # Get project info to determine sandbox_type
        project = await self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # Extract sandbox_type from metadata
        metadata = project.get('metadata', {})
        if isinstance(metadata, str):
            import json
            metadata = json.loads(metadata)

        # Get sandbox_type - default to 'docker' if not specified
        sandbox_type = metadata.get('settings', {}).get('sandbox_type', 'docker')

        # Create analysis record if storing in DB (or use provided ID)
        if store_in_db and not analysis_id:
            # Create new analysis record
            analysis_id = await self._create_analysis_record(
                project_ids=[project_id],
                sandbox_type=sandbox_type,
                triggered_by=triggered_by
            )
        # else: use the pre-created analysis_id from background task

        try:
            # 1. Fetch deep reviews with recommendations
            reviews = await self._fetch_deep_reviews(project_id)

            if len(reviews) < min_reviews:
                logger.warning(
                    f"Not enough deep reviews ({len(reviews)} < {min_reviews}). "
                    f"Analysis requires at least {min_reviews} reviews."
                )

                if store_in_db and analysis_id:
                    await self._mark_analysis_failed(
                        analysis_id,
                        f"Insufficient data: {len(reviews)} reviews < {min_reviews} required"
                    )

                return {
                    "status": "insufficient_data",
                    "reviews_found": len(reviews),
                    "min_required": min_reviews,
                    "proposals": [],
                    "analysis_id": str(analysis_id) if analysis_id else None
                }

            logger.info(f"Found {len(reviews)} deep reviews with recommendations")

            # 2. Get recommendations from reviews
            parsed_reviews = []
            for review in reviews:
                # Get recommendations from the prompt_improvements JSONB field
                structured_recommendations = review.get('prompt_improvements', [])

                # Ensure structured_recommendations is a list
                if isinstance(structured_recommendations, str):
                    try:
                        structured_recommendations = json.loads(structured_recommendations)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"Could not parse prompt_improvements for session {review.get('session_id')}")
                        structured_recommendations = []

                # Ensure it's a list
                if not isinstance(structured_recommendations, list):
                    structured_recommendations = []

                if structured_recommendations:
                    parsed_reviews.append({
                        'session_id': review['session_id'],
                        'session_number': review['session_number'],
                        'overall_rating': review['overall_rating'],
                        'prompt_improvements': structured_recommendations,  # Use parsed version
                        'recommendations': structured_recommendations  # Already structured!
                    })

            logger.info(f"Loaded structured recommendations from {len(parsed_reviews)} reviews")

            # 3. Aggregate by theme
            themes = self._aggregate_by_theme(parsed_reviews)

            # 4. Generate proposals
            proposals = self._generate_proposals(themes)

            # 5. Consolidate proposals with AI where needed
            logger.info(f"Consolidating {len(proposals)} proposals...")
            # Store themes for access in consolidation
            self._current_themes = themes
            proposals_consolidated = await self._consolidate_proposals_with_ai(
                proposals,
                sandbox_type
            )

            # 6. Store in database (always store)
            await self._store_analysis_results(
                analysis_id,
                sandbox_type,
                parsed_reviews,
                themes,
                proposals_consolidated
            )
            logger.info(f"Stored analysis results in database (ID: {analysis_id})")

            return {
                "status": "completed",
                "analysis_id": str(analysis_id),
                "reviews_analyzed": len(parsed_reviews),
                "themes_identified": len(themes),
                "proposals_generated": len(proposals_consolidated),
                "proposals": proposals_consolidated,
                "themes": themes
            }

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            await self._mark_analysis_failed(analysis_id, str(e))
            raise

    async def _fetch_deep_reviews(self, project_id: UUID) -> List[Dict[str, Any]]:
        """
        Fetch all deep reviews with prompt_improvements for a project.

        Uses the session_deep_reviews table (new schema).
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    dr.id,
                    dr.session_id,
                    s.session_number,
                    dr.overall_rating,
                    dr.review_text,
                    dr.prompt_improvements,
                    dr.model,
                    dr.created_at
                FROM session_deep_reviews dr
                JOIN sessions s ON dr.session_id = s.id
                WHERE s.project_id = $1
                  AND jsonb_array_length(dr.prompt_improvements) > 0
                ORDER BY s.session_number ASC
                """,
                project_id
            )

            results = []
            for row in rows:
                result = dict(row)
                # Parse JSONB fields
                if isinstance(result.get('prompt_improvements'), str):
                    try:
                        result['prompt_improvements'] = json.loads(result['prompt_improvements'])
                    except json.JSONDecodeError:
                        result['prompt_improvements'] = []
                results.append(result)

            return results
        

    def _aggregate_by_theme(
        self,
        parsed_reviews: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate recommendations by theme using keyword matching.

        Groups similar recommendations together based on their titles and content.

        Returns:
            Dict mapping theme_name -> {
                'recommendations': List of recommendation objects,
                'sessions': List of session info,
                'frequency': int,
                'avg_quality': float,
                'unique_sessions': int
            }
        """
        # Theme keywords for categorization
        theme_keywords = {
            'browser_verification': ['browser', 'screenshot', 'agent-browser', 'visual', 'verify', 'ui'],
            'tool_usage': ['tool', 'bash', 'command', 'wrong tool'],
            'error_handling': ['error', 'recovery', 'debugging', 'fix', 'retry', 'exception'],
            'git_commits': ['commit', 'git', 'message', 'co-author', 'version control'],
            'testing': ['test', 'testing', 'unit test', 'e2e', 'coverage', 'verification'],
            'parallel_execution': ['parallel', 'concurrent', 'independent', 'simultaneous'],
            'task_management': ['task', 'epic', 'checklist', 'todo', 'workflow'],
            'prompt_adherence': ['prompt', 'instruction', 'guideline', 'follow', 'adherence'],
        }

        themes = defaultdict(lambda: {
            'recommendations': [],
            'sessions': {},  # Use dict for deduplication
            'frequency': 0
        })

        for review in parsed_reviews:
            session_id = str(review['session_id'])
            session_info = {
                'session_id': session_id,
                'session_number': review['session_number'],
                'overall_rating': review['overall_rating']
            }

            for rec in review['recommendations']:
                # Skip if rec is not a dictionary
                if not isinstance(rec, dict):
                    continue

                # Use theme field if present (from structured recommendations)
                matched_themes = []
                if 'theme' in rec and rec['theme']:
                    matched_themes = [rec['theme']]

                # Default to 'general' if no match
                if not matched_themes:
                    matched_themes = ['general']

                # Add to each matched theme
                for theme in matched_themes:
                    themes[theme]['recommendations'].append({
                        **rec,
                        'session_number': review['session_number'],
                        'session_rating': review['overall_rating']
                    })
                    themes[theme]['frequency'] += 1

                    # Track unique sessions
                    if session_id not in themes[theme]['sessions']:
                        themes[theme]['sessions'][session_id] = session_info

        # Calculate averages and convert sessions dict to list
        result = {}
        for theme_name, data in themes.items():
            sessions_list = list(data['sessions'].values())
            unique_sessions = len(sessions_list)

            if unique_sessions > 0:
                avg_quality = sum(s['overall_rating'] for s in sessions_list) / unique_sessions

                result[theme_name] = {
                    'theme_name': theme_name,
                    'recommendations': data['recommendations'],
                    'sessions': sessions_list,
                    'frequency': data['frequency'],
                    'avg_quality': avg_quality,
                    'unique_sessions': unique_sessions
                }

        return result

    def _generate_proposals(
        self,
        themes: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate consolidated proposals from themed recommendations.

        Each proposal includes:
        - title: Consolidated title
        - theme: Theme category
        - priority: Calculated from individual priorities
        - problem: Consolidated problem statement
        - proposed_text: Best proposal (or merged)
        - impact: Expected impact
        - evidence: Session IDs, frequency, quality metrics
        - confidence_level: 1-10 score
        """
        proposals = []

        # Sort themes by frequency (most common first)
        sorted_themes = sorted(
            themes.items(),
            key=lambda x: (x[1]['frequency'], x[1]['avg_quality']),
            reverse=True
        )

        for theme_name, theme_data in sorted_themes:
            # Skip low-frequency themes
            if theme_data['frequency'] < 2:
                continue

            # Consolidate recommendations
            recommendations = theme_data['recommendations']

            # Find most common priority
            priority_counts = defaultdict(int)
            for rec in recommendations:
                priority_counts[rec['priority']] += 1
            consolidated_priority = max(priority_counts.items(), key=lambda x: x[1])[0]

            # Get unique titles (for consolidated title)
            titles = list(set(rec['title'] for rec in recommendations))
            consolidated_title = titles[0] if len(titles) == 1 else f"{theme_name.replace('_', ' ').title()} Improvements"

            # Consolidate problems
            problems = [rec['problem'] for rec in recommendations if rec['problem']]
            consolidated_problem = problems[0] if problems else f"Multiple {theme_name} issues identified"

            # Get best proposed text (longest/most detailed)
            proposed_texts = [rec['proposed_text'] for rec in recommendations if rec['proposed_text']]
            best_proposed = max(proposed_texts, key=len) if proposed_texts else ""

            # Get current text example
            current_texts = [rec['current_text'] for rec in recommendations if rec['current_text']]
            example_current = current_texts[0] if current_texts else ""

            # Consolidate impact
            impacts = [rec['impact'] for rec in recommendations if rec['impact']]
            consolidated_impact = impacts[0] if impacts else f"Improves {theme_name} across sessions"

            # Calculate confidence
            confidence = self._calculate_confidence(theme_data, consolidated_priority)

            # Create proposal
            proposal = {
                'title': consolidated_title,
                'theme': theme_name,
                'priority': consolidated_priority,
                'problem': consolidated_problem,
                'current_text': example_current,
                'proposed_text': best_proposed,
                'impact': consolidated_impact,
                'evidence': {
                    'frequency': theme_data['frequency'],
                    'unique_sessions': theme_data['unique_sessions'],
                    'avg_quality': round(theme_data['avg_quality'], 1),
                    'session_numbers': [s['session_number'] for s in theme_data['sessions']],
                    'session_ids': [s['session_id'] for s in theme_data['sessions']]
                },
                'confidence_level': confidence
            }

            proposals.append(proposal)

        # Deduplicate proposals with identical proposed_text
        # This can happen when multiple themes identify the same underlying issue
        deduplicated = []
        seen_texts = {}  # proposed_text -> index in deduplicated

        for proposal in proposals:
            proposed_text = proposal['proposed_text']

            if proposed_text in seen_texts:
                # Merge with existing proposal
                idx = seen_texts[proposed_text]
                existing = deduplicated[idx]

                # Combine themes
                existing['theme'] = f"{existing['theme']}, {proposal['theme']}"

                # Update title if different
                if proposal['title'] not in existing['title']:
                    existing['title'] = f"{existing['title']} / {proposal['title']}"

                # Merge evidence (combine session lists)
                existing['evidence']['frequency'] += proposal['evidence']['frequency']
                existing['evidence']['unique_sessions'] = max(
                    existing['evidence']['unique_sessions'],
                    proposal['evidence']['unique_sessions']
                )

                # Combine session IDs (deduplicate)
                existing_sessions = set(existing['evidence']['session_ids'])
                new_sessions = set(proposal['evidence']['session_ids'])
                combined_sessions = existing_sessions | new_sessions
                existing['evidence']['session_ids'] = list(combined_sessions)

                # Combine session numbers (deduplicate)
                existing_numbers = set(existing['evidence']['session_numbers'])
                new_numbers = set(proposal['evidence']['session_numbers'])
                combined_numbers = existing_numbers | new_numbers
                existing['evidence']['session_numbers'] = sorted(list(combined_numbers))

                # Update unique_sessions count based on merged data
                existing['evidence']['unique_sessions'] = len(combined_sessions)

                # Take higher confidence
                existing['confidence_level'] = max(
                    existing['confidence_level'],
                    proposal['confidence_level']
                )

            else:
                # New unique proposal
                seen_texts[proposed_text] = len(deduplicated)
                deduplicated.append(proposal)

        # Sort by confidence (highest first)
        deduplicated.sort(key=lambda x: x['confidence_level'], reverse=True)

        return deduplicated

    def _calculate_confidence(
        self,
        theme_data: Dict[str, Any],
        priority: str
    ) -> int:
        """
        Calculate confidence score (1-10) based on evidence.

        Factors:
        - Number of unique sessions mentioning it
        - Average quality of those sessions
        - Priority level
        - Frequency
        """
        unique_sessions = theme_data['unique_sessions']
        avg_quality = theme_data['avg_quality']
        frequency = theme_data['frequency']

        # Base confidence from session count
        if unique_sessions >= 5:
            base = 9
        elif unique_sessions >= 3:
            base = 7
        elif unique_sessions >= 2:
            base = 5
        else:
            base = 3

        # Adjust for priority
        priority_boost = {'High': 1, 'Medium': 0, 'Low': -1}
        base += priority_boost.get(priority, 0)

        # Adjust for quality
        if avg_quality >= 8:
            base += 1
        elif avg_quality < 6:
            base -= 1

        # Cap at 1-10
        return max(1, min(10, base))

    # Database operations

    async def _create_analysis_record(
        self,
        project_ids: List[UUID],
        sandbox_type: str,
        triggered_by: str = "manual"
    ) -> UUID:
        """Create initial analysis record in database."""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO prompt_improvement_analyses (
                    projects_analyzed,
                    sandbox_type,
                    triggered_by,
                    status
                )
                VALUES ($1, $2, $3, 'running')
                RETURNING id
                """,
                project_ids,
                sandbox_type,
                triggered_by
            )
            return row['id']

    async def _mark_analysis_failed(self, analysis_id: UUID, error: str):
        """Mark analysis as failed."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE prompt_improvement_analyses
                SET
                    status = 'failed',
                    completed_at = NOW(),
                    notes = $1
                WHERE id = $2
                """,
                error,
                analysis_id
            )

    async def _consolidate_proposals_with_ai(
        self,
        proposals: List[Dict[str, Any]],
        sandbox_type: str
    ) -> List[Dict[str, Any]]:
        """
        For proposals with multiple recommendations, use AI to consolidate them.
        For proposals with single recommendations, use them as-is.
        """
        consolidated_proposals = []

        for proposal in proposals:
            theme_data = self._current_themes.get(proposal['theme'], {})
            recommendations = theme_data.get('recommendations', [])

            # Get unique proposed texts for this theme
            unique_proposed_texts = []
            seen_texts = set()
            for rec in recommendations:
                text = rec.get('proposed_text', '').strip()
                if text and text not in seen_texts:
                    unique_proposed_texts.append(text)
                    seen_texts.add(text)

            if len(unique_proposed_texts) <= 1:
                # Single or no proposed text - use as-is
                consolidated_proposals.append(proposal)
            else:
                # Multiple different proposals - consolidate with AI
                logger.info(f"Consolidating {len(unique_proposed_texts)} proposals for theme '{proposal['theme']}'")
                consolidated_text = await self._consolidate_with_ai(
                    theme=proposal['theme'],
                    problem=proposal.get('problem', ''),
                    recommendations=recommendations,
                    unique_proposals=unique_proposed_texts
                )

                # Update proposal with AI-consolidated text
                proposal['proposed_text'] = consolidated_text
                proposal['consolidation_note'] = f"Consolidated {len(unique_proposed_texts)} proposals with AI"
                consolidated_proposals.append(proposal)

        return consolidated_proposals

    async def _consolidate_with_ai(
        self,
        theme: str,
        problem: str,
        recommendations: List[Dict[str, Any]],
        unique_proposals: List[str]
    ) -> str:
        """
        Use AI to consolidate multiple proposed texts into one best version.
        Returns the consolidated proposed_text directly (not JSON).
        """
        import os

        # Build consolidation prompt with emphasis on brevity
        prompt = f"""You are consolidating multiple improvement suggestions for the theme: {theme}

Problem being addressed: {problem}

Here are {len(unique_proposals)} different proposed improvements from various sessions:

"""
        for i, proposed_text in enumerate(unique_proposals, 1):
            prompt += f"---\nProposal {i}:\n{proposed_text}\n\n"

        prompt += """Please analyze these proposals and create a single, CONCISE consolidated version that:
1. Combines the best aspects of each proposal
2. Keeps the result minimal and focused (typically 1-10 lines)
3. Maintains consistency with the coding agent prompt style
4. Is ready to be directly inserted into the prompt file

IMPORTANT: Keep your consolidated version BRIEF. The entire prompt file is under 250 lines,
so replacements should be proportionally small. Focus only on the essential changes.

Return ONLY the consolidated text that should replace the problematic section in the prompt.
Do not include JSON formatting, markdown code blocks, or explanations.
Just return the exact, concise text to use as the replacement."""

        # Use Claude to consolidate
        from server.quality.reviews import create_review_client

        model = os.getenv('DEFAULT_REVIEW_MODEL', 'claude-sonnet-4-6')
        client = create_review_client(model=model)

        try:
            async with client:
                # Send prompt and get response
                await client.query(prompt)

                # Collect response text
                response_text = ""
                async for msg in client.receive_response():
                    msg_type = type(msg).__name__
                    if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                        for block in msg.content:
                            block_type = type(block).__name__
                            if block_type == "TextBlock" and hasattr(block, "text"):
                                response_text += block.text

            response_text = response_text.strip()

            # If we got a good response, return it
            if response_text:
                logger.info(f"Successfully consolidated {len(unique_proposals)} proposals into {len(response_text)} chars")
                return response_text

            # Fallback to longest proposal
            logger.warning("AI consolidation returned empty, using longest proposal")
            return max(unique_proposals, key=len) if unique_proposals else ""

        except Exception as e:
            logger.error(f"Failed to consolidate with AI: {e}")
            # Return the longest proposal as fallback
            return max(unique_proposals, key=len) if unique_proposals else ""


    async def _store_analysis_results(
        self,
        analysis_id: UUID,
        sandbox_type: str,
        parsed_reviews: List[Dict[str, Any]],
        themes: Dict[str, Dict[str, Any]],
        proposals: List[Dict[str, Any]]
    ):
        """Store analysis results and proposals in database."""
        async with self.db.acquire() as conn:
            # Update analysis record
            await conn.execute(
                """
                UPDATE prompt_improvement_analyses
                SET
                    status = 'completed',
                    completed_at = NOW(),
                    sessions_analyzed = $1,
                    patterns_identified = $2,
                    proposed_changes = $3
                WHERE id = $4
                """,
                len(parsed_reviews),
                json.dumps(themes, default=str),  # default=str to handle UUIDs
                json.dumps([p['title'] for p in proposals]),
                analysis_id
            )

            # Determine correct prompt file based on sandbox_type
            prompt_file = f'coding_prompt_{sandbox_type}.md'

            # Store each proposal
            for proposal in proposals:
                # Extract metadata
                metadata = {
                    'consolidation_note': proposal.get('consolidation_note', ''),
                    'impact': proposal.get('impact', ''),
                    'priority': proposal.get('priority', 'Medium')
                }

                await conn.execute(
                    """
                    INSERT INTO prompt_proposals (
                        analysis_id,
                        prompt_file,
                        section_name,
                        original_text,
                        proposed_text,
                        change_type,
                        rationale,
                        evidence,
                        confidence_level,
                        status,
                        metadata
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'proposed', $10)
                    """,
                    analysis_id,
                    prompt_file,
                    proposal['theme'],
                    proposal.get('current_text', ''),  # Original problem example from reviews
                    proposal.get('proposed_text', ''),  # Consolidated solution text
                    'modification',
                    f"{proposal['title']} - {proposal.get('problem', '')[:200]}",
                    json.dumps(proposal['evidence'], default=str),
                    proposal['confidence_level'],
                    json.dumps(metadata)
                )


# Standalone analysis function for testing
async def analyze_project_improvements(
    project_id: UUID,
    min_reviews: int = 3
) -> Dict[str, Any]:
    """
    Convenience function to analyze a project's prompt improvements.

    Args:
        project_id: Project UUID
        min_reviews: Minimum deep reviews required

    Returns:
        Analysis results
    """
    from server.database.connection import get_db

    db = await get_db()
    analyzer = PromptImprovementAnalyzer(db)
    results = await analyzer.analyze_project(project_id, min_reviews)
    return results


if __name__ == "__main__":
    # CLI for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python prompt_improvement_analyzer.py <project_id>")
        sys.exit(1)

    project_id = UUID(sys.argv[1])
    min_reviews = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    results = asyncio.run(analyze_project_improvements(project_id, min_reviews))

    print(f"\n{'='*60}")
    print(f"Prompt Improvement Analysis Results")
    print(f"{'='*60}\n")
    print(f"Status: {results['status']}")
    print(f"Reviews Analyzed: {results.get('reviews_analyzed', 0)}")
    print(f"Themes Identified: {results.get('themes_identified', 0)}")
    print(f"Proposals Generated: {results.get('proposals_generated', 0)}\n")

    if results['status'] == 'completed':
        print(f"{'='*60}")
        print(f"PROPOSALS (sorted by confidence)")
        print(f"{'='*60}\n")

        for i, proposal in enumerate(results['proposals'], 1):
            print(f"{i}. {proposal['title']}")
            print(f"   Theme: {proposal['theme']}")
            print(f"   Priority: {proposal['priority']}")
            print(f"   Confidence: {proposal['confidence_level']}/10")
            print(f"   Evidence: {proposal['evidence']['unique_sessions']} sessions, "
                  f"{proposal['evidence']['frequency']} mentions, "
                  f"avg quality {proposal['evidence']['avg_quality']}/10")
            print(f"   Sessions: {proposal['evidence']['session_numbers']}")
            print()
