"""
Specification Parser for Project Completion Review
Project Completion Review
Created: February 2, 2026

Parses app_spec.txt files to extract structured requirements for comparison
against implemented epics/tasks.
"""

import re
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class Requirement:
    """A single requirement extracted from specification."""
    id: str
    section: str
    text: str
    keywords: List[str] = field(default_factory=list)
    priority: str = "medium"  # high, medium, low
    line_number: int = 0
    is_nested: bool = False
    parent_id: Optional[str] = None


@dataclass
class SpecSection:
    """A section of the specification (Frontend, Backend, etc.)."""
    name: str
    requirements: List[Requirement] = field(default_factory=list)
    description: Optional[str] = None


@dataclass
class ParsedSpecification:
    """Complete parsed specification."""
    overview: str
    sections: Dict[str, SpecSection] = field(default_factory=dict)
    requirements: List[Requirement] = field(default_factory=list)
    spec_hash: str = ""
    spec_path: str = ""


class SpecificationParser:
    """
    Parse app_spec.txt files to extract requirements.

    Supports various markdown formats:
    - Sectioned specs (## Frontend, ## Backend, etc.)
    - Flat bullet lists
    - Numbered lists
    - Nested lists
    """

    # Common section names to recognize
    COMMON_SECTIONS = [
        "Frontend", "Backend", "Database", "API", "Authentication",
        "Authorization", "User Interface", "UI", "UX", "Features",
        "Additional Features", "Nice to Have", "MVP", "Phase 1", "Phase 2",
        "Requirements", "Functional Requirements", "Technical Requirements",
        "Infrastructure", "Deployment", "Testing", "Security"
    ]

    # Keywords that indicate high priority
    HIGH_PRIORITY_KEYWORDS = [
        "must", "required", "critical", "essential", "core", "mvp",
        "necessary", "mandatory", "vital", "crucial"
    ]

    # Keywords that indicate low priority
    LOW_PRIORITY_KEYWORDS = [
        "optional", "nice to have", "nice-to-have", "future", "later",
        "bonus", "enhancement", "could", "might", "consider"
    ]

    # Stop words for keyword extraction
    STOP_WORDS = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "should", "could", "may", "might", "can", "must", "shall"
    }

    def parse_spec(self, spec_path: Path) -> ParsedSpecification:
        """
        Parse specification file into structured format.

        Args:
            spec_path: Path to app_spec.txt file

        Returns:
            ParsedSpecification with all requirements extracted
        """
        logger.info(f"Parsing specification: {spec_path}")

        if not spec_path.exists():
            raise FileNotFoundError(f"Specification file not found: {spec_path}")

        # Read file content
        content = spec_path.read_text(encoding='utf-8')

        # Calculate hash
        spec_hash = hashlib.sha256(content.encode()).hexdigest()

        # Initialize result
        parsed = ParsedSpecification(
            overview="",
            spec_hash=spec_hash,
            spec_path=str(spec_path)
        )

        # Split into lines
        lines = content.split('\n')

        # Extract overview (everything before first section)
        overview_lines = []
        first_section_line = self._find_first_section(lines)

        if first_section_line > 0:
            overview_lines = lines[:first_section_line]
            parsed.overview = '\n'.join(overview_lines).strip()

        # Parse sections and requirements
        current_section: Optional[SpecSection] = None
        requirement_counter = 1

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Skip empty lines and code blocks
            if not stripped or stripped.startswith('```'):
                continue

            # Check for section header
            if stripped.startswith('##'):
                section_name = stripped.lstrip('#').strip()

                # Save previous section
                if current_section:
                    parsed.sections[current_section.name] = current_section

                # Start new section
                current_section = SpecSection(name=section_name)
                logger.debug(f"Found section: {section_name}")
                continue

            # Check for requirement (bullet or numbered list)
            req_text = self._extract_requirement_text(stripped)

            if req_text:
                # Determine section (use "General" if no section header found)
                section_name = current_section.name if current_section else "General"

                # Create requirement
                req = Requirement(
                    id=f"req_{requirement_counter}",
                    section=section_name,
                    text=req_text,
                    keywords=self._extract_keywords(req_text),
                    priority=self._infer_priority(req_text),
                    line_number=line_num,
                    is_nested=self._is_nested_requirement(line)
                )

                # Add to section and global list
                if current_section:
                    current_section.requirements.append(req)
                parsed.requirements.append(req)

                requirement_counter += 1
                logger.debug(f"Extracted requirement {req.id}: {req_text[:50]}...")

        # Save last section
        if current_section and current_section.name not in parsed.sections:
            parsed.sections[current_section.name] = current_section

        # If no sections found, create a "General" section with all requirements
        if not parsed.sections and parsed.requirements:
            general_section = SpecSection(name="General", requirements=parsed.requirements)
            parsed.sections["General"] = general_section

        logger.info(
            f"Parsed {len(parsed.requirements)} requirements "
            f"across {len(parsed.sections)} sections"
        )

        return parsed

    def _find_first_section(self, lines: List[str]) -> int:
        """Find the line number of the first section header."""
        for i, line in enumerate(lines):
            if line.strip().startswith('##'):
                return i
        return -1

    def _extract_requirement_text(self, line: str) -> Optional[str]:
        """
        Extract requirement text from a line if it's a bullet or numbered list item.

        Supports:
        - Bullet lists: -, *, +
        - Numbered lists: 1., 2., etc.
        - Nested lists with indentation
        """
        # Remove leading whitespace for pattern matching
        stripped = line.strip()

        # Bullet list patterns
        bullet_patterns = [
            r'^[-*+]\s+(.+)$',  # - item, * item, + item
            r'^\d+\.\s+(.+)$',  # 1. item, 2. item
        ]

        for pattern in bullet_patterns:
            match = re.match(pattern, stripped)
            if match:
                return match.group(1).strip()

        return None

    def _is_nested_requirement(self, line: str) -> bool:
        """Check if a requirement is nested (indented)."""
        # Count leading spaces/tabs
        leading_space = len(line) - len(line.lstrip())
        return leading_space > 0

    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract keywords from requirement text for matching.

        Uses simple heuristics:
        - Split on spaces and punctuation
        - Remove stop words
        - Keep words longer than 2 characters
        - Convert to lowercase
        """
        # Remove punctuation and split
        words = re.findall(r'\b\w+\b', text.lower())

        # Filter stop words and short words
        keywords = [
            word for word in words
            if word not in self.STOP_WORDS and len(word) > 2
        ]

        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords[:10]  # Limit to top 10 keywords

    def _infer_priority(self, text: str) -> str:
        """
        Infer requirement priority from text.

        Returns: "high", "medium", or "low"
        """
        text_lower = text.lower()

        # Check for high priority indicators
        for keyword in self.HIGH_PRIORITY_KEYWORDS:
            if keyword in text_lower:
                return "high"

        # Check for low priority indicators
        for keyword in self.LOW_PRIORITY_KEYWORDS:
            if keyword in text_lower:
                return "low"

        # Default to medium
        return "medium"

    def get_requirements_by_section(
        self,
        parsed: ParsedSpecification
    ) -> Dict[str, List[Requirement]]:
        """Get requirements grouped by section."""
        return {
            section_name: section.requirements
            for section_name, section in parsed.sections.items()
        }

    def get_requirements_by_priority(
        self,
        parsed: ParsedSpecification
    ) -> Dict[str, List[Requirement]]:
        """Get requirements grouped by priority."""
        by_priority: Dict[str, List[Requirement]] = {
            "high": [],
            "medium": [],
            "low": []
        }

        for req in parsed.requirements:
            by_priority[req.priority].append(req)

        return by_priority

    def get_requirement_count(self, parsed: ParsedSpecification) -> int:
        """Get total number of requirements."""
        return len(parsed.requirements)

    def to_dict(self, parsed: ParsedSpecification) -> Dict[str, Any]:
        """Convert parsed specification to dictionary for JSON serialization."""
        return {
            "overview": parsed.overview,
            "spec_hash": parsed.spec_hash,
            "spec_path": parsed.spec_path,
            "total_requirements": len(parsed.requirements),
            "sections": {
                name: {
                    "name": section.name,
                    "description": section.description,
                    "requirement_count": len(section.requirements),
                    "requirements": [
                        {
                            "id": req.id,
                            "text": req.text,
                            "keywords": req.keywords,
                            "priority": req.priority,
                            "line_number": req.line_number,
                            "is_nested": req.is_nested
                        }
                        for req in section.requirements
                    ]
                }
                for name, section in parsed.sections.items()
            },
            "requirements_by_priority": {
                priority: len(reqs)
                for priority, reqs in self.get_requirements_by_priority(parsed).items()
            }
        }
