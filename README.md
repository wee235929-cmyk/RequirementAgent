# Requirements Analysis Agent Assistant (RAAA)

面向需求工程（Requirements Engineering）的智能助理：支持基于对话的需求生成与质量评估、基于文档的 RAG 问答、以及多智能体“深度调研”报告生成。

## 什么是需求工程（Requirements Engineering）
需求工程是软件工程中的关键环节，关注“系统应该做什么、为什么要做、边界在哪里、如何验证是否满足”。典型工作包括：

- **需求获取（Elicitation）**：从业务方、用户、文档与现有系统中提取需求与约束
- **需求分析（Analysis）**：澄清范围、识别冲突与风险、建立一致的需求模型
- **需求规约（Specification）**：形成可交付的需求文档（如 SRS），确保可追踪、可验证
- **需求验证与确认（Validation & Verification）**：检查完整性、一致性、可测试性、无歧义
- **需求管理（Management）**：变更控制、版本管理、需求追踪与影响分析

本项目聚焦于用 LLM + RAG + Workflow（LangGraph）降低需求工程的“信息收集成本”和“规约产出成本”，并提升需求质量。

## 项目目的
- **提升需求产出效率**：通过对话驱动生成结构化需求（参考 ISO 29148、IEEE-830）
- **增强可追踪性与可复用性**：将需求要点/实体存储到记忆与索引中，方便后续检索与问答
- **降低理解成本**：针对需求内容自动生成 Mermaid 图（时序/流程/类图/ER）
- **支持领域调研**：多智能体深度调研，生成结构化报告并导出 PDF

## 主要能力
- **对话式需求生成**：按角色（需求分析师/架构师/开发/测试）生成不同视角的输出
- **需求质量评估与迭代**：对生成结果打分并给出改进建议，必要时自动迭代优化
- **文档 RAG 问答**：上传 PDF/Word/Excel/PPT/TXT/图片等文档，构建向量索引后问答
- **GraphRAG（轻量图谱增强）**：从已索引文本中抽取实体与关系，生成 `graph_index.json`，用于检索增强
- **Deep Research**：Planner → Searcher → Writer 的工作流，输出研究报告并生成 PDF

## 项目架构概览
本项目以 React + FastAPI 为前后端，以 LangGraph 编排多种能力：

- **前端（UI 层）**：`frontend/`（React 18 + TypeScript + TailwindCSS）
  - 文档上传/索引、图谱构建、对话交互、SRS 导出、调研 PDF 下载等
- **后端（API 层）**：`api/`（FastAPI）
  - RESTful API + 流式响应，Session 管理
- **编排层（Orchestrator）**：`src/core/orchestrator.py`
  - 意图识别（intent detection）
  - 根据意图路由到：需求生成 / RAG 问答 / 深度调研 / 普通对话
- **需求生成模块**：`src/requirements/generator.py`
  - 生成 → 评估 →（可选）改写迭代
- **记忆模块**：`src/memory/conversation.py`
  - 对话摘要 + 关键实体存储（FAISS）
- **RAG/GraphRAG 模块**：`src/rag/indexer.py`, `src/rag/chain.py`, `src/rag/parser.py`
  - 文档解析与切分
  - 向量索引（FAISS）
  - 轻量图谱构建与图谱检索增强
- **图表工具**：`src/tools/chart.py`
  - 根据需求内容生成 Mermaid 图

### GraphRAG 说明（本项目实现）
本项目的 GraphRAG 支持两种存储后端：

- **Neo4j 图数据库**（推荐）：完整的图数据库功能，支持复杂图查询
- **JSON 文件存储**（默认）：轻量级存储，无需额外依赖

**核心功能**：
- **图谱构建入口**：`RAGIndexer.build_graph_index()`
- **图谱存储**：Neo4j 数据库 或 `rag_index/graph_index.json`
- **抽取方式**：调用 LLM 从文本抽取
  - `entities`: 实体列表（概念、技术、组织、需求要点等）
  - `relationships`: 三元组列表 `[(entity1, relation, entity2), ...]`
- **使用方式**：检索时先在图谱中做关键词/ID 匹配，生成图谱上下文补充到回答中

更详细的流程见：`docs/graph_construction.md`

## 目录结构
```text
RequirementAgent/
├── run.py                # 启动入口
├── api/                  # FastAPI 后端
│   ├── main.py
│   ├── session.py
│   └── routes/           # API 路由（chat, documents, research, srs, stats）
├── frontend/             # React 前端（TypeScript + TailwindCSS）
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── src/                  # 核心业务逻辑
│   ├── config.py
│   ├── core/             # Orchestrator（意图识别与路由）
│   ├── memory/           # 对话记忆与 Mem0 适配
│   ├── requirements/     # 需求生成与质量评估
│   ├── research/         # Deep Research 工作流
│   ├── rag/              # RAG/GraphRAG（索引、检索、解析、Neo4j）
│   ├── tools/            # Mermaid 图表工具
│   ├── integrations/     # LangFuse 等外部集成
│   └── utils/            # 日志、异常等工具
├── templates/            # Jinja2 prompt 模板
│   ├── roles/            # 角色提示词
│   ├── rag/              # RAG 相关提示词
│   ├── research/         # Deep Research 提示词
│   ├── requirements/     # 需求生成提示词
│   └── system/           # 系统提示词
├── docs/                 # 项目文档
├── tests/                # 测试
├── rag_index/            # RAG 索引输出（运行后生成）
├── faiss_index/          # FAISS 索引输出（运行后生成）
├── reports/              # 研究报告输出（运行后生成）
├── mem0_storage/         # Mem0 本地存储（运行后生成）
└── requirements.txt
```


## 环境与依赖
- Python 3.10+（建议）
- Node.js 18+（前端）
- 主要依赖见 `requirements.txt`
  - `fastapi`, `uvicorn`, `langchain`, `langgraph`, `faiss-cpu`
  - 可选：`docling`（更强的文档解析能力）

## 快速开始

### 1) 安装依赖
```bash
# Python 后端依赖
pip install -r requirements.txt

# 前端依赖
cd frontend
npm install
```

### 2) 配置环境变量
复制 `.env.example` 为 `.env` 并填写：

- `DEEPSEEK_API_KEY`：LLM API Key
- `DEEPSEEK_BASE_URL`：LLM Base URL

（可选）如果你启用 LangSmith Trace，还需要配置 `LANGCHAIN_TRACING_V2`、`LANGCHAIN_API_KEY`、`LANGCHAIN_PROJECT` 等。

### 2.1) 配置 Neo4j（可选，推荐）
如果你希望使用 Neo4j 图数据库存储知识图谱：

1. 下载并安装 [Neo4j Desktop](https://neo4j.com/download/)
2. 创建新的 DBMS 并启动
3. 在 `.env` 文件中添加：
```bash
NEO4J_URI=neo4j://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
NEO4J_ENABLED=true
```

如果不配置 Neo4j，系统将自动使用 JSON 文件存储图谱。

### 3) 启动应用

#### 开发模式（推荐）

需要两个终端：

**终端 1 - 启动后端 API：**
```bash
python run.py
```

**终端 2 - 启动前端开发服务器：**
```bash
cd frontend
npm run dev
```

然后访问：http://localhost:5173

#### 生产模式

先构建前端，再启动后端（会自动托管前端静态文件）：
```bash
cd frontend && npm run build && cd ..
python run.py
```

访问：http://localhost:8000

启动后可访问 http://localhost:8000/docs 查看 Swagger API 文档。

## 使用指南

### 文档索引（RAG）
- 在侧边栏上传文档（PDF/Word/PPT/Excel/TXT/图片/JSON）
- 点击“Index Documents”构建向量索引

### 构建/更新知识图谱（GraphRAG）
- 索引完成后，点击“Build Graph / Update Graph”
- 将生成（或更新）`rag_index/graph_index.json`

### 需求生成（SRS）
- 与系统对话提供上下文
- 在侧边栏选择角色并点击生成 SRS
- 可下载 Markdown 格式 SRS

### Deep Research（深度调研）
- 提出调研问题
- 系统会规划任务、搜索与写作
- 输出报告并生成 PDF（保存在 `reports/`）

### Mermaid 图生成
- 用户可以主动要求生成图（例如“画一个流程图”）
- 或者系统根据需求内容自动判断并生成图表

## 常见问题
- **首次运行会慢**：可能在下载 embedding 模型（`sentence-transformers/all-MiniLM-L6-v2`）
- **Docling 不可用**：如果未安装或环境不支持，会自动回退到基础解析器
- **Neo4j 连接失败**：检查 Neo4j 服务是否启动，以及 `.env` 中的连接信息是否正确；系统会自动回退到 JSON 存储

## 许可证
MIT License
