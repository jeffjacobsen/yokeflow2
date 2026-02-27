"""
Test Compliance Analyzer - Enhanced Quality Analysis for Hybrid Testing
======================================================================

Analyzes coding session logs to detect testing compliance issues and
agent errors in the hybrid testing workflow.

This module extends the quality review system to specifically analyze:
1. Test requirement retrieval and verification patterns
2. Proper use of testing tools (get_task_tests, update_task_test_result, etc.)
3. Verification note quality and completeness
4. Common agent errors in test execution
5. Prompt compliance issues specific to testing

Usage:
    from server.quality.test_compliance_analyzer import analyze_test_compliance

    results = await analyze_test_compliance(
        session_id=session_uuid,
        jsonl_path=Path("logs/session_001.jsonl")
    )
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


class TestComplianceAnalyzer:
    """Analyzes session logs for testing compliance and quality issues."""

    def __init__(self, jsonl_path: Path):
        """Initialize with a session JSONL log path."""
        self.jsonl_path = jsonl_path
        self.events = []
        self.issues = []
        self.patterns = []
        self.recommendations = []

    def analyze(self) -> Dict[str, Any]:
        """
        Perform complete analysis of testing compliance.

        Returns:
            Dict containing:
            - compliance_score: 0-100 score for testing compliance
            - issues: List of detected issues
            - patterns: Recurring error patterns
            - recommendations: Specific prompt improvements
            - metrics: Detailed testing metrics
        """
        # Load and parse events
        self._load_events()

        # Analyze different aspects
        test_metrics = self._analyze_test_workflow()
        tool_errors = self._analyze_tool_errors()
        verification_quality = self._analyze_verification_quality()
        prompt_violations = self._analyze_prompt_compliance()

        # Calculate compliance score
        compliance_score = self._calculate_compliance_score(
            test_metrics, tool_errors, verification_quality, prompt_violations
        )

        # Generate recommendations
        self._generate_recommendations()

        return {
            'compliance_score': compliance_score,
            'issues': self.issues,
            'patterns': self.patterns,
            'recommendations': self.recommendations,
            'metrics': {
                'test_workflow': test_metrics,
                'tool_errors': tool_errors,
                'verification_quality': verification_quality,
                'prompt_violations': prompt_violations
            }
        }

    def _load_events(self):
        """Load and parse JSONL events."""
        with open(self.jsonl_path, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    self.events.append(event)
                except json.JSONDecodeError:
                    continue

    def _analyze_test_workflow(self) -> Dict[str, Any]:
        """
        Analyze the testing workflow compliance.

        Checks for:
        - Proper sequence: get_task_tests -> verification -> update_task_test_result
        - Tasks marked complete without testing
        - Epic tests run when required
        - Verification notes provided
        """
        metrics = {
            'tasks_completed': 0,
            'tasks_tested_properly': 0,
            'tasks_without_tests': [],
            'epic_tests_run': 0,
            'epic_tests_required': 0,
            'verification_notes_provided': 0,
            'test_sequence_violations': []
        }

        # Track task lifecycle
        task_states = {}  # task_id -> {started, tests_retrieved, tests_updated, completed}
        current_task = None

        for event in self.events:
            if event.get('event') == 'tool_use':
                tool_name = event.get('tool_name', '')
                params = event.get('input') or event.get('parameters', {})

                # Task lifecycle tracking
                if tool_name == 'mcp__task-manager__start_task':
                    task_id = params.get('task_id')
                    if task_id:
                        current_task = task_id
                        task_states[task_id] = {
                            'started': True,
                            'tests_retrieved': False,
                            'tests_updated': False,
                            'completed': False,
                            'timestamp': event.get('timestamp')
                        }

                elif tool_name == 'mcp__task-manager__get_task_tests' and current_task:
                    if current_task in task_states:
                        task_states[current_task]['tests_retrieved'] = True

                elif tool_name == 'mcp__task-manager__update_task_test_result':
                    test_task_id = params.get('task_id')  # Some tests include task_id
                    verification_notes = params.get('verification_notes')

                    if current_task and current_task in task_states:
                        task_states[current_task]['tests_updated'] = True
                        if verification_notes:
                            metrics['verification_notes_provided'] += 1

                elif tool_name == 'mcp__task-manager__update_task_status':
                    task_id = params.get('task_id')
                    done = params.get('done')

                    if done and task_id in task_states:
                        task_states[task_id]['completed'] = True
                        metrics['tasks_completed'] += 1

                        # Check if tests were properly done
                        state = task_states[task_id]
                        if state['tests_retrieved'] and state['tests_updated']:
                            metrics['tasks_tested_properly'] += 1
                        elif not state['tests_retrieved']:
                            metrics['tasks_without_tests'].append(task_id)
                            self.issues.append({
                                'type': 'test_workflow_violation',
                                'severity': 'high',
                                'message': f'Task {task_id} marked complete without retrieving tests',
                                'task_id': task_id
                            })

                # Epic test tracking
                elif tool_name == 'mcp__task-manager__get_epic_tests':
                    metrics['epic_tests_run'] += 1

                elif tool_name == 'mcp__task-manager__update_epic_test_result':
                    verification_notes = params.get('verification_notes')
                    if verification_notes:
                        metrics['verification_notes_provided'] += 1

        # Check for sequence violations
        for task_id, state in task_states.items():
            if state['completed'] and not state['tests_retrieved']:
                metrics['test_sequence_violations'].append({
                    'task_id': task_id,
                    'issue': 'completed_without_test_retrieval'
                })
            elif state['tests_updated'] and not state['tests_retrieved']:
                metrics['test_sequence_violations'].append({
                    'task_id': task_id,
                    'issue': 'updated_tests_without_retrieval'
                })

        return metrics

    def _analyze_tool_errors(self) -> Dict[str, Any]:
        """
        Analyze tool usage errors and patterns.

        Identifies:
        - Common tool errors (wrong parameters, missing tools, etc.)
        - Repeated error patterns
        - Recovery attempts and success rates
        """
        metrics = {
            'total_errors': 0,
            'error_types': {},
            'repeated_errors': [],
            'recovery_attempts': 0,
            'successful_recoveries': 0,
            'testing_tool_errors': []
        }

        last_tool = None
        error_history = []

        for i, event in enumerate(self.events):
            if event.get('event') == 'tool_use':
                last_tool = event.get('tool_name')

            elif event.get('event') == 'tool_result' and event.get('is_error'):
                error_msg = event.get('content', '')
                metrics['total_errors'] += 1

                # Categorize error type
                error_type = self._categorize_error(error_msg, last_tool)
                metrics['error_types'][error_type] = metrics['error_types'].get(error_type, 0) + 1

                # Track testing-specific errors
                if last_tool and ('test' in last_tool.lower() or 'epic' in last_tool.lower()):
                    metrics['testing_tool_errors'].append({
                        'tool': last_tool,
                        'error': error_msg[:200],
                        'timestamp': event.get('timestamp')
                    })

                    self.issues.append({
                        'type': 'testing_tool_error',
                        'severity': 'medium',
                        'tool': last_tool,
                        'error': error_msg[:200]
                    })

                # Check for repeated errors
                error_summary = f"{last_tool}:{error_type}"
                if error_summary in [e['summary'] for e in error_history[-5:]]:
                    metrics['repeated_errors'].append(error_summary)
                    self.patterns.append({
                        'type': 'repeated_error',
                        'pattern': error_summary,
                        'frequency': sum(1 for e in error_history if e['summary'] == error_summary)
                    })

                error_history.append({
                    'summary': error_summary,
                    'tool': last_tool,
                    'type': error_type
                })

                # Check if next action is a recovery attempt
                if i + 1 < len(self.events):
                    next_event = self.events[i + 1]
                    if next_event.get('event') == 'tool_use' and next_event.get('tool_name') == last_tool:
                        metrics['recovery_attempts'] += 1
                        # Check if recovery successful (no error in next result)
                        if i + 2 < len(self.events):
                            result_event = self.events[i + 2]
                            if result_event.get('event') == 'tool_result' and not result_event.get('is_error'):
                                metrics['successful_recoveries'] += 1

        return metrics

    def _analyze_verification_quality(self) -> Dict[str, Any]:
        """
        Analyze the quality of test verification.

        Checks:
        - Verification note completeness
        - Appropriate verification methods used
        - Browser testing for UI tasks
        - API testing for backend tasks
        """
        metrics = {
            'total_verifications': 0,
            'verifications_with_notes': 0,
            'note_quality_scores': [],
            'verification_methods': {},
            'ui_tasks_with_browser': 0,
            'api_tasks_with_curl': 0,
            'inappropriate_methods': []
        }

        current_task_type = None

        for event in self.events:
            if event.get('event') == 'tool_use':
                tool_name = event.get('tool_name', '')
                params = event.get('input') or event.get('parameters', {})

                # Track verification updates
                if tool_name in ['mcp__task-manager__update_task_test_result', 'mcp__task-manager__update_epic_test_result']:
                    metrics['total_verifications'] += 1
                    verification_notes = params.get('verification_notes', '')

                    if verification_notes:
                        metrics['verifications_with_notes'] += 1
                        quality_score = self._score_verification_notes(verification_notes)
                        metrics['note_quality_scores'].append(quality_score)

                        if quality_score < 50:
                            self.issues.append({
                                'type': 'low_quality_verification',
                                'severity': 'low',
                                'message': 'Verification notes lack detail',
                                'notes_preview': verification_notes[:100]
                            })

                # Track verification methods from Bash commands
                elif tool_name == 'Bash':
                    command = params.get('command', '').lower()

                    # Detect verification method
                    if 'agent-browser' in command or 'screenshot' in command:
                        metrics['verification_methods']['browser'] = metrics['verification_methods'].get('browser', 0) + 1
                        if current_task_type == 'ui':
                            metrics['ui_tasks_with_browser'] += 1
                    elif 'curl' in command:
                        metrics['verification_methods']['api'] = metrics['verification_methods'].get('api', 0) + 1
                        if current_task_type == 'api':
                            metrics['api_tasks_with_curl'] += 1
                    elif 'pytest' in command or 'python3 -c' in command:
                        metrics['verification_methods']['unit_test'] = metrics['verification_methods'].get('unit_test', 0) + 1
                    elif 'npm test' in command or 'npm run test' in command:
                        metrics['verification_methods']['js_test'] = metrics['verification_methods'].get('js_test', 0) + 1

        return metrics

    def _analyze_prompt_compliance(self) -> Dict[str, Any]:
        """
        Analyze compliance with prompt instructions.

        Checks for:
        - Proper file paths (no /workspace/ prefix)
        - Timeout usage in curl commands
        - Screenshot directory compliance
        - Python version usage
        """
        metrics = {
            'total_violations': 0,
            'workspace_prefix': 0,
            'missing_timeouts': 0,
            'screenshot_directory': 0,
            'python_vs_python3': 0
        }

        for event in self.events:
            if event.get('event') == 'tool_use':
                tool_name = event.get('tool_name', '')
                params = event.get('input') or event.get('parameters', {})

                # Check for /workspace/ prefix in file operations
                if tool_name in ['Read', 'Write', 'Edit']:
                    file_path = params.get('file_path', '')
                    if '/workspace/' in file_path:
                        metrics['workspace_prefix'] += 1
                        metrics['total_violations'] += 1
                        self.issues.append({
                            'type': 'path_error',
                            'severity': 'medium',
                            'message': f'{tool_name} used /workspace/ prefix',
                            'path': file_path
                        })

                # Check Bash commands for compliance issues
                elif tool_name == 'Bash':
                    command = params.get('command', '')

                    # Check curl without timeout
                    if 'curl' in command and '--max-time' not in command:
                        metrics['missing_timeouts'] += 1
                        metrics['total_violations'] += 1
                        self.issues.append({
                            'type': 'missing_timeout',
                            'severity': 'medium',
                            'message': 'curl command without --max-time',
                            'command': command[:100]
                        })

                    # Check python vs python3
                    if re.search(r'\bpython\s', command) and 'python3' not in command:
                        metrics['python_vs_python3'] += 1
                        metrics['total_violations'] += 1
                        self.issues.append({
                            'type': 'python_version',
                            'severity': 'medium',
                            'message': 'Used python instead of python3',
                            'command': command[:100]
                        })

                    # Check screenshot directory
                    if 'agent-browser screenshot' in command or 'agent-browser screenshot' in command.lower():
                        # The standard workflow pipes agent-browser screenshot through xargs mv/cp
                        # to yokeflow/screenshots/. Check if this command or a follow-up does that.
                        if 'yokeflow/screenshots' not in command and not self._check_screenshot_move(event.get('timestamp')):
                            metrics['screenshot_directory'] += 1
                            self.issues.append({
                                'type': 'screenshot_directory',
                                'severity': 'low',
                                'message': 'Screenshot not saved to yokeflow/screenshots/',
                                'command': command[:100]
                            })

        return metrics

    def _categorize_error(self, error_msg: str, tool_name: str) -> str:
        """Categorize an error message into a type."""
        error_lower = error_msg.lower()

        if 'not found' in error_lower or 'no such file' in error_lower:
            return 'file_not_found'
        elif 'permission denied' in error_lower:
            return 'permission_denied'
        elif 'timeout' in error_lower or 'timed out' in error_lower:
            return 'timeout'
        elif 'syntax error' in error_lower:
            return 'syntax_error'
        elif 'import' in error_lower and 'error' in error_lower:
            return 'import_error'
        elif 'connection' in error_lower and ('refused' in error_lower or 'failed' in error_lower):
            return 'connection_error'
        elif 'command not found' in error_lower:
            return 'command_not_found'
        elif 'invalid' in error_lower or 'validation' in error_lower:
            return 'validation_error'
        else:
            return 'other'

    def _score_verification_notes(self, notes: str) -> int:
        """
        Score verification notes quality (0-100).

        Rewards structured notes matching the WHAT/HOW/OUTCOME/ERRORS template
        from the coding prompt, plus specific evidence of observed results.
        """
        import re
        score = 0
        notes_lower = notes.lower()

        # Structure: WHAT/HOW/OUTCOME/ERRORS labels (up to 40 points, 10 each)
        structure_checks = {
            'what': [r'\bwhat\s*:'],
            'how': [r'\bhow\s*:'],
            'outcome': [r'\boutcome\s*:', r'\bresult\s*:', r'\bobserved\s*:'],
            'errors': [r'\berrors?\s*:', r'\bconsole\s*:'],
        }
        for category, patterns in structure_checks.items():
            if any(re.search(p, notes_lower) for p in patterns):
                score += 10

        # Specific evidence: numbers, measurements, codes (up to 30 points)
        evidence_patterns = [
            r'\b[1-5]\d{2}\b',          # HTTP status codes (100-599)
            r'\d+\s*(?:px|em|rem|%|ms)', # CSS/timing values
            r'\d+\s+\S*(?:element|item|card|file|test|row|node|component)', # Counts
            r'https?://\S+',            # URLs
            r'\bnone\b|\bno\s+(?:console\s+)?errors?\b|\b0\s+(?:error|warning|violation)', # No-errors
            r'\b\d+/\d+\b',             # Ratios like "5/5"
        ]
        evidence_count = sum(1 for p in evidence_patterns if re.search(p, notes_lower))
        score += min(30, evidence_count * 10)

        # Reasonable length (up to 20 points) — min 50 chars for meaningful content
        if len(notes) >= 50:
            score += min(20, len(notes) // 20)

        # Penalty: generic notes with no structure AND no evidence (cap at 40)
        generic_only = ['verified', 'tested', 'confirmed', 'working', 'passed', 'checked']
        has_specific = evidence_count > 0
        has_structure = score >= 20  # At least 2 structure labels matched
        if not has_specific and not has_structure and any(g in notes_lower for g in generic_only):
            score = min(score, 40)

        return min(100, score)

    def _check_screenshot_move(self, timestamp: str) -> bool:
        """Check if a screenshot is moved/copied to yokeflow/screenshots/ after being taken."""
        # Look for mv or cp command within next few events
        found_timestamp = False
        events_checked = 0
        for event in self.events:
            if event.get('timestamp') == timestamp:
                found_timestamp = True
                continue

            if found_timestamp and event.get('event') == 'tool_use':
                events_checked += 1
                tool_name = event.get('tool_name', '')
                if tool_name == 'Bash':
                    command = event.get('input', {}).get('command', '')
                    if ('mv' in command or 'cp' in command) and 'yokeflow/screenshots' in command:
                        return True

                # Only check next 3 tool uses
                if events_checked >= 3:
                    break

        return False

    def _calculate_compliance_score(self, test_metrics: Dict, tool_errors: Dict,
                                   verification_quality: Dict, prompt_violations: Dict) -> int:
        """Calculate overall compliance score (0-100)."""
        score = 100

        # Test workflow compliance (40 points)
        if test_metrics['tasks_completed'] > 0:
            test_compliance_rate = test_metrics['tasks_tested_properly'] / test_metrics['tasks_completed']
            score -= (1 - test_compliance_rate) * 40

        # Error rate impact (20 points)
        if tool_errors['total_errors'] > 0:
            # Penalize more for testing tool errors
            testing_error_weight = len(tool_errors['testing_tool_errors']) * 2
            error_penalty = min(20, testing_error_weight + tool_errors['total_errors'] * 0.5)
            score -= error_penalty

        # Verification quality (20 points)
        if verification_quality['total_verifications'] > 0:
            notes_rate = verification_quality['verifications_with_notes'] / verification_quality['total_verifications']
            score -= (1 - notes_rate) * 10

            # Average note quality
            if verification_quality['note_quality_scores']:
                avg_quality = sum(verification_quality['note_quality_scores']) / len(verification_quality['note_quality_scores'])
                score -= (1 - avg_quality / 100) * 10

        # Prompt compliance (20 points)
        violation_penalty = min(20, prompt_violations['total_violations'] * 2)
        score -= violation_penalty

        return max(0, int(score))

    def _generate_recommendations(self):
        """Generate specific recommendations for prompt improvements."""
        # Group issues by type
        issue_counts = {}
        for issue in self.issues:
            issue_type = issue['type']
            issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1

        # High-priority recommendations
        if issue_counts.get('test_workflow_violation', 0) > 0:
            self.recommendations.append({
                'priority': 'high',
                'category': 'test_workflow',
                'title': 'Enforce test retrieval before task completion',
                'description': 'Agent is marking tasks complete without retrieving test requirements',
                'prompt_change': 'Add explicit check: "STOP if get_task_tests not called before update_task_status"',
                'expected_impact': 'Prevent tasks being marked complete without verification'
            })

        # Medium-priority recommendations
        if issue_counts.get('missing_timeout', 0) > 0:
            self.recommendations.append({
                'priority': 'medium',
                'category': 'command_usage',
                'title': 'Enforce curl timeout usage',
                'description': f"Missing --max-time in {issue_counts.get('missing_timeout', 0)} curl commands",
                'prompt_change': 'Add rule: "NEVER use bare curl - ALWAYS add --max-time 5"',
                'expected_impact': 'Prevent 5-minute timeouts'
            })

        if issue_counts.get('low_quality_verification', 0) > 0:
            self.recommendations.append({
                'priority': 'medium',
                'category': 'verification_quality',
                'title': 'Improve verification note quality',
                'description': 'Verification notes lack detail and specific test outcomes',
                'prompt_change': 'Add template: "verification_notes should include: ✅ What was tested, ✅ How it was verified, ✅ Specific outcomes"',
                'expected_impact': 'Better test documentation and debugging'
            })

        # Low-priority recommendations
        if issue_counts.get('screenshot_directory', 0) > 0:
            self.recommendations.append({
                'priority': 'low',
                'category': 'file_organization',
                'title': 'Consistent screenshot directory usage',
                'description': 'Screenshots not consistently saved to yokeflow/screenshots/',
                'prompt_change': 'Emphasize: "ALWAYS save screenshots to yokeflow/screenshots/ directory"',
                'expected_impact': 'Better file organization'
            })

        # Pattern-based recommendations
        for pattern in self.patterns:
            if pattern['type'] == 'repeated_error' and pattern['frequency'] > 3:
                self.recommendations.append({
                    'priority': 'medium',
                    'category': 'error_prevention',
                    'title': f'Prevent repeated {pattern["pattern"]} errors',
                    'description': f'Same error occurred {pattern["frequency"]} times',
                    'prompt_change': f'Add specific guidance for {pattern["pattern"]} error recovery',
                    'expected_impact': 'Reduce repeated errors and improve efficiency'
                })


async def analyze_test_compliance(session_id: UUID, jsonl_path: Path) -> Dict[str, Any]:
    """
    Main entry point for test compliance analysis.

    Args:
        session_id: UUID of the session
        jsonl_path: Path to session JSONL log

    Returns:
        Analysis results with compliance score, issues, and recommendations
    """
    analyzer = TestComplianceAnalyzer(jsonl_path)
    results = analyzer.analyze()

    # Log summary
    logger.info(f"Test compliance analysis for session {session_id}:")
    logger.info(f"  Compliance score: {results['compliance_score']}/100")
    logger.info(f"  Issues found: {len(results['issues'])}")
    logger.info(f"  Recommendations: {len(results['recommendations'])}")

    return results


def format_compliance_report(results: Dict[str, Any]) -> str:
    """
    Format compliance analysis results as a readable report.

    Args:
        results: Analysis results from analyze_test_compliance

    Returns:
        Formatted markdown report
    """
    report = f"""# Test Compliance Analysis Report

## Overall Compliance Score: {results['compliance_score']}/100

## Summary
- **Issues Found**: {len(results['issues'])}
- **Error Patterns**: {len(results['patterns'])}
- **Recommendations**: {len(results['recommendations'])}

## Testing Workflow Metrics
"""

    test_metrics = results['metrics']['test_workflow']
    report += f"""- Tasks Completed: {test_metrics['tasks_completed']}
- Tasks Properly Tested: {test_metrics['tasks_tested_properly']}
- Tasks Without Tests: {len(test_metrics['tasks_without_tests'])}
- Epic Tests Run: {test_metrics['epic_tests_run']}
- Verification Notes Provided: {test_metrics['verification_notes_provided']}
"""

    # Issues section
    if results['issues']:
        report += "\n## Critical Issues\n"

        # Group by severity
        high_severity = [i for i in results['issues'] if i.get('severity') == 'high']
        medium_severity = [i for i in results['issues'] if i.get('severity') == 'medium']
        low_severity = [i for i in results['issues'] if i.get('severity') == 'low']

        if high_severity:
            report += "\n### High Severity\n"
            for issue in high_severity[:5]:  # Show top 5
                report += f"- **{issue['type']}**: {issue.get('message', '')}\n"

        if medium_severity:
            report += "\n### Medium Severity\n"
            for issue in medium_severity[:5]:
                report += f"- **{issue['type']}**: {issue.get('message', '')}\n"

    # Recommendations section
    if results['recommendations']:
        report += "\n## Recommendations for Prompt Improvements\n"

        for rec in sorted(results['recommendations'], key=lambda x: ['high', 'medium', 'low'].index(x['priority'])):
            report += f"""
### {rec['priority'].upper()}: {rec['title']}
- **Issue**: {rec['description']}
- **Solution**: {rec['prompt_change']}
- **Expected Impact**: {rec['expected_impact']}
"""

    return report