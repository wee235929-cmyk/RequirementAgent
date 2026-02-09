"""
Requirements Analysis Agent Assistant (RAAA) - 源码包

项目模块结构：
    - config: 集中配置
    - core: 核心编排逻辑
    - memory: 对话记忆管理
    - rag: 检索增强生成
    - research: 深度调研
    - requirements: 需求生成
    - tools: 工具模块
    - integrations: 外部服务集成
    - utils: 工具函数
"""
from . import config
from . import utils
from . import rag
from . import core
from . import memory
from . import research
from . import requirements
from . import tools
from . import integrations

