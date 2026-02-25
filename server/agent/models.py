"""
Orchestrator Data Models
========================

Data classes and enums used by the orchestrator.
Extracted from orchestrator.py for better organization.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class SessionStatus(Enum):
    """Session status enumeration."""
    PENDING = "pending"  # Session created but not started
    RUNNING = "running"  # Session currently executing
    COMPLETED = "completed"  # Session finished successfully
    ERROR = "error"  # Session encountered an error
    INTERRUPTED = "interrupted"  # Session was interrupted (Ctrl+C)
    BLOCKED = "blocked"  # Session blocked due to epic test failure (intervention required)


class SessionType(Enum):
    """Session type enumeration."""
    INITIALIZER = "initializer"  # First session that sets up project
    CODING = "coding"  # Regular coding session
    REVIEW = "review"  # Review session for quality analysis


@dataclass
class SessionInfo:
    """Information about a session."""
    session_id: str
    project_id: str
    session_number: int
    session_type: SessionType
    model: str
    status: SessionStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metrics: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "session_number": self.session_number,
            "session_type": self.session_type.value,
            "model": self.model,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "error_message": self.error_message,
            "metrics": self.metrics or {},
        }
