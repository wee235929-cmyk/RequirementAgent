"""
LangFuse handler module.
Provides centralized handler initialization for LangChain/LangGraph tracing.
Compatible with Langfuse 3.x which uses environment variables for configuration.
"""
import os
import uuid
from typing import Optional, List, Any

from .config import LANGFUSE_CONFIG, is_configured

# Global client instance (lazy initialization)
_langfuse_client = None
_initialization_attempted = False
_env_configured = False


def _get_logger():
    """Get logger - import here to avoid circular imports."""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from utils import get_logger
        return get_logger(__name__)
    except ImportError:
        import logging
        return logging.getLogger(__name__)


def _ensure_env_configured():
    """Ensure Langfuse environment variables are set from config."""
    global _env_configured
    if _env_configured:
        return
    
    # Langfuse 3.x reads from environment variables
    if LANGFUSE_CONFIG.get("secret_key"):
        os.environ.setdefault("LANGFUSE_SECRET_KEY", LANGFUSE_CONFIG["secret_key"])
    if LANGFUSE_CONFIG.get("public_key"):
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", LANGFUSE_CONFIG["public_key"])
    if LANGFUSE_CONFIG.get("host"):
        os.environ.setdefault("LANGFUSE_HOST", LANGFUSE_CONFIG["host"])
    
    _env_configured = True


def is_langfuse_enabled() -> bool:
    """Check if LangFuse is enabled and properly configured."""
    return is_configured()


def get_langfuse_client():
    """
    Get or create the global LangFuse client instance.
    Returns None if LangFuse is not enabled or not configured.
    """
    global _langfuse_client, _initialization_attempted
    
    if _initialization_attempted:
        return _langfuse_client
    
    _initialization_attempted = True
    logger = _get_logger()
    
    if not is_configured():
        logger.info("LangFuse is disabled or not configured")
        return None
    
    _ensure_env_configured()
    
    try:
        from langfuse import Langfuse
        _langfuse_client = Langfuse()
        logger.info(f"LangFuse client initialized (host: {LANGFUSE_CONFIG['host']})")
        return _langfuse_client
        
    except ImportError:
        logger.warning("langfuse package not installed. Run: pip install langfuse")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize LangFuse client: {e}")
        return None


def get_langfuse_handler(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[dict] = None,
):
    """
    Get a LangFuse CallbackHandler for LangChain/LangGraph tracing.
    
    Args:
        session_id: Optional session identifier for grouping traces
        user_id: Optional user identifier
        tags: Optional list of tags for filtering traces
        metadata: Optional metadata dictionary
        
    Returns:
        CallbackHandler instance or None if LangFuse is not enabled
    """
    if not is_configured():
        return None
    
    logger = _get_logger()
    _ensure_env_configured()
    
    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        try:
            from langfuse.callback import CallbackHandler
        except ImportError:
            logger.warning("langfuse package not installed. Run: pip install langfuse")
            return None
    
    try:
        # Langfuse 3.x: CallbackHandler reads config from environment variables
        # We pass session_id, user_id, tags, metadata via update_trace or trace_context
        handler = CallbackHandler()
        
        # Set trace attributes if provided (for Langfuse 3.x compatibility)
        # These will be applied when the trace is created
        if hasattr(handler, 'session_id') and session_id:
            handler.session_id = session_id
        if hasattr(handler, 'user_id') and user_id:
            handler.user_id = user_id
        if hasattr(handler, 'tags') and tags:
            handler.tags = tags
        if hasattr(handler, 'metadata') and metadata:
            handler.metadata = metadata
            
        return handler
        
    except ImportError:
        logger.warning("langfuse package not installed")
        return None
    except Exception as e:
        logger.error(f"Failed to create LangFuse handler: {e}")
        return None


def create_session_handler(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    intent: Optional[str] = None,
    role: Optional[str] = None,
):
    """
    Create a LangFuse handler for a specific session with RAAA-specific metadata.
    
    Args:
        session_id: Session identifier (auto-generated if not provided)
        user_id: User identifier
        intent: Current intent (e.g., 'requirements_generation', 'rag_qa')
        role: User role (e.g., 'Requirements Analyst')
        
    Returns:
        CallbackHandler instance or None if LangFuse is not enabled
    """
    if not is_configured():
        return None
    
    # Generate session ID if not provided
    if not session_id:
        session_id = f"raaa_{uuid.uuid4().hex[:12]}"
    
    # Build tags
    tags = ["raaa"]
    if intent:
        tags.append(f"intent:{intent}")
    if role:
        tags.append(f"role:{role.lower().replace(' ', '_')}")
    
    # Build metadata
    metadata = {}
    if intent:
        metadata["intent"] = intent
    if role:
        metadata["role"] = role
    
    return get_langfuse_handler(
        session_id=session_id,
        user_id=user_id,
        tags=tags,
        metadata=metadata,
    )


def flush_langfuse():
    """Flush any pending LangFuse events. Call this before application shutdown."""
    client = get_langfuse_client()
    if client:
        try:
            client.flush()
        except Exception:
            pass
