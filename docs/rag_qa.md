# RAG Q&A Flow Report

本文档说明本项目从用户输入 `query` 到 Agent 生成最终回答的 **RAG（Retrieval-Augmented Generation）问答流程**，包含关键模块、数据流转、检索策略以及可选的 GraphRAG / Web Search 介入条件。

> 主要代码位置：
>
>- API 入口：`api/routes/chat.py`, `api/routes/documents.py`
>- 编排与意图路由：`src/core/orchestrator.py`
>- RAG Chain：`src/rag/chain.py`
>- 索引与检索：`src/rag/indexer.py`
>- 文档解析：`src/rag/parser.py`
>- Prompt 配置：`src/config.py`（`SYSTEM_PROMPTS`）

---

## 1. 总览：从输入到回答的主链路

RAG Q&A 的整体调用链路可以概括为：

1. **用户在 Streamlit 聊天框输入问题**
2. **Orchestrator 进行意图识别**（判断是 `rag_qa` 还是其它能力）
3. **进入 RAG Q&A 节点**（`OrchestratorAgent._rag_qa_node`）
4. **调用 `AgenticRAGChain.invoke` 进行检索与生成**
5. **组装最终回答**：回答文本 + 文档来源 +（可选）图谱实体 +（可选）Web 来源
6. **写入对话记忆**：用于后续上下文与 query 重写

---

## 2. 入口与触发：UI 如何把 query 交给 Agent

### 2.1 用户输入
在 `app.py` 的 `render_chat_interface()` 中，用户通过 `st.chat_input()` 输入文本。

随后 `process_user_message(prompt)` 会：

- 判断当前是否上传文件
- 调用 `st.session_state.orchestrator.detect_intent(...)` 做意图识别
- 根据意图路由到不同处理函数

### 2.2 意图识别（决定是否走 RAG）
`OrchestratorAgent.detect_intent()` 使用 LLM + `SYSTEM_PROMPTS["intent_detection"]` 分类：

- `requirements_generation`
- `rag_qa`
- `deep_research`
- `general_chat`

当判断为 `rag_qa` 时，编排流程会走到 `OrchestratorAgent._rag_qa_node()`。

---

## 3. Orchestrator 的 RAG Q&A 节点做了什么

代码位置：`src/core/orchestrator.py` → `OrchestratorAgent._rag_qa_node()`

该节点主要职责：

- **检查索引是否可用**：
  - 调用 `self.rag_indexer.get_index_stats()`
  - 如果没有向量索引（`has_vectorstore=False`）或没有已索引文件，直接返回提示
- **准备上下文**：
  - 从 `state["conversation_history"]` 取出对话历史摘要（来自 memory）
- **调用 RAG Chain**：
  - `self.rag_chain.invoke(query=..., history=..., use_rewriting=True, use_graph=True, use_websearch=True)`
- **拼装展示层输出**：
  - 将 `answer` 作为主体
  - 将 `sources`（最多 3 条）展示为引用
  - 将 `graph_entities`（最多 5 个）展示为相关实体
  - 如触发 Web Search 则展示 Web 来源
- **写入 memory**：
  - `self.memory.add_message(user_input, "user")`
  - `self.memory.add_message(answer, "assistant")`

注意：RAG 的“检索 + 生成”核心逻辑完全在 `src/rag/chain.py` 中实现。

---

## 4. RAG Chain：`AgenticRAGChain.invoke` 的核心流程

代码位置：`src/rag/chain.py` → `AgenticRAGChain.invoke()`

### 4.1 前置条件：必须存在向量索引
如果 `self.indexer.vectorstore` 不存在，则返回：

- `status = "no_index"`
- `answer = "No documents have been indexed..."`

该逻辑保证问答必须在“已索引文档”的前提下进行。

### 4.2 Query 重写（可选，默认开启）
当 `use_rewriting=True` 时：

1. 调用 `rewrite_query(query, history)`
2. 使用 LLM 将 query 改写为“更利于检索”的版本（强调关键术语、ID、同义词等）
3. `result["query_rewritten"]` 会标注是否发生改写
4. `result["rewritten_query"]` 会返回改写后的 query

目的：提升召回，尤其是包含编号（如 `REQ-001`/`INT-004`）或缩写时。

### 4.3 多路检索（Hybrid Retrieval）：图谱 / 向量 / 关键词
在 `invoke` 中会收集 `all_docs`，并记录 `methods_used`。

#### 4.3.1 GraphRAG 检索（可选）
当 `use_graph=True` 且 `self.indexer.graphrag_available=True`：

- 调用 `self.indexer.graph_search(search_query)`
- 返回：
  - `graph_context`：文本化的实体与关系描述
  - `graph_entities`：命中的实体列表
  - `found`：是否命中

这里的 GraphRAG 是“轻量增强”：主要为回答阶段提供额外上下文，并不会直接返回文档 chunk。

#### 4.3.2 向量检索（Vector Similarity Search）
- 调用 `self.indexer.similarity_search(search_query, k=8)`
- 底层使用 FAISS（`langchain_community.vectorstores.FAISS`）
- 返回 `Document` 列表（每个是一个 chunk）

#### 4.3.3 关键词检索（Keyword Search）
- 调用 `self.indexer.keyword_search(search_query, k=8)`
- 机制：
  - 对 query 做分词（按空格）
  - 对 chunk 做 substring 匹配
  - 对类似 `ABC-123` 的 ID（正则）做加权命中

该策略用于补齐向量检索对“精确符号/编号”不敏感的问题。

#### 4.3.4 去重策略
`invoke()` 会对每个 doc 计算 `hash(doc.page_content[:200])`，避免重复 chunk。

#### 4.3.5 原始 query 兜底
当 query 被重写且 `search_query != query` 时，还会额外对 **原始 query** 做：

- 向量检索 `k=5`
- 关键词检索 `k=5`

用于降低“重写失真”带来的漏召回。

### 4.4 结果排序（可选）
当 `len(all_docs) > 3`：

- 调用 `rank_documents(query, all_docs)`
- 使用 LLM 对 doc preview 做相关性排序
- 输出 doc 的索引顺序（如 `2,0,3,1`）

这一步解决“多路检索合并后结果乱序”的问题。

### 4.5 组装回答上下文（Prompt Inputs）
最终取 `docs = all_docs[:10]`，并构造：

- `doc_context`
  - 格式：`[Source: filename]\nchunk_content`
- `graph_context`
  - 来自 GraphRAG 的文本化上下文
- `web_context`
  - 默认为空（除非触发 Web Search）
- `history`
  - 来自 Orchestrator 的对话摘要

这些会被注入到 `SYSTEM_PROMPTS["rag_answer"]` 中。

### 4.6 Web Search（可选，且触发条件非常苛刻）
当前实现的触发条件是：

- `use_websearch=True`
- `self.web_search_available=True`
- **并且 `not docs`（即本地检索一个 doc 都没有）**

满足后才会调用 `evaluate_rag_result(query, rag_preview)`。

评估 Prompt（`SYSTEM_PROMPTS["rag_evaluation"]`）约束：

- 只有当 RAG 结果完全无关 / 查询实时数据 / 明确要求外部信息 时，才返回 `NEEDS_WEBSEARCH: <query>`
- 否则返回 `SUFFICIENT`

若确实需要 Web Search：

- 使用 DuckDuckGo (`ddgs`) 查询
- 将结果拼成 `web_context`
- 并把 `web_sources` 返回给上层展示

### 4.7 最终回答生成
最后调用：

- `chain = self.answer_prompt | self.llm`
- `chain.invoke({query, doc_context, graph_context, web_context, history})`

并返回：

- `answer`: LLM 输出
- `sources`: chunk 来源（filename、chunk_index、preview）
- `graph_entities`, `graph_context`
- `web_sources`（如果触发）
- `search_methods`：graph/vector/keyword

---

## 5. 索引侧补充：RAG 的数据从哪里来（文档 → chunk → 向量库）

虽然本文件重点是问答链路，但为了理解“检索到的 docs 是如何产生的”，需要补充索引流程。

### 5.1 文档上传与索引入口
`app.py` 的侧边栏：

- 上传文件后点击 `Index Documents`
- 调用 `index_documents(files)`
- 最终执行 `rag_indexer.index_documents(file_paths)`

### 5.2 文档解析（DocumentParser）
`src/rag/parser.py`：

- 优先尝试 Docling（支持 PDF/Word/PPT/Excel/图片等）
- 失败则 fallback：
  - PDF：`pypdf`
  - Word：`python-docx`
  - Excel：`openpyxl`
  - PPT：`python-pptx`
  - TXT：直接读取

Docling 模式会把表格按“可搜索文本”方式拼到正文中（`--- TABLE DATA ---`），提升表格问答的可召回性。

### 5.3 切分与向量化
`src/rag/indexer.py`：

- 使用 `RecursiveCharacterTextSplitter` 切分：
  - `chunk_size = RAG_CONFIG["chunk_size"]`（默认 1000）
  - `chunk_overlap = RAG_CONFIG["chunk_overlap"]`（默认 200）
- 每个 chunk 都包装成 `Document(page_content=chunk, metadata=...)`
- 向量化：`FAISSVectorStore.from_documents(new_documents, embeddings)`
- 增量合并：`self.vectorstore.merge_from(new_vectorstore)`

---

## 6. 关键设计点与注意事项

- **RAG 的前提是索引存在**：未索引任何文档会直接返回提示。
- **Hybrid 检索**：向量 + 关键词，解决“语义匹配”和“精确符号/ID 匹配”两类需求。
- **GraphRAG 是增强上下文，而非替代文档检索**：它的输出用于丰富回答内容与关联关系展示。
- **Web Search 默认几乎不会触发**：只有在本地检索完全为空时才进入评估与搜索逻辑。
- **去重策略基于 chunk 的前 200 字符 hash**：简洁但可能存在哈希碰撞或相似 chunk 误判为重复的极小概率。

---

## 7. 相关文件索引
- `app.py`
- `src/agents/orchestrator.py`
- `src/rag/chain.py`
- `src/rag/indexer.py`
- `src/rag/parser.py`
- `src/config.py`
