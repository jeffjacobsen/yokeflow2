#!/usr/bin/env python3
"""
Wrapper script to start the API server with proper configuration.
This ensures uvicorn can properly reload the module.
"""

import uvicorn
import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Ensure we're in the correct directory (go to project root)
os.chdir(project_root)

# Check if PostgreSQL is configured
from server.database.connection import is_postgresql_configured

if not is_postgresql_configured():
    print("\n" + "="*60)
    print("WARNING: PostgreSQL is not configured!")
    print("="*60)
    print("\nThe API will run with limited functionality.")
    print("To enable full functionality:")
    print("1. Start PostgreSQL: docker-compose up -d")
    print("2. Set DATABASE_URL in .env file")
    print("3. Initialize database: python scripts/init_database.py --docker")
    print("="*60 + "\n")

# Pre-flight check: Verify MCP task-manager server
from server.client.claude import verify_mcp_server

print("Checking MCP task-manager server...")
mcp_check = verify_mcp_server(auto_rebuild=True)
if mcp_check["ok"]:
    status = "OK"
    if mcp_check["rebuilt"]:
        status = "OK (rebuilt)"
    print(f"  MCP server: {status} - {mcp_check['message']}")
else:
    print(f"\n{'='*60}")
    print("WARNING: MCP task-manager server check failed!")
    print(f"  {mcp_check['message']}")
    print(f"{'='*60}\n")

print("\nStarting API server on http://localhost:8010")
print("API documentation available at http://localhost:8010/docs")
print("\n[!]  Auto-reload is DISABLED")
print("   You must manually restart the server to see code changes")
print("\nPress Ctrl+C to stop the server")
print("="*60 + "\n")

# Start the server WITHOUT auto-reload
# This prevents watchfiles from reloading when projects/ directory changes
uvicorn.run(
    "server.api.app:app",
    host="0.0.0.0",
    port=8010,
    reload=False,  # DISABLED: Must manually restart to see code changes
    log_level="error"
)
