"""
Mem0 Memory Integration Module for RAAA.

This module provides a wrapper around the mem0 framework for persistent memory storage.
It supports both conversation history persistence and semantic memory (entities/facts).

Usage:
    - Set MEM0_ENABLED=true in .env to enable
    - Memories are stored locally in mem0_storage/ directory
    - Works alongside existing FAISS-based memory (non-destructive)
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MEM0_CONFIG
from utils import get_logger

logger = get_logger(__name__)


class Mem0MemoryStore:
    """
    Wrapper for mem0 persistent memory framework.
    
    Provides:
    - Conversation history persistence (messages)
    - Semantic memory storage (entities, facts, decisions)
    - Memory retrieval with semantic search
    """
    
    def __init__(self, user_id: Optional[str] = None):
        """
        Initialize Mem0 memory store.
        
        Args:
            user_id: User identifier for memory isolation. Defaults to config value.
        """
        self.enabled = MEM0_CONFIG.get("enabled", False)
        self.user_id = user_id or MEM0_CONFIG.get("user_id", "raaa_default_user")
        self.memory = None
        self._initialized = False
        
        if self.enabled:
            self._initialize_mem0()
    
    def _initialize_mem0(self) -> bool:
        """Initialize mem0 client with configuration."""
        try:
            from mem0 import Memory
        except ImportError:
            print("[Mem0] ERROR: mem0ai package not installed. Run: pip install mem0ai")
            logger.warning("mem0ai package not installed. Run: pip install mem0ai")
            self.enabled = False
            return False
        
        try:
            import chromadb
        except ImportError:
            print("[Mem0] ERROR: chromadb package not installed. Run: pip install chromadb")
            logger.warning("chromadb package not installed. Run: pip install chromadb")
            self.enabled = False
            return False
        
        try:
            storage_path = Path(MEM0_CONFIG.get("storage_path", "mem0_storage"))
            storage_path.mkdir(parents=True, exist_ok=True)
            
            config = {
                "llm": MEM0_CONFIG.get("llm", {}),
                "embedder": MEM0_CONFIG.get("embedder", {}),
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": "raaa_memories",
                        "path": str(storage_path),
                    }
                },
                "version": MEM0_CONFIG.get("version", "v1.1"),
            }
            
            print(f"[Mem0] Initializing with storage path: {storage_path}")
            self.memory = Memory.from_config(config)
            self._initialized = True
            print(f"[Mem0] Successfully initialized for user: {self.user_id}")
            logger.info(f"Mem0 initialized successfully for user: {self.user_id}")
            return True
            
        except Exception as e:
            print(f"[Mem0] ERROR: Failed to initialize: {e}")
            logger.error(f"Failed to initialize mem0: {e}")
            import traceback
            traceback.print_exc()
            self.enabled = False
            return False
    
    def is_available(self) -> bool:
        """Check if mem0 is available and initialized."""
        return self.enabled and self._initialized and self.memory is not None
    
    def add_conversation(self, user_message: str, assistant_message: str, 
                         metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store a conversation turn in mem0.
        
        Args:
            user_message: The user's input message
            assistant_message: The assistant's response
            metadata: Optional metadata (e.g., intent, role)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message}
            ]
            
            meta = metadata or {}
            meta["timestamp"] = datetime.now().isoformat()
            meta["type"] = "conversation"
            
            self.memory.add(messages, user_id=self.user_id, metadata=meta)
            logger.debug(f"Stored conversation in mem0 for user: {self.user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store conversation in mem0: {e}")
            return False
    
    def add_entity(self, entity_text: str, entity_type: str = "requirement",
                   metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store an entity/fact in mem0.
        
        Args:
            entity_text: The entity content (e.g., "FR-001: User login requirement")
            entity_type: Type of entity (requirement, decision, constraint, etc.)
            metadata: Additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            meta = metadata or {}
            meta["timestamp"] = datetime.now().isoformat()
            meta["type"] = "entity"
            meta["entity_type"] = entity_type
            
            self.memory.add(entity_text, user_id=self.user_id, metadata=meta)
            logger.debug(f"Stored entity in mem0: {entity_type}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store entity in mem0: {e}")
            return False
    
    def add_summary(self, summary_text: str, 
                    metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store a conversation summary in mem0.
        
        Args:
            summary_text: The summary content
            metadata: Additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            meta = metadata or {}
            meta["timestamp"] = datetime.now().isoformat()
            meta["type"] = "summary"
            
            self.memory.add(
                f"Conversation Summary: {summary_text}",
                user_id=self.user_id,
                metadata=meta
            )
            logger.debug("Stored summary in mem0")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store summary in mem0: {e}")
            return False
    
    def search(self, query: str, top_k: int = 5, 
               filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search memories by semantic similarity.
        
        Args:
            query: Search query
            top_k: Number of results to return
            filter_type: Optional filter by memory type (conversation, entity, summary)
            
        Returns:
            List of memory results with content and metadata
        """
        if not self.is_available():
            return []
        
        try:
            results = self.memory.search(query, user_id=self.user_id, limit=top_k)
            
            memories = []
            for result in results.get("results", []):
                memory_item = {
                    "id": result.get("id"),
                    "memory": result.get("memory"),
                    "score": result.get("score", 0),
                    "metadata": result.get("metadata", {}),
                }
                
                if filter_type:
                    item_type = memory_item.get("metadata", {}).get("type")
                    if item_type != filter_type:
                        continue
                
                memories.append(memory_item)
            
            return memories
            
        except Exception as e:
            logger.error(f"Failed to search mem0: {e}")
            return []
    
    def get_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all memories for the current user.
        
        Args:
            limit: Maximum number of memories to return
            
        Returns:
            List of all memory items
        """
        if not self.is_available():
            return []
        
        try:
            results = self.memory.get_all(user_id=self.user_id, limit=limit)
            
            memories = []
            for result in results.get("results", []):
                memories.append({
                    "id": result.get("id"),
                    "memory": result.get("memory"),
                    "metadata": result.get("metadata", {}),
                })
            
            return memories
            
        except Exception as e:
            logger.error(f"Failed to get all memories from mem0: {e}")
            return []
    
    def get_relevant_context(self, query: str, top_k: int = 5) -> str:
        """
        Get relevant memory context formatted for LLM prompt injection.
        
        Args:
            query: The current query/context to search for
            top_k: Number of relevant memories to retrieve
            
        Returns:
            Formatted string of relevant memories for prompt injection
        """
        if not self.is_available():
            return ""
        
        memories = self.search(query, top_k=top_k)
        
        if not memories:
            return ""
        
        context_parts = ["[Relevant Memories from Previous Sessions]"]
        for i, mem in enumerate(memories, 1):
            memory_text = mem.get("memory", "")
            mem_type = mem.get("metadata", {}).get("type", "unknown")
            context_parts.append(f"{i}. [{mem_type}] {memory_text}")
        
        return "\n".join(context_parts)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get memory statistics.
        
        Returns:
            Dictionary with memory stats
        """
        if not self.is_available():
            return {
                "enabled": False,
                "initialized": False,
                "total_memories": 0,
            }
        
        try:
            all_memories = self.get_all(limit=1000)
            
            type_counts = {}
            for mem in all_memories:
                mem_type = mem.get("metadata", {}).get("type", "unknown")
                type_counts[mem_type] = type_counts.get(mem_type, 0) + 1
            
            return {
                "enabled": True,
                "initialized": True,
                "user_id": self.user_id,
                "total_memories": len(all_memories),
                "by_type": type_counts,
            }
            
        except Exception as e:
            logger.error(f"Failed to get mem0 stats: {e}")
            return {
                "enabled": True,
                "initialized": True,
                "total_memories": 0,
                "error": str(e),
            }
    
    def clear(self) -> bool:
        """
        Clear all memories for the current user.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            self.memory.delete_all(user_id=self.user_id)
            logger.info(f"Cleared all mem0 memories for user: {self.user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear mem0 memories: {e}")
            return False


_mem0_instance: Optional[Mem0MemoryStore] = None


def get_mem0_store(user_id: Optional[str] = None) -> Mem0MemoryStore:
    """
    Get or create the global Mem0MemoryStore instance.
    
    Args:
        user_id: Optional user ID override
        
    Returns:
        Mem0MemoryStore instance
    """
    global _mem0_instance
    
    if _mem0_instance is None:
        _mem0_instance = Mem0MemoryStore(user_id=user_id)
    
    return _mem0_instance


def is_mem0_enabled() -> bool:
    """Check if mem0 is enabled in configuration."""
    return MEM0_CONFIG.get("enabled", False)
