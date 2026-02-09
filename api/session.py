"""
Session management for FastAPI backend.
Replaces Streamlit's session_state with in-memory session storage.
"""
import uuid
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field

from src.core.orchestrator import OrchestratorAgent
from src.requirements.generator import RequirementsGenerator


@dataclass
class UserSession:
    """Represents a user session with all state."""
    session_id: str
    created_at: datetime
    last_accessed: datetime
    
    # Core components (lazy initialized)
    _orchestrator: Optional[OrchestratorAgent] = field(default=None, repr=False)
    _requirements_generator: Optional[RequirementsGenerator] = field(default=None, repr=False)
    
    # State
    messages: list = field(default_factory=list)
    selected_role: str = "Requirements Analyst"
    indexed_files: Set[str] = field(default_factory=set)
    generated_srs: Optional[Dict] = None
    srs_markdown: Optional[str] = None
    
    # Deep Research state
    deep_research_task: Optional[str] = None
    deep_research_status: Optional[str] = None
    deep_research_result: Optional[Dict] = None
    deep_research_query: Optional[str] = None
    
    @property
    def orchestrator(self) -> OrchestratorAgent:
        """Lazy initialize orchestrator."""
        if self._orchestrator is None:
            self._orchestrator = OrchestratorAgent()
        return self._orchestrator
    
    @property
    def requirements_generator(self) -> RequirementsGenerator:
        """Lazy initialize requirements generator."""
        if self._requirements_generator is None:
            self._requirements_generator = RequirementsGenerator()
        return self._requirements_generator
    
    def touch(self):
        """Update last accessed time."""
        self.last_accessed = datetime.now()


class SessionManager:
    """
    Thread-safe session manager.
    Stores sessions in memory with automatic cleanup of expired sessions.
    """
    
    def __init__(self, session_timeout_minutes: int = 60):
        self._sessions: Dict[str, UserSession] = {}
        self._lock = threading.RLock()
        self._timeout = timedelta(minutes=session_timeout_minutes)
    
    def create_session(self) -> UserSession:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        now = datetime.now()
        
        session = UserSession(
            session_id=session_id,
            created_at=now,
            last_accessed=now
        )
        
        with self._lock:
            self._sessions[session_id] = session
            self._cleanup_expired()
        
        return session
    
    def get_session(self, session_id: str) -> Optional[UserSession]:
        """Get session by ID, returns None if not found or expired."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            
            # Check if expired
            if datetime.now() - session.last_accessed > self._timeout:
                del self._sessions[session_id]
                return None
            
            session.touch()
            return session
    
    def get_or_create_session(self, session_id: Optional[str] = None) -> UserSession:
        """Get existing session or create new one."""
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session
        return self.create_session()
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False
    
    def _cleanup_expired(self):
        """Remove expired sessions (called internally with lock held)."""
        now = datetime.now()
        expired = [
            sid for sid, session in self._sessions.items()
            if now - session.last_accessed > self._timeout
        ]
        for sid in expired:
            del self._sessions[sid]


# Global session manager instance
session_manager = SessionManager()


# Deep Research background task storage (shared across sessions)
_deep_research_lock = threading.Lock()
_deep_research_results: Dict[str, Dict[str, Any]] = {}


def get_deep_research_results() -> Dict[str, Dict[str, Any]]:
    """Get the deep research results storage."""
    return _deep_research_results


def get_deep_research_lock() -> threading.Lock:
    """Get the deep research lock."""
    return _deep_research_lock
