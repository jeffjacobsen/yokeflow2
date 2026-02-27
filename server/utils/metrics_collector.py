"""
Real-time Metrics Collection for Session Quality
================================================

This module provides enhanced metric collection that tracks all quality-relevant
metrics in real-time during session execution, eliminating the need for
post-session log parsing.

Key Features:
1. Single source of truth for all metrics
2. Unified browser detection (agent-browser)
4. Efficient storage in session_end event
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime
from collections import defaultdict, Counter


class MetricsCollector:
    """
    Collects and calculates all quality metrics in real-time.

    This is used by SessionLogger to track metrics as events happen,
    rather than parsing logs after the session.
    """

    def __init__(self):
        """Initialize the metrics collector."""

        # Basic counts
        self.tool_use_count = 0
        self.tool_errors = 0
        self.message_count = 0

        # Tool tracking
        self.tool_timings = {}  # tool_id -> start_time
        self.long_running_tools = 0  # Count of tools taking > 30s

        # Command analysis (replaces tool_counts)
        self.command_analysis = {
            'bash_commands': defaultdict(int),  # 'npm install': 5, 'git commit': 12
            'command_patterns': {
                'build_commands': 0,  # npm install, npm run build
                'test_commands': 0,   # npm test, pytest
                'git_commands': 0,    # git add, git commit
                'file_operations': 0  # ls, cat, mkdir
            }
        }

        # Enhanced error tracking (replaces error_types)
        self.error_analysis = {
            'command_errors': [],  # Detailed error info with context
            'error_categories': defaultdict(int),  # 'build_failures', 'test_failures', etc.
            'repeated_errors': defaultdict(int),  # error_message -> count
            'recovery_tracking': {}  # error_instance -> attempt_count
        }

        # Browser operations (unified detection)
        self.browser_verifications = 0  # Total browser ops
        self.browser_operations = {
            'screenshots': 0,
            'navigations': 0,
            'interactions': 0,  # clicks, fills, etc.
            'evaluations': 0,
            }

        # Testing metrics
        self.test_metrics = {
            'tasks_started': 0,
            'tasks_completed': 0,
            'tests_retrieved': 0,
            'tests_passed': 0,
            'tests_with_notes': 0,
            'epic_tests_run': 0,
            'epic_tests_passed': 0
        }

        # Task tracking
        self.current_task = None
        self.task_states = {}  # task_id -> {started, tests_retrieved, completed}

        # Verification tracking per task (simplified - no classification)
        self.task_verification = {}  # task_id -> verification info

        # Error pattern tracking with recovery attempts
        self.error_patterns = defaultdict(lambda: {
            'count': 0,
            'repeated': False,
            'recovery_attempts': [],
            'examples': [],
            'task_contexts': []
        })

        # Prompt adherence violations
        self.adherence_violations = []

        # Session progression metrics (hourly buckets)
        self.session_progression = {
            'hourly_metrics': [],  # List of hourly snapshots
            'last_hour_check': time.time()
        }

        # Session timing
        self.start_time = time.time()

    def track_tool_use(self, tool_name: str, tool_id: str, params: Optional[Dict] = None):
        """
        Track a tool use event.

        Args:
            tool_name: Name of the tool being used
            tool_id: Unique ID for this tool use
            params: Tool parameters (for browser detection)
        """
        self.tool_use_count += 1

        # Start timing for this tool
        self.tool_timings[tool_id] = time.time()

        # Track important tools
        if tool_name in ['Edit', 'Read', 'Write']:
            self.command_analysis['command_patterns']['file_operations'] += 1

        # Detect browser operations (unified for both modes)
        self._detect_browser_operation(tool_name, params or {})

        # Track testing tools
        self._track_testing_tool(tool_name, params or {})

        # Detect prompt adherence violations
        self._detect_adherence_violation(tool_name, params or {})

    def track_tool_result(self, tool_id: str, is_error: bool, error_type: Optional[str] = None, error_content: Optional[str] = None):
        """
        Track a tool result event with enhanced error analysis.

        Args:
            tool_id: ID of the tool use
            is_error: Whether the tool resulted in an error
            error_type: Type of error if applicable
            error_content: Full error message/content
        """
        # Calculate tool duration
        if tool_id in self.tool_timings:
            duration = time.time() - self.tool_timings[tool_id]
            if duration > 30:
                self.long_running_tools += 1
            del self.tool_timings[tool_id]

        # Enhanced error tracking
        if is_error:
            self.tool_errors += 1
            self._analyze_error(tool_id, error_type, error_content)

    def _detect_adherence_violation(self, tool_name: str, params: Dict):
        """
        Detect prompt adherence violations.
        """
        # Check for workspace prefix in file paths
        if tool_name in ['Read', 'Write', 'Edit']:
            file_path = params.get('file_path', '')
            if file_path.startswith('/workspace/'):
                self.adherence_violations.append({
                    'type': 'workspace_prefix',
                    'timestamp': time.time(),
                    'context': f"Used /workspace/ prefix in {tool_name}: {file_path}",
                    'impact': 'File path may be incorrect'
                })

        # Check for cd usage (should use subshells)
        if tool_name == 'Bash':
            command = params.get('command', '')
            if command.strip().startswith('cd ') and not '&&' in command:
                self.adherence_violations.append({
                    'type': 'directory_change',
                    'timestamp': time.time(),
                    'context': f"Changed directory with cd: {command[:100]}",
                    'impact': 'Working directory change persists across commands'
                })

    def _analyze_bash_command(self, command: str):
        """Analyze bash command for patterns and adherence."""
        if not command:
            return
            
        cmd_lower = command.lower().strip()
        
        # Store for error tracking
        self._last_bash_command = command
        
        # Track command usage
        # Extract the main command (first word)
        main_cmd = cmd_lower.split()[0] if cmd_lower.split() else ''
        self.command_analysis['bash_commands'][main_cmd] += 1
        
        # Categorize command patterns
        if any(build_cmd in cmd_lower for build_cmd in ['npm install', 'npm run build', 'yarn install', 'pip install']):
            self.command_analysis['command_patterns']['build_commands'] += 1
        elif any(test_cmd in cmd_lower for test_cmd in ['npm test', 'pytest', 'jest', 'npm run test']):
            self.command_analysis['command_patterns']['test_commands'] += 1
        elif any(git_cmd in cmd_lower for git_cmd in ['git add', 'git commit', 'git push', 'git status']):
            self.command_analysis['command_patterns']['git_commands'] += 1
        elif any(file_cmd in cmd_lower for file_cmd in ['ls', 'cat', 'mkdir', 'cp', 'mv', 'rm']):
            self.command_analysis['command_patterns']['file_operations'] += 1

    def _analyze_error(self, tool_id: str, error_type: Optional[str], error_content: Optional[str]):
        """Analyze error for patterns and categorization."""
        if not error_content:
            return
            
        error_msg = str(error_content).lower()
        
        # Categorize error
        category = 'general'
        if 'no such file' in error_msg or 'not found' in error_msg:
            category = 'file_not_found'
        elif 'permission denied' in error_msg or 'access denied' in error_msg:
            category = 'permission_denied'
        elif 'exit code' in error_msg or 'command failed' in error_msg:
            category = 'command_failed'
        elif 'network' in error_msg or 'connection' in error_msg:
            category = 'network_error'
        elif 'test' in error_msg and 'fail' in error_msg:
            category = 'test_failure'
        elif 'build' in error_msg and 'fail' in error_msg:
            category = 'build_failure'
            
        self.error_analysis['error_categories'][category] += 1
        
        # Track repeated errors
        error_key = error_msg[:100]  # First 100 chars as key
        self.error_analysis['repeated_errors'][error_key] += 1
        
        # Store detailed error info
        error_info = {
            'tool_id': tool_id,
            'category': category,
            'message': error_content[:500],  # Truncate long messages
            'task_id': self.current_task,
            'timestamp': time.time()
        }

        # Track error patterns with recovery attempts
        pattern_key = f"{category}_{error_key}"
        pattern = self.error_patterns[pattern_key]
        pattern['count'] += 1
        if pattern['count'] > 1:
            pattern['repeated'] = True
        if len(pattern['examples']) < 3:  # Keep first 3 examples
            pattern['examples'].append(error_content[:200])
        if self.current_task and self.current_task not in pattern['task_contexts']:
            pattern['task_contexts'].append(self.current_task)

        # Track recovery attempts (will be updated when same error occurs again)
        if pattern_key in self.error_analysis.get('recovery_tracking', {}):
            self.error_analysis['recovery_tracking'][pattern_key] += 1
            pattern['recovery_attempts'].append(self.error_analysis['recovery_tracking'][pattern_key])
        else:
            self.error_analysis['recovery_tracking'][pattern_key] = 1

        # Update error count for current task
        if self.current_task and self.current_task in self.task_verification:
            self.task_verification[self.current_task]['error_count'] += 1
        
        # Add command info if this was a bash command error
        if hasattr(self, '_last_bash_command'):
            error_info['command'] = self._last_bash_command
            
        self.error_analysis['command_errors'].append(error_info)

    def _detect_browser_operation(self, tool_name: str, params: Dict):
        """
        Detect agent-browser operations via Bash commands.
        """
        if tool_name == 'Bash':
            command = params.get('command', '').lower()

            if 'agent-browser' in command:
                self.browser_verifications += 1

                # Track verification method for current task (Bug #2 fix)
                if self.current_task:
                    self.track_verification_method(self.current_task, 'browser')

                # Categorize operation type
                if 'screenshot' in command or 'snapshot' in command:
                    self.browser_operations['screenshots'] += 1
                elif 'eval' in command:
                    self.browser_operations['evaluations'] += 1
                elif any(nav in command for nav in ['open', 'navigate', 'goto']):
                    self.browser_operations['navigations'] += 1
                elif any(action in command for action in ['click', 'fill', 'type', 'select']):
                    self.browser_operations['interactions'] += 1

            # Detect curl commands for API verification (Bug #2 fix)
            elif 'curl' in command and self.current_task:
                self.track_verification_method(self.current_task, 'curl')

    # Removed _classify_task_type - tasks don't have types, tests do

    def _track_testing_tool(self, tool_name: str, params: Dict):
        """Track testing-related tool usage."""
        # Task management
        if tool_name == 'mcp__task-manager__start_task':
            self.test_metrics['tasks_started'] += 1
            task_id = params.get('task_id')
            if task_id:
                self.current_task = task_id
                self.task_states[task_id] = {
                    'started': True,
                    'tests_retrieved': False,
                    'completed': False,
                    'start_time': time.time()
                }
                # Initialize verification tracking (simplified)
                self.task_verification[task_id] = {
                    'verification_methods': set(),  # Track all methods used
                    'error_count': 0,
                    'start_time': time.time()
                }

        elif tool_name == 'mcp__task-manager__update_task_status':
            if params.get('done'):
                self.test_metrics['tasks_completed'] += 1
                task_id = params.get('task_id')
                if task_id in self.task_states:
                    self.task_states[task_id]['completed'] = True

        # Test retrieval
        elif tool_name == 'mcp__task-manager__get_task_tests':
            self.test_metrics['tests_retrieved'] += 1
            if self.current_task in self.task_states:
                self.task_states[self.current_task]['tests_retrieved'] = True

        elif tool_name == 'mcp__task-manager__get_epic_tests':
            self.test_metrics['epic_tests_run'] += 1

        # Test results (task tests)
        elif tool_name == 'mcp__task-manager__update_task_test_result':
            if params.get('passes'):
                self.test_metrics['tests_passed'] += 1
            if params.get('verification_notes'):
                self.test_metrics['tests_with_notes'] += 1

        elif tool_name == 'mcp__task-manager__update_epic_test_result':
            if params.get('result') == 'passed':
                self.test_metrics['epic_tests_passed'] += 1
            if params.get('verification_notes'):
                self.test_metrics['tests_with_notes'] += 1


    # Removed update_task_info - no longer classifying tasks
    # Test types (browser, api, unit, integration) come from database

    def track_verification_method(self, task_id: str, method: str):
        """
        Track the actual verification method used for a task.

        Args:
            task_id: The task being verified
            method: 'browser', 'curl', 'build', etc.
        """
        if task_id in self.task_verification:
            self.task_verification[task_id]['verification_methods'].add(method)

    def _update_hourly_metrics(self):
        """
        Update hourly progression metrics for trend analysis.
        """
        current_time = time.time()
        hours_elapsed = (current_time - self.start_time) / 3600

        # Check if an hour has passed since last check
        if current_time - self.session_progression['last_hour_check'] >= 3600:
            # Calculate metrics for the past hour
            hourly_snapshot = {
                'hour': len(self.session_progression['hourly_metrics']) + 1,
                'tasks_completed': self.test_metrics['tasks_completed'],
                'errors_count': self.tool_errors,
                'verification_rate': sum(1 for t in self.task_verification.values() if t['verification_methods']) / max(1, len(self.task_verification)),
                'browser_operations': self.browser_verifications,
                'timestamp': current_time
            }

            self.session_progression['hourly_metrics'].append(hourly_snapshot)
            self.session_progression['last_hour_check'] = current_time

    def get_summary(self) -> Dict[str, Any]:
        """
        Get complete metrics summary for storage.

        Returns:
            Dictionary containing all collected metrics and calculated scores
        """
        duration = time.time() - self.start_time
        error_rate = self.tool_errors / max(1, self.tool_use_count)

        # Update hourly metrics before returning
        self._update_hourly_metrics()

        # Convert error patterns to serializable format
        error_patterns_summary = {}
        for pattern_key, pattern_data in self.error_patterns.items():
            if pattern_data['count'] > 0:
                error_patterns_summary[pattern_key] = {
                    'count': pattern_data['count'],
                    'repeated': pattern_data['repeated'],
                    'recovery_attempts': pattern_data['recovery_attempts'],
                    'avg_recovery_attempts': sum(pattern_data['recovery_attempts']) / len(pattern_data['recovery_attempts']) if pattern_data['recovery_attempts'] else 0,
                    'examples': pattern_data['examples'][:2],  # First 2 examples
                    'task_contexts': pattern_data['task_contexts'][:3]  # First 3 tasks
                }

        return {
            # Basic metrics
            'tool_use_count': self.tool_use_count,
            'tool_errors': self.tool_errors,
            'error_rate': error_rate,
            'long_running_tools': self.long_running_tools,
            'duration_seconds': duration,

            # Enhanced command analysis (replaces tool_counts)
            'command_analysis': {
                'bash_commands': dict(self.command_analysis['bash_commands']),
                'command_patterns': self.command_analysis['command_patterns']
            },

            # Enhanced error analysis with patterns and recovery
            'error_analysis': {
                'error_categories': dict(self.error_analysis['error_categories']),
                'repeated_errors': dict(self.error_analysis['repeated_errors']),
                'command_errors': self.error_analysis['command_errors'][-10:],  # Last 10 errors
                'error_patterns': error_patterns_summary  # NEW: Detailed error patterns
            },

            # Browser metrics (unified)
            'browser_verifications': self.browser_verifications,
            'browser_operations': self.browser_operations,

            # Testing metrics
            'test_metrics': self.test_metrics,
            'test_compliance_rate': self.test_metrics['tests_retrieved'] / max(1, self.test_metrics['tasks_completed']),

            # Verification tracking (simplified - test types come from database)
            'verification_analysis': {
                'tasks_verified': sum(1 for t in self.task_verification.values() if t['verification_methods']),
                'tasks_unverified': sum(1 for t in self.task_verification.values() if not t['verification_methods']),
                'verification_rate': sum(1 for t in self.task_verification.values() if t['verification_methods']) / max(1, len(self.task_verification)),
                'methods_used': list(set().union(*[t['verification_methods'] for t in self.task_verification.values()])) if self.task_verification else []
            },

            # NEW: Prompt adherence violations
            'adherence_violations': self.adherence_violations,
            'adherence_summary': {
                'total_violations': len(self.adherence_violations),
                'violation_types': dict(Counter(v['type'] for v in self.adherence_violations))
            },

            # NEW: Session progression for trend analysis
            'session_progression': {
                'hourly_metrics': self.session_progression['hourly_metrics'],
                'current_hour': len(self.session_progression['hourly_metrics']) + 1,
                'tasks_per_hour': self.test_metrics['tasks_completed'] / max(1, duration / 3600),
                'errors_per_hour': self.tool_errors / max(1, duration / 3600)
            },

            # Metadata
            'metrics_version': '3.0',  # Updated version for new metrics
            'calculated_at': datetime.now().isoformat()
        }


def categorize_error(error_message: str) -> str:
    """
    Categorize an error message into a type.

    Args:
        error_message: The error message to categorize

    Returns:
        Error category string
    """
    error_lower = error_message.lower()

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