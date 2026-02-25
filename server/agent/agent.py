"""
Agent Session Logic
===================

Core agent interaction functions for running YokeFlow coding sessions.
"""

import signal
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Awaitable
from datetime import datetime

from claude_agent_sdk import ClaudeSDKClient

from server.database.connection import DatabaseManager
from server.utils.observability import SessionLogger, QuietOutputFilter
from server.agent.intervention import InterventionManager
from server.utils.logging import (
    get_logger,
    set_session_id,
    set_project_id,
    clear_context,
    PerformanceLogger
)
from server.utils.errors import (
    SessionError,
    ToolExecutionError,
    ClaudeAPIError
)

# Module-level structured logger (use 'module_logger' to avoid conflict with SessionLogger parameter)
module_logger = get_logger(__name__)


# Configuration
AUTO_CONTINUE_DELAY_SECONDS = 3


class SessionManager:
    """
    Manages graceful shutdown for agent sessions.

    Handles SIGINT (Ctrl+C) and SIGTERM signals to ensure sessions
    are properly finalized before raising KeyboardInterrupt for the API server to handle.
    """

    def __init__(self):
        """Initialize session manager."""
        self.interrupted = False
        self.current_logger: Optional[SessionLogger] = None
        self._original_sigint = None
        self._original_sigterm = None

    def setup_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        self._original_sigint = signal.signal(signal.SIGINT, self._handle_interrupt)
        self._original_sigterm = signal.signal(signal.SIGTERM, self._handle_interrupt)

    def restore_handlers(self):
        """Restore original signal handlers."""
        if self._original_sigint:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm:
            signal.signal(signal.SIGTERM, self._original_sigterm)

    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signal and raise KeyboardInterrupt for the orchestrator to catch."""
        if self.interrupted:
            # Second interrupt - force raise exception
            print("\n\nForce exit (second interrupt)")
            raise KeyboardInterrupt("Force interrupt")

        self.interrupted = True
        signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"

        print(f"\n\n{'='*70}")
        print(f"  Received {signal_name} - Shutting down gracefully...")
        print(f"{'='*70}")

        # Finalize current session if one is active
        if self.current_logger:
            try:
                print("\nFinalizing session logs...")
                self.current_logger.finalize("interrupted", "Session interrupted by user")
                print("✓ Session logs saved")
            except Exception as e:
                print(f"Warning: Could not finalize session logs: {e}")

        print("\nSession interrupted. To resume, run the same command again.")
        print(f"{'='*70}\n")

        # Raise KeyboardInterrupt so orchestrator can catch it
        raise KeyboardInterrupt("Session interrupted")

    def set_current_logger(self, logger: Optional[SessionLogger]):
        """Set the current active logger for graceful shutdown."""
        self.current_logger = logger


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
    project_dir: Path,
    logger: SessionLogger,
    verbose: bool = False,
    session_manager: Optional[SessionManager] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    intervention_config: Optional[Dict[str, Any]] = None,
) -> tuple[str, str]:
    """
    Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send
        project_dir: Project directory path
        logger: Session logger for recording events
        verbose: If True, show detailed terminal output (default: quiet mode)
        session_manager: Optional session manager for interrupt checking
        progress_callback: Optional async callback for real-time progress updates.
                          Called with event dict containing type, tool_name, timestamp, etc.

    Returns:
        (status, response_text) where status is:
        - "continue" if agent should continue working
        - "error" if an error occurred
    """
    # Set context for structured logging
    if hasattr(logger, "session_id"):
        set_session_id(str(logger.session_id))
    if hasattr(logger, "project_id"):
        set_project_id(str(logger.project_id))

    # module_logger.info("Starting agent session", extra={
    #    "project_dir": str(project_dir),
    #    "verbose": verbose,
    #    "intervention_enabled": intervention_config.get("enabled", False) if intervention_config else False
    # })

    output_filter = QuietOutputFilter(verbose=verbose)

    # Initialize intervention manager if config provided
    intervention_manager = None
    if intervention_config and intervention_config.get("enabled", False):
        # Determine environment from intervention config or default to local
        environment = intervention_config.get("environment", "local")
        intervention_manager = InterventionManager(intervention_config, environment=environment)
        # Set session info for notifications
        session_id = logger.session_id if hasattr(logger, "session_id") else "unknown"
        project_name = project_dir.name
        intervention_manager.set_session_info(session_id, project_name)

    if verbose:
        print("Sending prompt to Claude Agent SDK...\n")

    # Log the prompt (JSONL only for agent review, not in TXT or terminal)
    logger.log_prompt(message)

    # Initialize variables that might be needed in exception handler
    response_text = ""
    message_count = 0
    usage_data = None  # Will be populated by ResultMessage

    try:
        # Send the query
        await client.query(message)

        async for msg in client.receive_response():
            # Check if session was interrupted
            if session_manager and session_manager.interrupted:
                print("\n\nSession interrupted by user request")
                raise KeyboardInterrupt("Session stopped by user")

            msg_type = type(msg).__name__

            # Handle ResultMessage (final message with usage data)
            if msg_type == "ResultMessage":
                # Extract usage and cost information
                if hasattr(msg, "usage") and msg.usage:
                    usage_data = {
                        "input_tokens": msg.usage.get("input_tokens", 0),
                        "output_tokens": msg.usage.get("output_tokens", 0),
                        "cache_creation_input_tokens": msg.usage.get("cache_creation_input_tokens", 0),
                        "cache_read_input_tokens": msg.usage.get("cache_read_input_tokens", 0),
                    }

                    # Extract cost if available
                    if hasattr(msg, "total_cost_usd") and msg.total_cost_usd is not None:
                        usage_data["cost_usd"] = msg.total_cost_usd

                    # Log to JSONL
                    logger.log_result_message(usage_data)

                    if verbose:
                        print(f"\n[Usage] Input: {usage_data['input_tokens']:,} tokens, Output: {usage_data['output_tokens']:,} tokens", flush=True)
                        if "cost_usd" in usage_data:
                            print(f"[Cost] ${usage_data['cost_usd']:.4f}", flush=True)

                continue

            # Handle AssistantMessage (text and tool use)
            if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "TextBlock" and hasattr(block, "text"):
                        response_text += block.text

                        # Check for critical errors that should stop the session immediately
                        if "Credit balance is too low" in block.text:
                            error_msg = "Credit balance is too low - API key is being used instead of OAuth token"
                            logger.log_error(error_msg)
                            print(f"\n❌ FATAL ERROR: {error_msg}", flush=True)
                            print("   This usually means ANTHROPIC_API_KEY leaked from the generated project.", flush=True)
                            print("   Check projects/{project}/.env and remove ANTHROPIC_API_KEY if present.", flush=True)
                            raise RuntimeError(error_msg)

                        # Log assistant text
                        logger.log_assistant_text(block.text)

                        # Always show assistant text (even in quiet mode)
                        if output_filter.should_show_assistant_text():
                            # Add newline before message if this is not the first message
                            if message_count > 0:
                                print()
                            print(block.text, end="", flush=True)
                            message_count += 1

                    elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                        tool_name = block.name
                        tool_id = getattr(block, "id", "unknown")
                        tool_input = getattr(block, "input", {})

                        # Log tool use
                        logger.log_tool_use(tool_name, tool_id, tool_input)

                        # Track task starts for quality monitoring
                        if intervention_manager and tool_name == "mcp__task-manager__start_task":
                            task_id = str(tool_input.get("task_id", ""))
                            # We'd need to get task description from database or context
                            # For now, just track the task ID
                            intervention_manager.set_current_task(task_id, f"Task {task_id}")

                        # Track when agent gets next task for quality monitoring
                        if intervention_manager and tool_name == "mcp__task-manager__get_next_task":
                            # The response will contain task info, but we handle this after execution
                            pass

                        # Check for task verification if this is update_task_status
                        if tool_name == "mcp__task-manager__update_task_status":
                            # Check if task is being marked as done
                            if tool_input.get("done", False):
                                task_id = str(tool_input.get("task_id", ""))

                                # First check quality standards with intervention manager
                                if intervention_manager:
                                    quality_blocked, quality_reason = await intervention_manager.check_task_completion(
                                        task_id, marking_complete=True
                                    )
                                    if quality_blocked:
                                        # Quality check failed - block completion
                                        error_msg = f"❌ Quality Check Failed: {quality_reason}"
                                        print(f"\n{error_msg}\n")
                                        logger.log_error(error_msg)

                                        # Skip normal tool execution
                                        continue

                                # Verification system removed - tests are now run via MCP tools

                        # Check for retry loops with intervention manager
                        if intervention_manager:
                            is_blocked, reason = await intervention_manager.check_tool_use(
                                tool_name, tool_input
                            )
                            if is_blocked:
                                # Document blocker and halt session
                                error_msg = f"🚨 INTERVENTION: {reason}"
                                print(f"\n{error_msg}\n")
                                logger.log_error(error_msg)

                                # Document in yokeflow/agent-progress.md
                                task_info = {"id": "unknown", "name": "Current task"}
                                intervention_manager.document_blocker(
                                    project_dir, task_info, reason
                                )

                                # Pause the session and save state
                                from server.agent.session_manager import PausedSessionManager
                                from server.utils.notifications import MultiChannelNotificationService

                                paused_manager = PausedSessionManager()

                                # Get project and session IDs from logger or config
                                session_id = getattr(logger, 'session_id', 'unknown')
                                project_id = getattr(logger, 'project_id', 'unknown')

                                # Determine pause type based on reason
                                pause_type = "retry_limit"
                                if "critical error" in reason.lower():
                                    pause_type = "critical_error"
                                elif "timeout" in reason.lower():
                                    pause_type = "timeout"

                                # Save paused session state
                                paused_session_id = await paused_manager.pause_session(
                                    session_id=session_id,
                                    project_id=project_id,
                                    reason=reason,
                                    pause_type=pause_type,
                                    intervention_manager=intervention_manager,
                                    current_task=task_info,
                                    message_count=message_count
                                )

                                # Send notifications if configured
                                if intervention_config.get("notifications", {}).get("enabled"):
                                    notifier = MultiChannelNotificationService(intervention_config.get("notifications", {}))
                                    await notifier.send_notification(
                                        title="Session Paused - Intervention Required",
                                        message=f"Session for {project_dir.name} has been paused due to: {reason}",
                                        details={
                                            "project_name": project_dir.name,
                                            "session_id": session_id,
                                            "pause_type": pause_type,
                                            "current_task": task_info.get("name", "Unknown"),
                                            "intervention_id": paused_session_id
                                        }
                                    )

                                print(f"\n📋 Session paused (ID: {paused_session_id})")
                                print(f"   To resume: Use the Web UI or API to resolve and resume")
                                print(f"   API endpoint: POST /api/interventions/{paused_session_id}/resume\n")

                                # Return error status to halt session
                                return "error", f"Session paused for intervention: {reason}"

                        # Defensive check: Warn about risky background bash usage
                        if tool_name == "Bash" and tool_input.get("run_in_background"):
                            timeout_ms = tool_input.get("timeout", 120000)
                            timeout_sec = timeout_ms / 1000
                            command = tool_input.get("command", "")

                            # Check for long-running server commands
                            risky_patterns = ["npm run dev", "npm start", "node server", "uvicorn", "flask run", "python -m"]
                            is_risky = any(pattern in command for pattern in risky_patterns)

                            if is_risky and timeout_sec < 60:
                                warning_msg = (
                                    f"⚠️  WARNING: Background bash with short timeout ({timeout_sec}s) for server command.\n"
                                    f"   Command: {command}\n"
                                    f"   Risk: Process may timeout and abort silently (known Claude Code bug).\n"
                                    f"   Recommendation: Start servers via init.sh before session, not during.\n"
                                    f"   See: prompts/coding_prompt.md - Background Bash section"
                                )
                                # Log warning to session logs
                                logger.log_system_message("risky_background_bash_warning", warning_msg)
                                # Also print to console for visibility
                                print(f"\n{warning_msg}\n", flush=True)
                            elif tool_input.get("run_in_background"):
                                # Log all background bash for debugging
                                info_msg = (
                                    f"Background bash started: {command} (timeout: {timeout_sec}s). "
                                    f"Note: Process timeouts may fail silently (Claude Code limitation)."
                                )
                                logger.log_system_message("background_bash", info_msg)

                        # Send progress update via callback
                        if progress_callback:
                            try:
                                await progress_callback({
                                    "type": "tool_use",
                                    "tool_name": tool_name,
                                    "tool_id": tool_id,
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception as e:
                                # Don't fail session if callback fails
                                logger.log_error(f"Progress callback failed: {e}")

                        # Show tool use based on verbose mode
                        if output_filter.should_show_tool_use(tool_name):
                            print(f"\n[Tool: {tool_name}]", flush=True)
                            if verbose and hasattr(block, "input"):
                                input_str = str(block.input)
                                if len(input_str) > 200:
                                    print(f"   Input: {input_str[:200]}...", flush=True)
                                else:
                                    print(f"   Input: {input_str}", flush=True)

                    elif block_type == "ThinkingBlock" and hasattr(block, "thinking"):
                        # Log thinking
                        logger.log_thinking(block.thinking)

                        # Show thinking based on quiet mode
                        if output_filter.should_show_thinking():
                            print(f"\n[Thinking]\n{block.thinking[:500]}...\n", flush=True)

            # Handle UserMessage (tool results)
            elif msg_type == "UserMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "ToolResultBlock":
                        result_content = getattr(block, "content", "")
                        is_error = getattr(block, "is_error", False)
                        tool_id = getattr(block, "tool_use_id", "unknown")

                        # Log tool result
                        logger.log_tool_result(tool_id, result_content, is_error)

                        # Check for errors with intervention manager
                        if is_error and intervention_manager:
                            error_msg = str(result_content)
                            is_blocked, reason = await intervention_manager.check_tool_error(error_msg)
                            if is_blocked:
                                # Document blocker and halt session
                                error_msg = f"🚨 INTERVENTION: {reason}"
                                print(f"\n{error_msg}\n")
                                logger.log_error(error_msg)

                                # Document in yokeflow/agent-progress.md
                                task_info = {"id": "unknown", "name": "Current task"}
                                intervention_manager.document_blocker(
                                    project_dir, task_info, reason
                                )

                                # Return error status to halt session
                                return "error", f"Session blocked due to critical error: {reason}"

                        # Send progress update via callback
                        if progress_callback:
                            try:
                                await progress_callback({
                                    "type": "tool_result",
                                    "tool_id": tool_id,
                                    "is_error": is_error,
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception as e:
                                # Don't fail session if callback fails
                                logger.log_error(f"Progress callback failed: {e}")

                        # Show based on verbose mode
                        if output_filter.should_show_tool_result(is_error):
                            if is_error:
                                # Show errors (truncated)
                                error_str = str(result_content)[:500]
                                print(f"   [Error] {error_str}", flush=True)
                            elif verbose:
                                # Tool succeeded - show brief confirmation in verbose mode only
                                print("   [Done]", flush=True)

            # Handle SystemMessage
            elif msg_type == "SystemMessage":
                subtype = getattr(msg, "subtype", "unknown")
                message_text = str(msg)

                logger.log_system_message(subtype, message_text)

                # Check for MCP server failures (init message only)
                if subtype == "init" and hasattr(msg, "data"):
                    mcp_servers = msg.data.get("mcp_servers", [])
                    failed_servers = [
                        s["name"] for s in mcp_servers
                        if isinstance(s, dict) and s.get("status") == "failed"
                    ]
                    if failed_servers:
                        error_msg = f"MCP server(s) failed to start: {', '.join(failed_servers)}"
                        logger.log_error(error_msg)
                        print(f"\n❌ {error_msg}", flush=True)
                        print("   This is usually a transient issue (Node.js cold start or PostgreSQL slow to respond).", flush=True)
                        print("   The session will be retried with a fresh client.\n", flush=True)
                        raise SessionError(error_msg)

                # Check for API key usage warning (init message only)
                if subtype == "init" and hasattr(msg, "data"):
                    api_key_source = msg.data.get("apiKeySource", "none")
                    if api_key_source == "ANTHROPIC_API_KEY" and progress_callback:
                        # Send warning to UI via WebSocket
                        try:
                            await progress_callback({
                                "type": "api_key_warning",
                                "source": api_key_source,
                                "message": (
                                    "⚠️ Using ANTHROPIC_API_KEY (credit-based billing). "
                                    "This is more expensive than CLAUDE_CODE_OAUTH_TOKEN (membership plan). "
                                    "Check if ANTHROPIC_API_KEY leaked from project .env file."
                                ),
                                "timestamp": datetime.now().isoformat()
                            })
                        except Exception as e:
                            logger.log_error(f"Failed to send API key warning: {e}")

                        # Also print warning to console
                        print("\n" + "=" * 80)
                        print("⚠️  WARNING: Using ANTHROPIC_API_KEY (Credit-Based Billing)")
                        print("=" * 80)
                        print("You are using an API key instead of OAuth token (membership plan).")
                        print("This is significantly more expensive (~$3/million tokens vs included in plan).")
                        print("")
                        print("Common causes:")
                        print("  1. ANTHROPIC_API_KEY leaked from generated project's .env file")
                        print("  2. ANTHROPIC_API_KEY set in system environment")
                        print("")
                        print("To fix:")
                        print("  1. Check projects/{project}/.env and remove ANTHROPIC_API_KEY")
                        print("  2. Unset ANTHROPIC_API_KEY: unset ANTHROPIC_API_KEY")
                        print("  3. Ensure CLAUDE_CODE_OAUTH_TOKEN is set in agent's .env file")
                        print("=" * 80 + "\n")

                if verbose:
                    print(f"[System: {subtype}] {message_text}", flush=True)

        if verbose:
            print("\n" + "-" * 70 + "\n")

        # Check if the response indicates a BLOCKED epic test intervention
        # The agent's response should contain the BLOCKED message if it properly stopped
        session_status = "continue"
        if "BLOCKED:" in response_text or "BLOCKED on" in response_text:
            session_status = "blocked"
            module_logger.info("Epic test intervention detected - session blocked")

            # Also check database for epic_test_interventions if needed
            try:
                async with DatabaseManager() as db:
                    async with db.acquire() as conn:
                        # Check for recent epic test interventions
                        result = await conn.fetchval(
                            """SELECT COUNT(*) FROM epic_test_interventions
                               WHERE session_id = $1 AND blocked = true""",
                            session_id
                        )
                        if result > 0:
                            session_status = "blocked"
            except Exception as e:
                module_logger.warning(f"Could not check epic test interventions: {e}")

        # Finalize logging and get session summary
        session_summary = logger.finalize(session_status, response_text, usage_data=usage_data)

        # module_logger.info("Agent session completed successfully", extra={
        #    "status": session_status,
        #    "message_count": message_count,
        #    "usage": usage_data
        # })

        # Clear context before returning
        clear_context()

        return session_status, response_text, session_summary

    except RuntimeError as e:
        # Re-raise RuntimeError (critical errors like credit issues) without catching
        print(f"Error during agent session: {e}")

        # Log error with structured logging
        module_logger.error("Agent session failed", exc_info=True, extra={
            "error_type": type(e).__name__,
            "message_count": message_count
        })

        # Log error to session logger
        logger.log_error(e)
        logger.finalize("error", "", usage_data=usage_data)

        # Clear context before re-raising
        clear_context()

        # Re-raise to allow caller to handle
        raise

    except Exception as e:
        print(f"Error during agent session: {e}")

        # Log error with structured logging
        module_logger.error("Agent session failed", exc_info=True, extra={
            "error_type": type(e).__name__,
            "message_count": message_count
        })

        # Log error to session logger
        logger.log_error(e)
        session_summary = logger.finalize("error", "", usage_data=usage_data)

        # Clear context before returning
        clear_context()

        return "error", str(e), session_summary

