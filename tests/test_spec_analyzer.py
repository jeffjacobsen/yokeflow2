"""
Test suite for the Spec Pre-Analysis module.

Tests the optional pre-analysis of specification files that generates
a condensed summary, feature list, and suggested epic structure.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.generation.spec_analyzer import analyze_spec, ANALYSIS_PROMPT
from server.utils.config import Config, SpecAnalysisConfig


# --- Fixtures ---

SAMPLE_SPEC = """# My App

## Overview
A task management application with real-time collaboration.

## Tech Stack
- React, TypeScript, Node.js, PostgreSQL

## Features
- User authentication
- Task boards with drag-and-drop
- Real-time updates via WebSocket
"""

VALID_ANALYSIS_JSON = {
    "summary": "A task management app with real-time collaboration features.",
    "key_features": [
        "User authentication",
        "Task boards",
        "Drag-and-drop",
        "Real-time updates",
    ],
    "technical_requirements": ["React", "TypeScript", "Node.js", "PostgreSQL", "WebSocket"],
    "suggested_epics": [
        {"name": "Project Setup", "rationale": "Foundation for all other work"},
        {"name": "Authentication", "rationale": "Required before user-specific features"},
        {"name": "Task Board UI", "rationale": "Core feature of the application"},
    ],
    "complexity_assessment": "medium",
    "key_risks": ["WebSocket scaling", "Real-time conflict resolution"],
}


def _mock_anthropic_response(text: str) -> MagicMock:
    """Create a mock Anthropic API response."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


# --- Tests ---


class TestAnalyzeSpec:
    """Tests for the analyze_spec function."""

    @pytest.mark.asyncio
    async def test_valid_json_response(self):
        """Parses a clean JSON response correctly."""
        mock_response = _mock_anthropic_response(json.dumps(VALID_ANALYSIS_JSON))

        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "test-token"}):
            with patch("server.generation.spec_analyzer.AsyncAnthropic") as mock_cls:
                mock_client = AsyncMock()
                mock_client.messages.create.return_value = mock_response
                mock_cls.return_value = mock_client

                result = await analyze_spec(SAMPLE_SPEC, model="claude-haiku-4-5-20251001")

        assert result["summary"] == VALID_ANALYSIS_JSON["summary"]
        assert len(result["key_features"]) == 4
        assert len(result["suggested_epics"]) == 3
        assert result["complexity_assessment"] == "medium"

    @pytest.mark.asyncio
    async def test_json_wrapped_in_code_fences(self):
        """Extracts JSON from markdown code fences."""
        wrapped = f"```json\n{json.dumps(VALID_ANALYSIS_JSON)}\n```"
        mock_response = _mock_anthropic_response(wrapped)

        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "test-token"}):
            with patch("server.generation.spec_analyzer.AsyncAnthropic") as mock_cls:
                mock_client = AsyncMock()
                mock_client.messages.create.return_value = mock_response
                mock_cls.return_value = mock_client

                result = await analyze_spec(SAMPLE_SPEC)

        assert result["summary"] == VALID_ANALYSIS_JSON["summary"]
        assert len(result["suggested_epics"]) == 3

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        """Raises ValueError when response is not valid JSON."""
        mock_response = _mock_anthropic_response("This is not JSON at all.")

        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "test-token"}):
            with patch("server.generation.spec_analyzer.AsyncAnthropic") as mock_cls:
                mock_client = AsyncMock()
                mock_client.messages.create.return_value = mock_response
                mock_cls.return_value = mock_client

                with pytest.raises(ValueError, match="invalid JSON"):
                    await analyze_spec(SAMPLE_SPEC)

    @pytest.mark.asyncio
    async def test_missing_fields_get_defaults(self):
        """Missing fields in response are filled with defaults."""
        partial = {"summary": "A task app."}
        mock_response = _mock_anthropic_response(json.dumps(partial))

        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "test-token"}):
            with patch("server.generation.spec_analyzer.AsyncAnthropic") as mock_cls:
                mock_client = AsyncMock()
                mock_client.messages.create.return_value = mock_response
                mock_cls.return_value = mock_client

                result = await analyze_spec(SAMPLE_SPEC)

        assert result["summary"] == "A task app."
        assert result["key_features"] == []
        assert result["technical_requirements"] == []
        assert result["suggested_epics"] == []
        assert result["key_risks"] == []
        assert result["complexity_assessment"] == "medium"

    @pytest.mark.asyncio
    async def test_no_oauth_token_raises(self):
        """Raises ValueError when CLAUDE_CODE_OAUTH_TOKEN is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Also patch to ensure no .env loading overrides
            with patch("server.generation.spec_analyzer.os.getenv", return_value=None):
                with pytest.raises(ValueError, match="CLAUDE_CODE_OAUTH_TOKEN"):
                    await analyze_spec(SAMPLE_SPEC)

    @pytest.mark.asyncio
    async def test_passes_correct_model(self):
        """The specified model is passed to the Anthropic API call."""
        mock_response = _mock_anthropic_response(json.dumps(VALID_ANALYSIS_JSON))

        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "test-token"}):
            with patch("server.generation.spec_analyzer.AsyncAnthropic") as mock_cls:
                mock_client = AsyncMock()
                mock_client.messages.create.return_value = mock_response
                mock_cls.return_value = mock_client

                await analyze_spec(SAMPLE_SPEC, model="claude-sonnet-4-6")

                call_kwargs = mock_client.messages.create.call_args
                assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_spec_content_included_in_prompt(self):
        """The spec content is included in the prompt sent to the API."""
        mock_response = _mock_anthropic_response(json.dumps(VALID_ANALYSIS_JSON))

        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "test-token"}):
            with patch("server.generation.spec_analyzer.AsyncAnthropic") as mock_cls:
                mock_client = AsyncMock()
                mock_client.messages.create.return_value = mock_response
                mock_cls.return_value = mock_client

                await analyze_spec(SAMPLE_SPEC)

                call_kwargs = mock_client.messages.create.call_args
                messages = call_kwargs.kwargs["messages"]
                assert len(messages) == 1
                assert SAMPLE_SPEC in messages[0]["content"]


class TestSpecAnalysisConfig:
    """Tests for SpecAnalysisConfig and YAML loading."""

    def test_default_config(self):
        """Default config has spec_analysis disabled."""
        config = Config()
        assert config.spec_analysis.enabled is False
        assert config.spec_analysis.model == "claude-haiku-4-5-20251001"

    def test_load_from_yaml(self, tmp_path):
        """Config loads spec_analysis from YAML."""
        yaml_content = """
spec_analysis:
  enabled: true
  model: claude-sonnet-4-6
"""
        config_path = tmp_path / ".yokeflow.yaml"
        config_path.write_text(yaml_content)

        config = Config.load_from_file(config_path)
        assert config.spec_analysis.enabled is True
        assert config.spec_analysis.model == "claude-sonnet-4-6"

    def test_partial_yaml(self, tmp_path):
        """Config handles partial spec_analysis in YAML."""
        yaml_content = """
spec_analysis:
  enabled: true
"""
        config_path = tmp_path / ".yokeflow.yaml"
        config_path.write_text(yaml_content)

        config = Config.load_from_file(config_path)
        assert config.spec_analysis.enabled is True
        assert config.spec_analysis.model == "claude-haiku-4-5-20251001"  # default
