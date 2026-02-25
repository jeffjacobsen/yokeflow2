"""
AI-Powered Specification Generator using Claude SDK
=====================================================

Generates structured application specifications from natural language descriptions
using the same Claude SDK client that YokeFlow uses for agent sessions.
"""

import asyncio
import json
import logging
import os
import tempfile
from typing import Optional, Dict, Any, List, AsyncGenerator
from pathlib import Path
from dotenv import load_dotenv

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from server.utils.auth import get_oauth_token
from server.utils.config import Config
from server.utils.logging import get_logger

# Load environment variables from .env file
_current_file = Path(__file__)
_generation_dir = _current_file.parent
_server_dir = _generation_dir.parent
_project_root = _server_dir.parent
_env_file = _project_root / ".env"

# Load the .env file to make CLAUDE_CODE_OAUTH_TOKEN available
load_dotenv(dotenv_path=_env_file)

logger = get_logger(__name__)


class SpecGenerator:
    """Generate application specifications using Claude SDK."""

    # Prompt template for Claude
    GENERATION_PROMPT = """You are an expert software architect helping to create a detailed application specification.

Based on the following description, generate a comprehensive specification document for a web application.

Description: {description}

{context_section}

Please generate a detailed specification in markdown format with the following sections:
1. **Overview** - A clear description of what the application does and its main purpose
2. **Tech Stack** - The technologies to be used (frameworks, libraries, tools)
3. **Frontend** - Detailed frontend requirements, components, and user interface
4. **Backend** - API endpoints, business logic, and server-side functionality
5. **Database** - Schema design, tables, relationships, and data models
6. **Additional Features** - Authentication, security, performance, deployment considerations
7. **Development Notes** - Implementation suggestions and best practices

Make the specification detailed enough that a developer could implement the application from it.
Focus on modern web development best practices and use popular, well-maintained technologies.

Return ONLY the markdown content, no explanations or meta-commentary."""

    CONTEXT_TEMPLATE = """
Context Files Provided:
{context_summaries}

Please incorporate insights from these context files into the specification where relevant.
"""

    def __init__(self, config: Optional[Config] = None):
        """Initialize the spec generator.

        Args:
            config: Optional configuration object
        """
        self.config = config or Config()
        self.client = None

        # Model selection - use Sonnet for cost efficiency
        # Use the same model as the coding agent
        self.model = "claude-sonnet-4-6"  # Default model
        if hasattr(self.config, 'generation') and hasattr(self.config.generation, 'model'):
            self.model = self.config.generation.model
        elif hasattr(self.config, 'models') and hasattr(self.config.models, 'coding'):
            self.model = self.config.models.coding

    def _create_client(self, temp_dir: Path) -> ClaudeSDKClient:
        """Create a Claude SDK client for spec generation.

        Args:
            temp_dir: Temporary directory for the SDK to work in

        Returns:
            Configured ClaudeSDKClient
        """
        # Get OAuth token
        oauth_token = get_oauth_token()

        if not oauth_token:
            raise ValueError(
                "No OAuth token found. Please ensure you're authenticated with Claude Code. "
                "Run 'claude setup-token' or check ~/.claude/.credentials.json"
            )

        # Prepare environment for SDK
        sdk_env = {
            "CLAUDE_CODE_OAUTH_TOKEN": oauth_token,
            "ANTHROPIC_API_KEY": ""  # Explicitly unset to prevent conflicts
        }

        # Create a minimal client without MCP servers since we just need to generate text
        return ClaudeSDKClient(
            options=ClaudeAgentOptions(
                model=self.model,
                system_prompt="You are an expert software architect helping to create detailed application specifications.",
                permission_mode="bypassPermissions",
                mcp_servers={},  # No MCP servers needed for spec generation
                max_turns=1,  # Single turn conversation
                cwd=str(temp_dir),
                env=sdk_env
            )
        )

    async def _sdk_query(self, prompt: str, system_prompt: Optional[str] = None,
                         max_turns: int = 1) -> str:
        """Run a single-turn SDK query and return the text response.

        Args:
            prompt: The user prompt to send
            system_prompt: Optional override for the system prompt
            max_turns: Maximum conversation turns

        Returns:
            The text content from Claude's response
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            oauth_token = get_oauth_token()

            if not oauth_token:
                raise ValueError(
                    "No OAuth token found. Please ensure you're authenticated with Claude Code. "
                    "Run 'claude setup-token' or check ~/.claude/.credentials.json"
                )

            sdk_env = {
                "CLAUDE_CODE_OAUTH_TOKEN": oauth_token,
                "ANTHROPIC_API_KEY": ""
            }

            client = ClaudeSDKClient(
                options=ClaudeAgentOptions(
                    model=self.model,
                    system_prompt=system_prompt or "You are an expert software architect.",
                    permission_mode="bypassPermissions",
                    mcp_servers={},
                    max_turns=max_turns,
                    cwd=str(temp_path),
                    env=sdk_env
                )
            )

            async with client:
                await client.query(prompt)

                content = ""
                async for msg in client.receive_response():
                    if type(msg).__name__ == "AssistantMessage" and hasattr(msg, "content"):
                        for block in msg.content:
                            if type(block).__name__ == "TextBlock" and hasattr(block, "text"):
                                content += block.text

            return content

    async def generate_spec(
        self,
        description: str,
        project_name: str,
        context_files: Optional[List[Dict[str, str]]] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """Generate a specification from a natural language description.

        Args:
            description: Natural language description of the application
            project_name: Name of the project
            context_files: Optional list of context files with their summaries
            stream: Whether to stream the response (for SSE)

        Yields:
            Chunks of the generated specification
        """
        # Prepare context section
        context_section = ""
        if context_files:
            summaries = "\n".join([
                f"- {file['name']}: {file.get('summary', 'No summary available')}"
                for file in context_files
            ])
            context_section = self.CONTEXT_TEMPLATE.format(
                context_summaries=summaries
            )

        # Build the full prompt
        prompt = self.GENERATION_PROMPT.format(
            description=description,
            context_section=context_section
        )

        logger.info(f"Generating specification for project: {project_name}")
        logger.debug(f"Description: {description[:200]}...")

        # Create a temporary directory for the SDK
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            try:
                # Create the client
                client = self._create_client(temp_path)

                # Use the client with async context manager (handles connect/disconnect)
                async with client:
                    # Send the query
                    logger.info("Sending prompt to Claude SDK...")
                    logger.debug(f"Prompt length: {len(prompt)} characters")
                    logger.debug(f"First 200 chars of prompt: {prompt[:200]}...")
                    await client.query(prompt)

                    # Collect the full response
                    spec_content = ""
                    message_count = 0
                    block_count = 0

                    async for msg in client.receive_response():
                        msg_type = type(msg).__name__
                        message_count += 1
                        logger.debug(f"Received message #{message_count} of type: {msg_type}")

                        # Handle AssistantMessage (text content)
                        if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                            for block in msg.content:
                                block_type = type(block).__name__
                                block_count += 1
                                logger.debug(f"  Block #{block_count} type: {block_type}")

                                if block_type == "TextBlock" and hasattr(block, "text"):
                                    text_chunk = block.text
                                    spec_content += text_chunk
                                    logger.debug(f"  Added {len(text_chunk)} characters")
                                    logger.debug(f"  First 100 chars: {text_chunk[:100]}...")

                    logger.info(f"Received {message_count} messages with {block_count} blocks")

                    if spec_content:
                        logger.info(f"Generated specification ({len(spec_content)} characters)")
                        logger.debug(f"Full spec first 500 chars: {spec_content[:500]}...")

                        if stream:
                            # Simulate streaming by yielding chunks
                            chunk_size = 100
                            for i in range(0, len(spec_content), chunk_size):
                                yield spec_content[i:i + chunk_size]
                                await asyncio.sleep(0.01)  # Small delay to simulate streaming
                        else:
                            # Yield the complete response
                            yield spec_content
                    else:
                        error_msg = "No response received from Claude"
                        logger.error(error_msg)
                        raise ValueError(error_msg)

            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg or "authentication" in error_msg.lower():
                    logger.error(
                        "Authentication failed. Please ensure you're logged in with Claude Code. "
                        "Run 'claude setup-token' to authenticate."
                    )
                    raise ValueError(
                        "Authentication failed. Please authenticate with 'claude setup-token' "
                        "and ensure your Claude Code credentials are valid."
                    )
                logger.error(f"Error generating specification: {error_msg}")
                raise

    async def generate_spec_sections(
        self,
        description: str,
        project_name: str,
        context_files: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, str]:
        """Generate specification sections as a dictionary.

        Args:
            description: Natural language description
            project_name: Name of the project
            context_files: Optional context files

        Returns:
            Dictionary with section names as keys and content as values
        """
        # Generate the full specification
        full_spec = ""
        async for chunk in self.generate_spec(
            description, project_name, context_files, stream=False
        ):
            full_spec += chunk

        return self._parse_markdown_sections(full_spec)

    def _parse_markdown_sections(self, markdown: str) -> Dict[str, str]:
        """Parse markdown into sections based on headers.

        Args:
            markdown: Markdown content to parse

        Returns:
            Dictionary of section names to content
        """
        sections = {}
        current_section = None
        current_content = []

        for line in markdown.split("\n"):
            # Check for main headers
            if line.startswith("## "):
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                # Start new section
                current_section = line[3:].strip().lower().replace(" ", "_")
                current_content = []
            elif current_section:
                current_content.append(line)
            elif line.startswith("# "):
                # Project title
                sections["title"] = line[2:].strip()

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    async def enhance_spec(self, existing_spec: str, feedback: str) -> str:
        """Enhance an existing specification based on user feedback.

        Args:
            existing_spec: Current specification markdown
            feedback: User feedback for improvements

        Returns:
            Enhanced specification
        """
        prompt = f"""You are helping to improve an application specification.

Current Specification:
{existing_spec}

User Feedback:
{feedback}

Please update the specification to address the feedback while maintaining the same markdown format and section structure.
Return ONLY the updated markdown content."""

        try:
            return await self._sdk_query(prompt)
        except Exception as e:
            logger.error(f"Error enhancing specification: {str(e)}")
            raise

    async def generate_summary(self, content: str, max_length: int = 500) -> str:
        """Generate a concise summary of content.

        Uses a cheaper model (Haiku) for cost efficiency.

        Args:
            content: Content to summarize
            max_length: Maximum length of summary

        Returns:
            Concise summary
        """
        summary_model = self.config.get("generation.summary_model", "claude-haiku-4-5")

        prompt = f"""Summarize the following content in {max_length} characters or less.
Focus on the key technical details and purpose.

Content:
{content[:5000]}

Return ONLY the summary, no explanations."""

        try:
            # Use Haiku for summaries via a dedicated client with the cheaper model
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                oauth_token = get_oauth_token()

                if not oauth_token:
                    raise ValueError("No OAuth token found.")

                sdk_env = {
                    "CLAUDE_CODE_OAUTH_TOKEN": oauth_token,
                    "ANTHROPIC_API_KEY": ""
                }

                client = ClaudeSDKClient(
                    options=ClaudeAgentOptions(
                        model=summary_model,
                        system_prompt="You are a concise technical summarizer.",
                        permission_mode="bypassPermissions",
                        mcp_servers={},
                        max_turns=1,
                        cwd=str(temp_path),
                        env=sdk_env
                    )
                )

                async with client:
                    await client.query(prompt)

                    content_result = ""
                    async for msg in client.receive_response():
                        if type(msg).__name__ == "AssistantMessage" and hasattr(msg, "content"):
                            for block in msg.content:
                                if type(block).__name__ == "TextBlock" and hasattr(block, "text"):
                                    content_result += block.text

                return content_result
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            # Fallback to simple truncation
            return content[:max_length] + "..." if len(content) > max_length else content
