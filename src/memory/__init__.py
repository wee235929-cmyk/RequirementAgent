"""
Memory Module - 记忆模块

提供对话记忆管理和持久化功能。

组件：
    - EnhancedConversationMemory: 增强对话记忆，支持 FAISS 向量索引
    - Mem0Memory: Mem0 适配器，用于跨会话持久化记忆
"""
from .conversation import EnhancedConversationMemory

__all__ = ["EnhancedConversationMemory"]

# 可选的 Mem0 集成
try:
    from .mem0_adapter import Mem0Memory
    __all__.append("Mem0Memory")
except ImportError:
    pass
