# Memory Management Report

本文档说明本项目如何管理“记忆”（Memory），以及是否存在长期/短期记忆的区分。这里的“记忆”主要分为两条线：

- **Agent 对话记忆（Conversation Memory）**：用于保留会话上下文、摘要、以及从需求输出中抽取的实体（更接近“Agent 的记忆”）
- **RAG 检索记忆（RAG Index / Knowledge Store）**：用于对上传文档形成可检索的向量索引、可关键词检索的 chunk 列表，以及（可选）GraphRAG 图谱（更接近“知识库/外部记忆”）

---

## 1. 结论先行：是否区分长期记忆与短期记忆？

本项目**存在“短期记忆 vs 长期记忆”的事实区分**，但它不是通过一个统一的接口显式标注的，而是体现在“存储介质与生命周期”上：

- **短期记忆（Short-term / Working Memory）**
  - 主要是运行时内存里的对话消息列表：`EnhancedConversationMemory.messages`
  - 特点：随会话推进不断增长，但会触发摘要压缩；不落盘（重启后丢失）

- **长期记忆（Long-term / Persistent Memory）**
  - 主要是：
    - 对话摘要文本：`EnhancedConversationMemory.summary`（在当前实现中也主要驻留内存；是否落盘取决于你是否扩展）
    - **实体向量库**：`faiss_index/index.faiss` + `faiss_index/metadata.pkl`（落盘，重启可恢复）
    - **RAG 文档索引**：`rag_index/faiss_index/` + `rag_index/metadata.json` + `rag_index/documents.json`（落盘，重启可恢复）
    - **GraphRAG 图谱**：`rag_index/graph_index.json`（落盘，重启可恢复）

因此：

- Agent 的“短期记忆”更多表现为**最近对话上下文**。
- Agent 的“长期记忆”更多表现为**落盘的实体库（FAISS）**。
- RAG 的“长期记忆”是**整个可检索知识库**（向量库/文档块/图谱）。

---

## 2. Agent 侧记忆：EnhancedConversationMemory

代码位置：`src/modules/memory.py`

### 2.1 记忆的组成
`EnhancedConversationMemory` 内部维护了三类数据：

- **messages（短期对话消息）**：
  - 类型：`List[BaseMessage]`，存储 `HumanMessage` / `AIMessage`
  - 用途：在达到阈值前直接作为上下文参与摘要

- **summary（摘要，压缩后的上下文）**：
  - 类型：`str`
  - 用途：当消息过多时，把“旧消息”压缩成摘要，减少上下文长度

- **entity_store + faiss_index（实体存储与向量索引，偏长期）**：
  - `entity_store`: `List[Dict[str, Any]]`，保存实体文本、metadata、embedding（可选）
  - `faiss_index`: `faiss.Index`，用于实体相似度检索
  - 落盘文件：
    - `faiss_index/index.faiss`
    - `faiss_index/metadata.pkl`

### 2.2 写入时机
#### 2.2.1 写入对话消息
在 Orchestrator 的多个节点中都会写入 memory，例如：

- `OrchestratorAgent._requirements_generation_node()`
  - `self.memory.add_message(user_input, "user")`
  - `self.memory.add_message(llm_output, "assistant")`

- `OrchestratorAgent._rag_qa_node()`
  - `self.memory.add_message(user_input, "user")`
  - `self.memory.add_message(rag_answer, "assistant")`

这意味着：

- 需求生成、RAG 问答、普通对话都会把输入与输出纳入同一套对话记忆。

#### 2.2.2 写入实体（Entity Store）
实体写入主要发生在“生成 SRS”之后：

- `app.py` → `generate_srs()`
  - `RequirementsGenerator.extract_entities_for_storage(result)` 抽取 `FR-xxx`/`NFR-xxx`/`BR-xxx`
  - `memory.store_entity(entity["text"], entity["metadata"])` 写入 FAISS

这一步会把“结构化需求条目”变成可检索实体，作为 Agent 的长期记忆资产。

### 2.3 摘要策略（短期 → 压缩）
当 `messages` 长度超过 `max_messages_before_summary`（默认 10）时：

- `_summarize_messages()` 会把 `messages[:-5]`（较早消息）合并成文本交给 LLM 总结
- 总结结果追加到 `summary`
- 只保留最近 5 条消息作为 `messages`

效果：

- 保留“近期对话细节”（短期工作记忆）
- 旧内容压缩进摘要（更接近长期语义记忆，但当前实现默认不落盘）

### 2.4 实体检索（FAISS）
`retrieve_entities(query, top_k)`：

- 如果 embeddings 可用，使用 query embedding 在 FAISS 上做相似度检索
- 若 embeddings 不可用，则退化为返回前 `top_k` 条 entity_store

注意：当前代码中 `retrieve_entities` 在 Orchestrator 的核心链路里**并没有被用于增强提示词**（即：它存在，但尚未在回答生成时自动注入 context）。

### 2.5 清理机制
- UI 按钮：`app.py` → `_render_chat_controls()`
  - `Clear Memory` → `st.session_state.orchestrator.clear_memory()`

- `OrchestratorAgent.clear_memory()`
  - `self.memory.clear_memory()`

- `EnhancedConversationMemory.clear_memory()` 会：
  - 清空 `messages/summary/entity_store`
  - 重置 `faiss_index`
  - 并调用 `_save_faiss_index()` 把“空索引”写回磁盘

---

## 3. RAG 侧记忆：RAGIndexer 的索引与持久化

代码位置：`src/rag/indexer.py`

### 3.1 RAG 的“记忆”是什么
从系统角度看，RAG 的记忆不是对话，而是“可检索知识存储”，包括：

- **vectorstore（FAISS VectorStore）**：语义检索
- **documents（Document chunks）**：为关键词检索提供原始 chunk 列表
- **indexed_files（元数据）**：用于去重与索引统计
- **graph_index（可选 GraphRAG 图谱）**：实体/关系增强

### 3.2 落盘与恢复（长期记忆）
`RAGIndexer._load_index()` 在初始化时尝试从 `index_path`（默认 `rag_index/`）加载：

- `rag_index/faiss_index/`：向量库
- `rag_index/metadata.json`：已索引文件信息
- `rag_index/documents.json`：chunk 文本与 metadata（用于 keyword_search）
- `rag_index/graph_index.json`：图谱

`RAGIndexer._save_index()` 会保存：

- `self.vectorstore.save_local(rag_index/faiss_index)`
- 写 `metadata.json`
- 写 `documents.json`（仅当 `self.documents` 存在时）

因此：

- RAG 知识库是**可长期持久化**的。
- 应用重启后可恢复，不需要重新解析文档（前提是文件仍在且索引目录存在）。

### 3.3 清理机制
- UI 按钮：`app.py` → `_render_index_stats()`
  - `Clear Index` → `st.session_state.orchestrator.clear_rag_index()`

- `OrchestratorAgent.clear_rag_index()`
  - `self.rag_indexer.clear_index()`

- `RAGIndexer.clear_index()` 会：
  - 清空内存态的 `vectorstore/documents/indexed_files/graph_index`
  - 删除整个 `rag_index/` 目录并重建

这会彻底删除 RAG 的长期记忆（向量库、文档块、图谱）。

### 3.4 导入/导出（迁移长期记忆）
RAGIndexer 支持 JSON 导入导出：

- `export_index_json()`：导出 `indexed_files` + `documents` + `graph_index`
- `import_index_json(json_path)`：导入并重建向量库/文档列表/图谱

UI：`app.py` 的 `Export Index` 按钮。

这是一种“把长期记忆随项目迁移/共享”的机制。

---

## 4. Agent 记忆与 RAG 记忆的关系

### 4.1 彼此独立、通过 Orchestrator 协作
- Agent memory（`EnhancedConversationMemory`）由 Orchestrator 维护，用于：
  - 提供 `conversation_history`（摘要 + 最近消息）
  - 记录交互过程
  - 存储需求条目实体到 FAISS

- RAG memory（`RAGIndexer`）由 Orchestrator 持有，用于：
  - 文档检索（向量/关键词/图谱）
  - 作为问答的知识来源

二者在对象层面彼此独立：

- `OrchestratorAgent` 同时持有 `self.memory` 和 `self.rag_indexer/self.rag_chain`
- RAG 回答时会把 `history`（来自 Agent memory 的摘要）传给 `AgenticRAGChain.invoke`

### 4.2 当前的“缺口”与可改进点（仅说明，不改代码）
- Agent 的实体 FAISS（`faiss_index/`）目前主要用于存储，并未在 RAG / 需求生成提示词中自动检索注入。
- 若要实现更完整的长期记忆，可考虑：
  - 在每次回答前执行 `memory.retrieve_entities(query)` 并注入到 prompt 的 `history` 或新增字段
  - 将 `summary` 也落盘（例如存储到 JSON），实现真正可恢复的“对话长期记忆”

---

## 5. 记忆文件与目录清单（便于 GitHub/部署说明）

- **Agent 实体长期记忆（FAISS）**：
  - `faiss_index/index.faiss`
  - `faiss_index/metadata.pkl`

- **RAG 长期记忆（索引目录）**：
  - `rag_index/faiss_index/`（向量索引）
  - `rag_index/metadata.json`（索引文件元数据）
  - `rag_index/documents.json`（chunk 文本与 metadata）
  - `rag_index/graph_index.json`（图谱，若构建过）
  - `rag_index/exported_index.json`（导出文件，若导出过）

---

## 6. 相关源码索引
- `src/modules/memory.py`
- `src/agents/orchestrator.py`
- `app.py`
- `src/rag/indexer.py`
