# 项目结构说明

本文档描述 RAAA (Requirements Analysis Agent Assistant) 项目的模块化结构。

## 目录结构

```
RequirementAgent/
├── api/                          # FastAPI 后端 API
│   ├── __init__.py
│   ├── main.py                   # FastAPI 应用入口
│   ├── session.py                # 会话管理
│   └── routes/                   # API 路由
│       ├── chat.py               # 对话接口
│       ├── documents.py          # 文档管理接口
│       ├── research.py           # 深度调研接口
│       ├── srs.py                # SRS 生成接口
│       └── stats.py              # 统计信息接口
│
├── src/                          # 核心源码
│   ├── __init__.py
│   ├── config.py                 # 集中配置（LLM、RAG、Prompts等）
│   │
│   ├── core/                     # 核心编排模块
│   │   ├── __init__.py
│   │   └── orchestrator.py       # 主编排代理（意图识别、工作流路由）
│   │
│   ├── memory/                   # 记忆管理模块
│   │   ├── __init__.py
│   │   ├── conversation.py       # 对话记忆（FAISS 向量索引）
│   │   └── mem0_adapter.py       # Mem0 适配器（跨会话持久化）
│   │
│   ├── rag/                      # RAG 检索增强生成模块
│   │   ├── __init__.py
│   │   ├── chain.py              # 智能 RAG 链（查询重写、混合检索）
│   │   ├── indexer.py            # 文档索引器（FAISS + 图索引）
│   │   ├── parser.py             # 文档解析器
│   │   └── neo4j_store.py        # Neo4j 图存储
│   │
│   ├── research/                 # 深度调研模块
│   │   ├── __init__.py
│   │   ├── workflow.py           # LangGraph 工作流
│   │   ├── agents.py             # Planner/Searcher/Writer 代理
│   │   └── report_generator.py   # PDF/Word 报告生成器
│   │
│   ├── requirements/             # 需求生成模块
│   │   ├── __init__.py
│   │   ├── generator.py          # 需求文档生成器
│   │   └── roles.py              # 用户角色管理
│   │
│   ├── tools/                    # 工具模块
│   │   ├── __init__.py
│   │   └── chart.py              # Mermaid 图表工具
│   │
│   ├── integrations/             # 外部服务集成
│   │   ├── __init__.py
│   │   └── langfuse/             # LangFuse 追踪集成
│   │       ├── __init__.py
│   │       ├── config.py
│   │       └── handler.py
│   │
│   └── utils/                    # 工具函数
│       ├── __init__.py
│       ├── exceptions.py         # 自定义异常
│       └── logging_config.py     # 日志配置
│
├── frontend/                     # React 前端
│   ├── src/
│   ├── package.json
│   └── ...
│
├── templates/                    # Jinja2 模板与配置
│   ├── __init__.py               # 模板模块入口
│   ├── template_loader.py        # 模板加载器（支持 Jinja2 和 YAML）
│   ├── settings.yaml             # 集中参数配置（LLM/RAG/深度调研等）
│   ├── roles/                    # 角色提示词模板
│   │   ├── requirements_analyst.j2
│   │   ├── software_architect.j2
│   │   ├── software_developer.j2
│   │   └── test_engineer.j2
│   ├── system/                   # 系统提示词模板
│   │   ├── intent_detection.j2
│   │   ├── mixed_intent_detection.j2
│   │   ├── general_chat.j2
│   │   ├── rag_evaluation.j2
│   │   ├── rag_answer.j2
│   │   └── query_restatement.j2
│   ├── research/                 # 调研提示词模板
│   │   ├── planner.j2
│   │   ├── synthesizer.j2
│   │   └── report_writer.j2
│   └── rag/                      # RAG 提示词模板
│
├── docs/                         # 项目文档
│   ├── DeepResearch.md           # 深度调研功能说明
│   ├── rag_qa.md                 # RAG 问答流程说明
│   ├── memory_management.md      # 记忆管理说明
│   ├── graph_construction.md     # 知识图谱构建说明
│   ├── mermaid_diagram_pipeline.md # Mermaid 图表构建流程
│   ├── frontend.md               # 前端架构说明
│   ├── interview_intro.md        # 面试项目介绍
│   ├── resume.md                 # 简历项目描述
│   └── project_structure.md      # 项目结构说明（本文档）
│
├── reports/                      # 生成的报告输出目录
├── rag_index/                    # RAG 索引存储目录
├── faiss_index/                  # FAISS 索引存储目录
│
├── run.py                        # 应用启动脚本
├── requirements.txt              # Python 依赖
└── .env                          # 环境变量配置
```

## 模块职责

### 1. `src/core/` - 核心编排
- **职责**：系统的中央控制器，负责意图识别和工作流路由
- **主要类**：`OrchestratorAgent`
- **依赖**：memory, rag, research, requirements, tools

### 2. `src/memory/` - 记忆管理
- **职责**：管理对话历史、实体记忆和跨会话持久化
- **主要类**：`EnhancedConversationMemory`, `Mem0Memory`
- **依赖**：config

### 3. `src/rag/` - 检索增强生成
- **职责**：文档解析、索引、检索和问答
- **主要类**：`RAGIndexer`, `AgenticRAGChain`, `DocumentParser`
- **依赖**：config, integrations.langfuse

### 4. `src/research/` - 深度调研
- **职责**：自动化深度调研，生成研究报告
- **主要类**：`DeepResearchWorkflow`, `PlannerAgent`, `SearcherAgent`, `WriterAgent`
- **依赖**：config, integrations.langfuse

### 5. `src/requirements/` - 需求生成
- **职责**：根据用户角色生成需求文档
- **主要类**：`RequirementsGenerator`
- **依赖**：config, templates

### 9. `templates/` - 模板与配置
- **职责**：集中管理提示词模板和可调参数
- **主要文件**：`template_loader.py`, `settings.yaml`
- **子目录**：`roles/`, `system/`, `research/`, `rag/`

### 6. `src/integrations/` - 外部集成
- **职责**：与外部服务（如 LangFuse）的集成
- **子模块**：`langfuse`

### 7. `src/tools/` - 工具
- **职责**：提供辅助工具（如图表生成）
- **主要类**：`MermaidChartTool`

### 8. `src/utils/` - 工具函数
- **职责**：通用工具函数和异常定义
- **主要函数**：`get_logger`

## 设计原则

### 高内聚
- 每个模块只负责一个明确的功能领域
- 相关的类和函数放在同一模块中

### 低耦合
- 模块间通过清晰的接口交互
- 使用依赖注入而非硬编码依赖
- 配置集中在 `config.py`

### 命名规范
- 目录名：小写下划线（snake_case）
- 文件名：小写下划线（snake_case）
- 类名：大驼峰（PascalCase）
- 函数名：小写下划线（snake_case）

## 导入示例

```python
# 从核心模块导入
from src.core import OrchestratorAgent

# 从记忆模块导入
from src.memory import EnhancedConversationMemory

# 从 RAG 模块导入
from src.rag import RAGIndexer, AgenticRAGChain, create_rag_system

# 从研究模块导入
from src.research import DeepResearchWorkflow, create_deep_research_workflow

# 从需求模块导入
from src.requirements import select_role_prompt, get_available_roles

# 从集成模块导入
from src.integrations.langfuse import get_langfuse_handler, is_langfuse_enabled
```
