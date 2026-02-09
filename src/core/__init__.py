"""
Core Module - 核心模块

包含系统的核心编排逻辑和会话管理。

组件：
    - OrchestratorAgent: 主编排代理，负责意图识别和工作流路由
"""
from .orchestrator import OrchestratorAgent

__all__ = ["OrchestratorAgent"]
