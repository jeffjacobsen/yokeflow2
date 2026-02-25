"""
Context File Retrieval Tool
============================

MCP tool for on-demand context file retrieval during agent sessions.
Allows agents to access uploaded context files when needed.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from server.generation.context_manager import ContextManager
from server.generation.context_manifest import ContextManifest
from server.utils.logging import get_logger

logger = get_logger(__name__)


class ContextTool:
    """MCP tool for context file retrieval during agent sessions."""

    # Tool metadata for MCP registration
    TOOL_METADATA = {
        "name": "retrieve_context_file",
        "description": "Retrieve a context file that was uploaded during project creation",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the context file to retrieve"
                },
                "project_dir": {
                    "type": "string",
                    "description": "Path to the project directory"
                }
            },
            "required": ["filename", "project_dir"]
        }
    }

    def __init__(self):
        """Initialize the context tool."""
        self.context_managers = {}  # Cache managers by project

    def _get_context_manager(self, project_dir: str) -> ContextManager:
        """Get or create a context manager for a project.

        Args:
            project_dir: Project directory path

        Returns:
            ContextManager instance
        """
        if project_dir not in self.context_managers:
            self.context_managers[project_dir] = ContextManager(Path(project_dir))
        return self.context_managers[project_dir]

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the context retrieval tool.

        Args:
            params: Tool parameters with filename and project_dir

        Returns:
            Tool response with file content or error
        """
        filename = params.get("filename")
        project_dir = params.get("project_dir")

        if not filename:
            return {
                "success": False,
                "error": "Filename parameter is required"
            }

        if not project_dir:
            return {
                "success": False,
                "error": "Project directory parameter is required"
            }

        try:
            # Get context manager
            context_manager = self._get_context_manager(project_dir)

            # Try to load the file
            content = context_manager.load_context_file(filename)

            if content is None:
                # File not found, check manifest for available files
                manifest = context_manager.get_context_manifest()
                available_files = [f["name"] for f in manifest.get("files", [])]

                return {
                    "success": False,
                    "error": f"File '{filename}' not found",
                    "available_files": available_files,
                    "suggestion": "Use one of the available files listed above"
                }

            # Get summary from manifest if available
            manifest_path = Path(project_dir) / ".yokeflow" / "context" / "manifest.json"
            summary = None
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                    for file_entry in manifest.get("files", []):
                        if file_entry["name"] == filename:
                            summary = file_entry.get("summary")
                            break
                except Exception as e:
                    logger.warning(f"Could not load summary from manifest: {e}")

            return {
                "success": True,
                "filename": filename,
                "content": content,
                "summary": summary,
                "size": len(content)
            }

        except Exception as e:
            logger.error(f"Error retrieving context file: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def list_context_files(self, project_dir: str) -> Dict[str, Any]:
        """List all available context files for a project.

        Args:
            project_dir: Project directory path

        Returns:
            List of available files with metadata
        """
        try:
            context_manager = self._get_context_manager(project_dir)
            manifest = context_manager.get_context_manifest()

            return {
                "success": True,
                "files": manifest.get("files", []),
                "total_size": manifest.get("total_size", 0),
                "file_count": manifest.get("file_count", 0),
                "categories": manifest.get("categories", {}),
                "loading_strategy": manifest.get("loading_strategy", {})
            }

        except Exception as e:
            logger.error(f"Error listing context files: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_recommended_files(self, project_dir: str) -> Dict[str, Any]:
        """Get recommended context files based on manifest.

        Args:
            project_dir: Project directory path

        Returns:
            Recommended files and their content
        """
        try:
            # Load manifest to get recommendations
            manifest_path = Path(project_dir) / ".yokeflow" / "context" / "manifest.json"
            if not manifest_path.exists():
                return {
                    "success": False,
                    "error": "No context manifest found"
                }

            manifest = json.loads(manifest_path.read_text())
            recommendations = manifest.get("recommendations", {})
            initial_files = recommendations.get("initial_files", [])

            if not initial_files:
                return {
                    "success": True,
                    "message": "No specific files recommended - load as needed",
                    "files": []
                }

            # Load recommended files
            context_manager = self._get_context_manager(project_dir)
            loaded_files = []

            for filename in initial_files:
                content = context_manager.load_context_file(filename)
                if content:
                    # Find summary from manifest
                    summary = None
                    for file_entry in manifest.get("files", []):
                        if file_entry["name"] == filename:
                            summary = file_entry.get("summary")
                            break

                    loaded_files.append({
                        "name": filename,
                        "content": content,
                        "summary": summary,
                        "size": len(content)
                    })

            return {
                "success": True,
                "files": loaded_files,
                "count": len(loaded_files),
                "suggestions": recommendations.get("suggestions", [])
            }

        except Exception as e:
            logger.error(f"Error getting recommended files: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def register_with_mcp(self) -> Dict[str, Any]:
        """Get MCP registration information for this tool.

        Returns:
            MCP tool registration dictionary
        """
        return {
            "tools": [self.TOOL_METADATA],
            "handler": self.execute
        }

    async def load_context_for_task(
        self,
        project_dir: str,
        task_name: str
    ) -> Dict[str, Any]:
        """Load context files relevant to a specific task.

        Args:
            project_dir: Project directory path
            task_name: Name of the current task

        Returns:
            Relevant context files and content
        """
        try:
            # Load manifest to understand available files
            manifest_path = Path(project_dir) / ".yokeflow" / "context" / "manifest.json"
            if not manifest_path.exists():
                return {
                    "success": True,
                    "message": "No context files available",
                    "files": []
                }

            manifest = json.loads(manifest_path.read_text())
            loading_strategy = manifest.get("loading_strategy", {})

            # If load_all strategy, return all files
            if loading_strategy.get("strategy_type") == "load_all":
                context_manager = self._get_context_manager(project_dir)
                all_files = context_manager.load_all_context_files()
                return {
                    "success": True,
                    "strategy": "load_all",
                    "files": [
                        {"name": name, "content": content}
                        for name, content in all_files.items()
                    ]
                }

            # Otherwise, use task-specific loading
            relevant_files = []
            task_lower = task_name.lower()

            # Keywords to file type mapping
            keyword_mapping = {
                "database": ["database", "sql"],
                "api": ["backend", "api", "endpoint"],
                "ui": ["frontend", "component", "page"],
                "config": ["configuration", "settings", "environment"],
                "test": ["test", "testing", "spec"]
            }

            # Determine relevant file types based on task
            relevant_types = set()
            for keyword, types in keyword_mapping.items():
                if keyword in task_lower:
                    relevant_types.update(types)

            # Load relevant files
            context_manager = self._get_context_manager(project_dir)
            for file_entry in manifest.get("files", []):
                file_type = file_entry.get("type", "")
                filename = file_entry["name"]

                # Check if file is relevant
                if (file_type in relevant_types or
                    any(keyword in filename.lower() for keyword in relevant_types)):
                    content = context_manager.load_context_file(filename)
                    if content:
                        relevant_files.append({
                            "name": filename,
                            "content": content,
                            "summary": file_entry.get("summary"),
                            "type": file_type
                        })

            return {
                "success": True,
                "strategy": "task_specific",
                "task": task_name,
                "files": relevant_files,
                "count": len(relevant_files)
            }

        except Exception as e:
            logger.error(f"Error loading context for task: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }