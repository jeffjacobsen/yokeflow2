"""
Claude SDK Client Configuration
================================

Creates Claude Agent SDK clients with MCP task-manager integration
and security hooks for autonomous agent operation.
"""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

from server.utils.security import bash_security_hook
from server.utils.auth import get_oauth_token

logger = logging.getLogger(__name__)


def copy_agent_skills(project_dir: Path) -> None:
    """
    Copy agent skill files from yokeflow2/claude/ to the project's .claude/ directory.

    Only copies specific subdirectories (commands/, skills/) — not settings files
    or other yokeflow2-specific state. This keeps the agent's skill access separate
    from yokeflow2's own .claude/ configuration.
    """
    agent_root = Path(__file__).parent.parent.parent  # yokeflow2/
    source_claude_dir = agent_root / "claude"
    dest_claude_dir = project_dir / ".claude"

    # Only copy these subdirectories (add "skills" when that directory exists)
    dirs_to_copy = ["scripts", "skills"]

    for subdir in dirs_to_copy:
        src = source_claude_dir / subdir
        if not src.exists():
            continue
        dst = dest_claude_dir / subdir
        shutil.copytree(src, dst, dirs_exist_ok=True)
        logger.info(f"[Skills] Copied {subdir}/ to {dst}")


def get_mcp_env(project_dir: Path, project_id: str = None) -> dict:
    """
    Get environment variables for MCP task-manager server.

    Args:
        project_dir: Project directory path
        project_id: UUID of the project in the database (optional, will be generated if not provided)
    """
    import os
    import uuid

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    # Use provided project_id or generate from project name
    if not project_id:
        project_name = project_dir.name
        # Generate deterministic UUID based on project name (fallback)
        project_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, project_name))
        print(f"[DEBUG] MCP task-manager using generated UUID for project: {project_name} (ID: {project_id})")
    else:
        project_name = project_dir.name
        print(f"[DEBUG] MCP task-manager using PostgreSQL for project: {project_name} (ID: {project_id})")

    return {
        "DATABASE_URL": database_url,
        "PROJECT_ID": project_id
    }


def create_client(project_dir: Path, model: str, project_id: str = None) -> ClaudeSDKClient:
    """
    Create a Claude Agent SDK client with multi-layered security.

    Args:
        project_dir: Directory for the project
        model: Claude model to use
        project_id: UUID of the project in the database (optional)

    Returns:
        Configured ClaudeSDKClient

    Security layers (defense in depth):
    1. BypassPermissions - Agent has broad tool access for autonomous operation
    2. Security hooks - Bash commands validated against a blocklist
       (see security.py for BLOCKED_COMMANDS)

    The agent runs locally and needs broad command access to work autonomously.
    """

    # Ensure authentication is properly configured
    # The generated app may set ANTHROPIC_API_KEY in its environment, which can leak
    # into our agent process. We explicitly remove it and prefer CLAUDE_CODE_OAUTH_TOKEN.
    from dotenv import load_dotenv

    # CRITICAL FIX: Remove any leaked ANTHROPIC_API_KEY BEFORE loading agent's .env
    # If we don't do this first, the leaked key persists in os.environ and gets picked up
    # by the Claude SDK even though we load our .env file after.
    # This happens because environment variables persist across module imports.
    os.environ.pop("ANTHROPIC_API_KEY", None)

    # CRITICAL: Load .env from agent's root directory, NOT from project directory
    # The project directory may have its own .env file with ANTHROPIC_API_KEY for the generated app
    agent_root = Path(__file__).parent.parent.parent.parent  # /path/to/yokeflow2/ (project root)
    agent_env_file = agent_root / ".env"
    load_dotenv(dotenv_path=agent_env_file)  # Load from agent's .env file only

    # Now check for authentication (after cleaning environment and loading our .env)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    # Get OAuth token with automatic refresh from ~/.claude/.credentials.json
    # This ensures we always use the fresh token instead of a stale .env copy
    oauth_token = get_oauth_token()

    if api_key:
        raise RuntimeError(
            "  - ANTHROPIC_API_KEY is set"
        )

    # Explicitly set OAuth token for the Claude SDK subprocess
    if oauth_token:
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

    # Configure MCP task manager server
    # Path is relative to yokeflow root (3 levels up from this file)
    # /Users/jeff/code/yokeflow2/server/client/claude.py -> /Users/jeff/code/yokeflow2
    mcp_server_path = Path(__file__).parent.parent.parent / "mcp-task-manager" / "dist" / "index.js"

    # Pre-flight check: verify build exists, is fresh, and parses correctly
    check = verify_mcp_server(auto_rebuild=True)
    if not check["ok"]:
        raise FileNotFoundError(
            f"MCP task manager server verification failed: {check['message']}. "
            f"Run 'cd mcp-task-manager && npm install && npm run build' to build it."
        )
    if check["rebuilt"]:
        logger.info(f"[MCP] Server was auto-rebuilt: {check['message']}")

    # Configure MCP servers
    mcp_env = get_mcp_env(project_dir, project_id)
    print(f"[DEBUG] MCP server path: {mcp_server_path.absolute()}")
    print(f"[DEBUG] MCP environment: DATABASE_URL={mcp_env.get('DATABASE_URL', 'NOT SET')}, PROJECT_ID={mcp_env.get('PROJECT_ID', 'NOT SET')}")

    mcp_servers = {
        "task-manager": {
            "command": "node",
            "args": [str(mcp_server_path.absolute())],  # Ensure absolute path
            "env": mcp_env
        }
    }

    # Build system prompt
    # Session-specific guidance is loaded from prompts.py
    # This base prompt is minimal and generic
    system_prompt = "You are an expert full-stack developer building a production-quality web application."

    # Prepare environment for SDK subprocess
    # CRITICAL: Explicitly pass cleaned environment to prevent .env leakage
    # The SDK subprocess will have cwd=project_dir, and if it calls load_dotenv(),
    # it would load the project's .env file. By explicitly setting env vars here,
    # we ensure our cleaned environment takes precedence.
    sdk_env = {}

    # Only pass OAuth token if we have it (preferred authentication method)
    if oauth_token:
        sdk_env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

    # CRITICAL: Explicitly unset ANTHROPIC_API_KEY in subprocess environment
    # Even though we removed it from parent process, the subprocess might load it
    # from the project's .env file when it runs with cwd=project_dir.
    # The env dict in ClaudeAgentOptions MERGES with parent environment, so we
    # need to explicitly override ANTHROPIC_API_KEY to prevent it from being used.
    # Setting to empty string tells the SDK not to use an API key.
    sdk_env["ANTHROPIC_API_KEY"] = ""

    # Capture stderr from the Claude Code subprocess for MCP server diagnostics
    def _stderr_handler(line: str) -> None:
        # Log MCP-related stderr at warning level for visibility
        if "[MCP]" in line or "task-manager" in line.lower():
            logger.warning(f"[SDK stderr] {line}")
        else:
            logger.debug(f"[SDK stderr] {line}")

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt=system_prompt,
            permission_mode="bypassPermissions",
            mcp_servers=mcp_servers,
            hooks={
                "PreToolUse": [
                    # Security hook validates Bash commands against blocklist
                    HookMatcher(matcher="Bash", hooks=[bash_security_hook]),
                ],
            },
            setting_sources=["project"],
            max_turns=1000,
            max_buffer_size=10485760,  # 10MB (10x default of 1MB) - prevents large snapshot crashes
            cwd=str(project_dir.resolve()),
            env=sdk_env,  # Explicitly set environment to prevent .env leakage
            stderr=_stderr_handler,  # Capture subprocess stderr for MCP diagnostics
        )
    )


def get_mcp_server_path() -> Path:
    """Get the path to the MCP task-manager server's compiled output."""
    return Path(__file__).parent.parent.parent / "mcp-task-manager" / "dist" / "index.js"


def get_mcp_source_dir() -> Path:
    """Get the path to the MCP task-manager source directory."""
    return Path(__file__).parent.parent.parent / "mcp-task-manager" / "src"


def verify_mcp_server(auto_rebuild: bool = True) -> dict:
    """
    Pre-flight check for the MCP task-manager server.

    Validates:
    1. The compiled dist/index.js exists
    2. The build is not stale (source files are not newer than dist)
    3. The server can be parsed by Node.js without crashing

    Args:
        auto_rebuild: If True, automatically rebuild when build is stale or missing

    Returns:
        dict with keys: ok (bool), message (str), rebuilt (bool)
    """
    mcp_root = Path(__file__).parent.parent.parent / "mcp-task-manager"
    dist_path = mcp_root / "dist" / "index.js"
    src_dir = mcp_root / "src"

    # Check 1: Does dist/index.js exist?
    if not dist_path.exists():
        if auto_rebuild:
            logger.info("[MCP Preflight] dist/index.js missing, rebuilding...")
            rebuilt = _rebuild_mcp_server(mcp_root)
            if rebuilt:
                return {"ok": True, "message": "MCP server rebuilt successfully (was missing)", "rebuilt": True}
            return {"ok": False, "message": "MCP server build failed. Run 'cd mcp-task-manager && npm run build' manually.", "rebuilt": False}
        return {"ok": False, "message": f"MCP server not found at {dist_path}. Run 'cd mcp-task-manager && npm run build'.", "rebuilt": False}

    # Check 2: Is the build stale? (any .ts source file newer than dist/index.js)
    dist_mtime = dist_path.stat().st_mtime
    stale = False
    stale_files = []
    for ts_file in src_dir.glob("*.ts"):
        if ts_file.stat().st_mtime > dist_mtime:
            stale = True
            stale_files.append(ts_file.name)

    if stale:
        if auto_rebuild:
            logger.info(f"[MCP Preflight] Build stale (modified: {', '.join(stale_files)}), rebuilding...")
            rebuilt = _rebuild_mcp_server(mcp_root)
            if rebuilt:
                return {"ok": True, "message": f"MCP server rebuilt (stale files: {', '.join(stale_files)})", "rebuilt": True}
            return {"ok": False, "message": "MCP server rebuild failed after detecting stale build.", "rebuilt": False}
        return {"ok": False, "message": f"MCP server build is stale. Files changed: {', '.join(stale_files)}", "rebuilt": False}

    # Check 3: Can Node.js parse the server without crashing?
    # Use --check flag for syntax validation (doesn't execute the code)
    try:
        result = subprocess.run(
            ["node", "--check", str(dist_path)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            if auto_rebuild:
                logger.warning(f"[MCP Preflight] Syntax check failed: {result.stderr.strip()}, rebuilding...")
                rebuilt = _rebuild_mcp_server(mcp_root)
                if rebuilt:
                    return {"ok": True, "message": "MCP server rebuilt (syntax check failed on old build)", "rebuilt": True}
                return {"ok": False, "message": f"MCP server has syntax errors and rebuild failed: {result.stderr.strip()}", "rebuilt": False}
            return {"ok": False, "message": f"MCP server syntax check failed: {result.stderr.strip()}", "rebuilt": False}
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"ok": False, "message": f"Node.js check failed: {e}", "rebuilt": False}

    return {"ok": True, "message": "MCP server verified", "rebuilt": False}


def _rebuild_mcp_server(mcp_root: Path) -> bool:
    """
    Rebuild the MCP task-manager server by running `npm run build`.

    Returns True on success, False on failure.
    """
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(mcp_root),
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            logger.info("[MCP Preflight] Rebuild successful")
            return True
        else:
            logger.error(f"[MCP Preflight] Rebuild failed: {result.stderr.strip()}")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error(f"[MCP Preflight] Rebuild error: {e}")
        return False