"""
Requirements Module - 需求生成模块

提供需求文档生成和角色管理功能。

组件：
    - RequirementsGenerator: 需求文档生成器
    - select_role_prompt: 角色提示词选择器
    - get_available_roles: 获取可用角色列表
"""
from .roles import select_role_prompt, get_available_roles

__all__ = [
    "select_role_prompt",
    "get_available_roles",
]

# 可选的需求生成器
try:
    from .generator import RequirementsGenerator
    __all__.append("RequirementsGenerator")
except ImportError:
    pass
