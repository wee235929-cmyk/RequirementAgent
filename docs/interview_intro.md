# 面试项目介绍：Requirements Analysis Agent Assistant（RAAA）

> 本文是面向面试的项目介绍稿，目标是帮你用“可讲述、可追问、可落地”的方式，讲清楚这个项目做什么、为什么这么设计、关键技术点在哪里、效果如何，以及面试官可能怎么追问。

## 1. 一句话介绍（30 秒版本）

RAAA 是一个面向需求工程（Requirements Engineering）的智能助理：以 Streamlit 作为交互入口，用 LangGraph 编排多条能力链路（需求生成/质量评估迭代、文档 RAG 问答、GraphRAG 关系增强、多智能体深度调研与 PDF 输出），把“需求调研—信息消化—结构化规约产出—质量把关”这条链路尽可能自动化。

## 2. 项目背景（可略虚构但自洽的故事线）

在中小团队/外包交付场景里，需求阶段经常遇到几个典型痛点：

- 需求信息来源分散：会议纪要、历史 PRD、竞品资料、行业规范、客户邮件、Excel 表格……信息检索成本很高。
- 需求产出不可控：不同人写出来的需求粒度不一致、缺少验收口径、非功能约束经常遗漏。
- 需求质量难量化：是否“清晰/完整/一致/可测试”往往靠经验，很难快速做出反馈闭环。
- 需求变更频繁：没有长期可检索的“需求资产”，新成员接手成本高。

因此我做了 RAAA：把 LLM 的语言能力与“可追溯检索（RAG/GraphRAG）+ 可编排工作流（LangGraph）+ 可持久化记忆”结合，用较低的工程复杂度快速搭出一套可用的需求工程助理原型，强调 **产物结构化、可解释、可扩展**，并尽可能让每条能力都能被面试官追问到具体实现。

## 3. 项目的总任务（你在面试里怎么定义问题）

项目总任务可以定义为：

- **输入**：用户的对话上下文 + 上传的领域文档（PDF/Word/Excel/PPT/图片/TXT 等）+ 可选的互联网信息
- **过程**：通过意图识别将请求路由到合适工作流（需求生成 / 文档问答 / 深度调研 / 混合意图串联），并通过记忆管理与检索增强减少幻觉
- **输出**：
  - 结构化的 SRS（参考 ISO 29148 / IEEE-830）
  - 需求质量评分与改进建议（并可自动迭代优化）
  - 文档问答答案 + 可展示的来源片段（sources）
  - GraphRAG 命中的实体/关系上下文（辅助解释“为什么这么回答”）
  - 深度调研报告 + PDF 文件落盘

## 4. 架构设计（从“入口—编排—能力—存储”讲清楚）

### 4.1 分层结构

- **UI 层（Streamlit）**：`app.py`
  - 上传文件、触发索引构建/图谱构建、聊天交互、导出 SRS、下载研究报告 PDF。

- **编排层（LangGraph Orchestrator）**：`src/agents/orchestrator.py`
  - 通过 LLM 做意图识别（支持单意图与混合意图）
  - 将请求路由到对应节点：
    - `requirements_generation`
    - `rag_qa`
    - `deep_research`
    - `general_chat`
    - `mixed_intent_orchestrator`（将多个能力串起来）

- **能力模块层（Modules）**：
  - **需求生成与质量闭环**：`src/modules/requirements_generator.py`
    - 生成（结构化 JSON）→ 质量评估（四维度打分）→ 低于阈值自动迭代优化。
  - **记忆模块（对话摘要 + 需求实体库）**：`src/modules/memory.py`
    - 对话超过阈值后自动摘要压缩；把 FR/NFR/BR 等需求条目存到 FAISS 形成“长期实体记忆”。
  - **Deep Research 工作流**：`src/modules/research/workflow.py` + `agents.py` + `pdf_generator.py`
    - Planner → Searcher（Web search + synthesis）→ Writer → PDF。

- **检索与知识库层（RAG/GraphRAG）**：
  - 文档解析：`src/rag/parser.py`（Docling 优先，失败则 fallback loaders）
  - 索引与持久化：`src/rag/indexer.py`（FAISS + documents.json + metadata.json）
  - 检索/生成链：`src/rag/chain.py`（Query 重写 + Hybrid 检索 + LLM 排序 + 条件 websearch）
  - 图谱存储：`src/rag/neo4j_store.py`（可选 Neo4j）或 `rag_index/graph_index.json`

### 4.2 数据流（你可以用“从用户输入到输出”来讲）

1. 用户在 `app.py` 输入问题/需求或上传文档。
2. `OrchestratorAgent` 读取 `EnhancedConversationMemory` 的摘要作为 `conversation_history`。
3. 用 `SYSTEM_PROMPTS["mixed_intent_detection"]` 做意图识别：
   - 单意图：直接路由到某个节点
   - 混合意图：例如 `rag_qa+deep_research+requirements_generation`，按顺序执行，并把中间结果拼成下游上下文。
4. RAG 侧：如果命中文档问答，会走 `AgenticRAGChain.invoke()`：
   - Query 重写（提升召回）
   - 向量检索 + 关键词检索（解决语义匹配与编号/ID 精确命中）
   - GraphRAG（按“是否值得用图”的 agent 决策触发）
   - 文档结果过多时用 LLM 做相关性排序
   - 本地完全无结果时才考虑 Web Search（并有严格评估提示词约束）
5. 需求生成侧：用结构化输出（Pydantic schema + JsonOutputParser）确保产物可控；并用质量评分驱动迭代优化。
6. Deep Research 侧：Planner 将大问题拆成可搜索任务，Searcher 搜索并二次综合，Writer 写结构化报告，最后由 reportlab 生成 PDF。

## 5. 技术要点（面试最值得讲的“可追问点”）

### 5.1 LangGraph 做编排：把“智能”变成“可控流程”

- 不是把所有能力塞进一个 prompt，而是把系统拆成多个节点（intent → node），每个节点有清晰的输入输出。
- 支持 **mixed intent**：把“先查文档再生成需求 / 先研究再写需求”这类真实工作流串起来。
- 面试表达要点：你解决的是“多能力共存时的路由与可维护性”，而不是单次问答。

### 5.2 RAG 的工程化：解析、切分、持久化、去重、可解释

- **解析策略**：`DocumentParser` 优先 Docling（支持 PDF/Office/图片），失败回退到基础解析器（pypdf/python-docx/openpyxl/python-pptx）。
- **表格可召回性增强**：Docling 模式会把表格转成可搜索文本拼接到正文（`--- TABLE DATA ---`），减少“表格信息检索不到”的问题。
- **索引持久化**：
  - 向量库：`rag_index/faiss_index/`
  - 文档块：`rag_index/documents.json`（支撑 keyword_search）
  - 元数据：`rag_index/metadata.json`（文件去重与统计）
- **增量索引 + 去重**：按 `filename + file_size` 去重，避免重复构建。
- **可解释输出**：回答时返回 sources（文件名、chunk、preview），方便面试官追问“你怎么降低幻觉”。

### 5.3 Hybrid Retrieval：向量 + 关键词（解决“语义 vs 精确符号”）

- 向量检索擅长语义相似，但对 `REQ-001`、`INT-004` 这类符号/编号不敏感。
- keyword_search 对 ID 命中加权（+10），补齐向量检索的短板。
- 同时保留对原始 query 的兜底检索，降低 query 重写失真带来的漏召回。

### 5.4 GraphRAG：轻量图谱增强 + 可选 Neo4j

- 图谱构建：`RAGIndexer.build_graph_index()` 用 LLM 从文本抽取 `entities` 和 `relationships`。
- 存储后端：
  - 默认 JSON（`rag_index/graph_index.json`）适合快速原型
  - 可选 Neo4j（更强查询/可视化/扩展性）
- 在本项目中 GraphRAG 的定位是 **“回答上下文增强”**，而不是替代文档 chunk 检索：
  - 图谱提供关联实体/关系，帮助回答“X 和 Y 的关系/依赖”类问题更完整。

### 5.5 需求生成的“结构化 + 质量闭环”（这是面试亮点）

- 用 Pydantic schema 约束输出：功能/非功能/业务规则/用例/假设等，避免自由文本失控。
- 引入质量评估链：从 ambiguity/completeness/consistency/clarity 四维打分。
- 设置阈值（默认 7.0）触发自动 refinement（默认最多 2 次），形成闭环。
- 产物格式：提供 `to_markdown()`，自动生成带 FR/NFR/BR 编号的 SRS。

### 5.6 记忆管理：短期摘要 + 长期实体 FAISS

- 短期：messages 超过阈值后，把旧消息摘要压缩（保留最近 5 条细节）。
- 长期：把生成的 FR/NFR/BR 作为实体写入 `faiss_index/`，形成可复用资产。
- 面试表达要点：你不是“把历史对话全塞进上下文”，而是做了 **可控的压缩与持久化**。

### 5.7 Deep Research：可复用的 Planner/Searcher/Writer 工作流

- Planner 输出 JSON 任务列表（含 priority），并对模型输出做容错解析。
- Searcher 不是直接把搜索结果塞给 Writer，而是先做一次 synthesis，降低噪声。
- Writer 输出结构化报告，PDF 生成用 reportlab 落盘到 `reports/`。

## 6. 最终解决了什么问题、取得了什么效果（可量化但保持可信）

你可以用“内部试用 + 小规模对比”的口径来描述（适当虚构，但逻辑自洽）：

- **需求产出效率**：把“从零到一的初稿”从原先 0.5～1 天缩短到 30～60 分钟；并且能自动生成编号化条目，减少后续整理成本。
- **需求质量可控**：用质量评分让产出可衡量，低分自动迭代；在试用样例中，整体评分从 ~6.x 提升到 ~7.x～8.x。
- **知识检索成本下降**：上传领域资料后，可通过 RAG 快速定位出处；对 ID/编号类查询，hybrid 检索显著减少漏召回。
- **可追溯性增强**：回答附带来源 chunk，能在评审会议中直接定位“依据来自哪份文档”。
- **调研交付物自动化**：Deep Research 可以把“竞品/标准/最佳实践”调研变成结构化报告并导出 PDF，提高交付速度。

## 7. 你在面试里如何讲“我的贡献”

建议按“设计—实现—取舍—效果”结构讲，重点落在工程化与可控性：

- 我把需求工程常见流程拆成了可编排的工作流，并实现了 intent routing + mixed intent 串联。
- 我把 RAG 做成“可落盘可复用”的索引体系，并做了 hybrid 检索与来源展示，降低幻觉风险。
- 我用结构化输出 + 质量评分 + 自动迭代的方式，让需求生成具备闭环而不是一次性生成。
- 我为调研做了 Planner/Searcher/Writer 三段式工作流，并支持 PDF 产物输出。

## 8. 面试官高频问题清单（含参考回答）

### Q1：为什么用 LangGraph，而不是纯 LangChain Chain？

**答法要点**：

- 我需要的是“多能力路由 + 状态机/工作流”，LangGraph 天生适合表示节点与条件边。
- mixed intent（多步执行）在 LangGraph 下实现更清晰，可维护性更好。
- 每个节点职责单一，方便测试与扩展（比如新增一个“需求变更影响分析”节点）。

### Q2：你怎么做意图识别？会不会误判？

**答法要点**：

- 用 LLM + 明确的分类 prompt（`SYSTEM_PROMPTS["mixed_intent_detection"]`）。
- 输出被强约束为固定枚举；并对 mixed intent 做二次校验（确保每个 intent 都在白名单）。
- 误判处理：默认回退 general_chat；同时 UI 层可让用户用更明确指令触发。

### Q3：RAG 为什么要做“向量 + 关键词”？

**答法要点**：

- 需求工程场景非常依赖编号/条款/接口名等“精确 token”，纯向量容易漏掉。
- keyword_search 对 ID 命中加权，解决“REQ-001 查不到”的典型问题。
- 两路结果合并后再去重、再排序，保证最终上下文更相关。

### Q4：如何降低幻觉？

**答法要点**：

- 先保证“回答必须基于检索上下文”，并把 sources 返回给用户。
- 本地检索为空才会触发 websearch，而且还要经过评估 prompt（默认 SUFFICIENT），避免随意联网导致引入噪声。
- 对话历史用摘要压缩，减少上下文污染。

### Q5：GraphRAG 解决的是什么问题？为什么不是直接上知识图谱就完了？

**答法要点**：

- 图谱适合回答关系/依赖/追踪类问题，但生成与维护成本更高。
- 我把 GraphRAG 定位为“增强上下文”，不是替代 chunk 检索：
  - 文档 chunk 提供事实依据
  - 图谱提供关联结构，让回答更完整、更像需求分析师的思路
- 同时支持 Neo4j 与 JSON，兼顾工程化与易用性。

### Q6：需求生成为什么要结构化输出？

**答法要点**：

- 面试强调：结构化输出让产物可以直接进入后续工程流程（导出 SRS、生成测试点、追踪变更）。
- 用 Pydantic schema + JsonOutputParser，输出稳定，便于后续处理（比如实体入库、自动编号、对比版本差异）。

### Q7：质量评分与迭代怎么保证有效？会不会越改越差？

**答法要点**：

- 评分维度是需求工程常见质量属性（歧义/完整/一致/清晰）。
- 只有低于阈值才触发迭代，且迭代次数有限（默认 2 次），避免无穷循环与成本不可控。
- 如果评估链失败会 fallback，保证系统可用性。

### Q8：Deep Research 为什么要 Planner/Searcher/Writer 三段？

**答法要点**：

- 大问题直接搜会失焦；Planner 把问题拆成可搜索任务，让搜索更可控。
- Searcher 先把搜索结果做 synthesis，降低噪声并形成可读要点。
- Writer 再把多个 findings 组织成结构化报告，最终可以产出 PDF 给业务方。

### Q9：你做了哪些工程取舍？

**答法要点**（挑你最想讲的 2～3 个）：

- Graph 抽取做了采样与截断（控制 token/成本），并支持增量更新。
- Web search 触发条件做得很苛刻，优先保证“基于本地知识库”回答。
- Mermaid 图生成默认关闭自动触发，只在用户显式要求时生成，避免“看起来炫但影响主流程”。

### Q10：如果继续迭代，你会加什么？

**答法要点**：

- 把长期实体记忆（FAISS）真正接入到回答/需求生成 prompt（当前已经存了实体，但未自动注入到 RAG/生成链中）。
- 加入更严格的引用与可追溯（让 Writer 在 References 里强制输出 URL 列表）。
- 引入评测集与自动化评测（RAG 命中率、需求质量分布、用户满意度）。

## 9. 建议你在面试现场的讲述顺序（推荐）

1. 痛点与场景（需求工程信息碎片化 + 产物质量不可控）
2. 总体方案（Streamlit + LangGraph + RAG/GraphRAG + 记忆 + DeepResearch）
3. 选一个深挖点讲透（建议：Hybrid RAG 或 需求生成闭环）
4. 讲工程取舍（成本控制/可解释/可持久化）
5. 讲效果与复盘（效率提升 + 可追溯）

---

*文件位置：`docs/interview_intro.md`*
