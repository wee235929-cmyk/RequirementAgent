"""
Stats API routes for RAAA.
Provides memory and index statistics.
"""
from typing import Optional, List
from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.session import session_manager
from src.config import USER_ROLES, DEFAULT_ROLE


router = APIRouter()


class MemoryStats(BaseModel):
    """Memory statistics."""
    entity_count: int
    mem0_enabled: bool
    mem0_stats: Optional[dict] = None


class IndexStats(BaseModel):
    """RAG index statistics."""
    indexed_files: int
    total_chunks: int
    has_graph: bool
    graph_storage: str
    neo4j_connected: bool
    neo4j_entity_count: int
    neo4j_relationship_count: int
    needs_graph_update: bool


class SessionInfo(BaseModel):
    """Session information."""
    session_id: str
    selected_role: str
    message_count: int
    indexed_files_count: int
    has_srs: bool
    has_active_research: bool


@router.get("/memory", response_model=MemoryStats)
async def get_memory_stats(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Get memory statistics for the current session."""
    session = session_manager.get_or_create_session(x_session_id)
    memory = session.orchestrator.get_memory()
    
    stats = MemoryStats(
        entity_count=len(memory.entity_store),
        mem0_enabled=memory.is_mem0_enabled(),
    )
    
    if memory.is_mem0_enabled():
        stats.mem0_stats = memory.get_mem0_stats()
    
    return stats


@router.get("/index", response_model=IndexStats)
async def get_index_stats(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Get RAG index statistics."""
    session = session_manager.get_or_create_session(x_session_id)
    rag_indexer = session.orchestrator.get_rag_indexer()
    
    index_stats = rag_indexer.get_index_stats()
    needs_update = rag_indexer.needs_graph_update()
    
    return IndexStats(
        indexed_files=index_stats.get("indexed_files", 0),
        total_chunks=index_stats.get("total_chunks", 0),
        has_graph=index_stats.get("has_graph", False),
        graph_storage=index_stats.get("graph_storage", "json"),
        neo4j_connected=index_stats.get("neo4j_connected", False),
        neo4j_entity_count=index_stats.get("neo4j_entity_count", 0),
        neo4j_relationship_count=index_stats.get("neo4j_relationship_count", 0),
        needs_graph_update=needs_update,
    )


@router.get("/session", response_model=SessionInfo)
async def get_session_info(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Get current session information."""
    session = session_manager.get_or_create_session(x_session_id)
    
    return SessionInfo(
        session_id=session.session_id,
        selected_role=session.selected_role,
        message_count=len(session.messages),
        indexed_files_count=len(session.indexed_files),
        has_srs=session.generated_srs is not None,
        has_active_research=session.deep_research_task is not None,
    )


@router.get("/roles")
async def get_available_roles():
    """Get list of available user roles."""
    return {
        "roles": USER_ROLES,
        "default": DEFAULT_ROLE
    }


@router.delete("/memory/clear")
async def clear_memory(
    clear_mem0: bool = False,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Clear conversation memory."""
    session = session_manager.get_or_create_session(x_session_id)
    memory = session.orchestrator.get_memory()
    
    if clear_mem0 and memory.is_mem0_enabled():
        memory.clear_memory(clear_mem0=True)
        return {"success": True, "message": "Memory and Mem0 storage cleared."}
    else:
        session.orchestrator.clear_memory()
        return {"success": True, "message": "Memory cleared."}


@router.post("/session/new")
async def create_new_session():
    """Create a new session."""
    session = session_manager.create_session()
    return {
        "session_id": session.session_id,
        "message": "New session created."
    }


@router.delete("/session")
async def delete_session(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Delete the current session."""
    if x_session_id:
        deleted = session_manager.delete_session(x_session_id)
        if deleted:
            return {"success": True, "message": "Session deleted."}
    
    return {"success": False, "message": "Session not found."}
