# Knowledge Graph Construction Report

## 1. 概述
本项目采用一种轻量级、增量式的 GraphRAG (Graph-enhanced Retrieval-Augmented Generation) 方法构建知识图谱。该过程集成在 `RAGIndexer` 类中，主要负责从文档中提取实体（Entities）和关系（Relationships），并将其存储为结构化的 JSON 数据，用于增强后续的检索和问答环节。

核心代码位于：`src/rag/indexer.py`

## 2. 构建流程详解

知识图谱的构建主要通过 `build_graph_index` 方法完成，具体步骤如下：

### 2.1 初始化与检查
- **文档检查**：首先检查系统中是否已索引文档 (`self.documents`)。如果没有文档，流程终止。
- **增量更新检查**：系统维护一个 `_graph_doc_count` 计数器。
  - 如果 `force_rebuild=True`，则重置图谱，从头开始处理所有文档。
  - 如果并非强制重建，系统会计算 `start_idx`，仅处理尚未进入图谱的新文档。
  - 如果所有文档都已处理 (`start_idx >= len(self.documents`)，则跳过构建。

### 2.2 实体抽取 (Entity Extraction)
针对需要处理的新文档，系统采用 LLM 进行实体和关系的抽取。

- **采样策略**：
  目前代码中采用了一种采样策略 (`sample_docs`)，仅处理新文档中的前 20 篇 (`new_docs[:min(20, len(new_docs))]`)。这可能是为了控制 token 消耗或处理时间的优化策略。
  > 代码引用: `src/rag/indexer.py:293`

- **Prompt 设计**：
  使用 `ChatPromptTemplate` 构建提示词，指示 LLM 从文本中识别关键实体（如人名、组织、概念、技术、需求等）及其相互关系。
  
  **System Prompt**:
  ```text
  Extract key entities (people, organizations, concepts, technologies, requirements) from the following text.
  Return as JSON: {"entities": ["entity1", "entity2", ...], "relationships": [["entity1", "relates_to", "entity2"], ...]}
  ```

- **处理循环**：
  1. 对每个采样文档，截取前 2000 个字符 (`doc.page_content[:2000]`)。
  2. 调用配置好的 LLM (`ChatOpenAI`)。
  3. 解析 LLM 返回的 JSON 内容，提取 `entities` 和 `relationships`。

### 2.3 数据聚合与存储
- **聚合**：将新抽取的实体和关系添加到现有的集合中。
  - 实体列表去重 (`list(set(entities))`)。
  - 关系列表直接追加。
- **状态更新**：更新 `document_count` 以记录已处理的文档数量。
- **持久化**：将最终的图谱数据保存到 `graph_index.json` 文件中。

## 3. 数据结构

构建生成的知识图谱以 JSON 格式存储，包含以下关键字段：

```json
{
  "entities": [
    "EntityA",
    "EntityB",
    ...
  ],
  "relationships": [
    ["EntityA", "relation_type", "EntityB"],
    ...
  ],
  "document_count": 10
}
```

## 4. 检索应用 (Graph Search)

构建好的图谱主要通过 `graph_search` 方法用于增强检索：

1. **ID 匹配**：利用正则表达式 (`[A-Z]{2,}-\d+`) 匹配查询中的特定 ID（如需求 ID）与图谱中的实体 ID。
2. **关键词匹配**：
   - 检查查询词是否出现在实体名称中。
   - 检查实体名称的组成部分是否出现在查询中。
3. **上下文构建**：
   - 提取匹配到的实体。
   - 提取与这些实体相关的关系（三元组）。
   - 将这些信息格式化为文本上下文 (`Graph context`)，辅助 LLM 生成答案。

## 5. 总结

本项目的 GraphRAG 实现具有以下特点：
- **轻量化**：不依赖复杂的图数据库（如 Neo4j），直接使用 JSON 文件存储。
- **增量式**：支持随新文档加入自动更新图谱。
- **混合检索**：在 `hybrid_search` 和 `graph_first_search` 中，图谱检索结果被用作向量检索和关键词检索的补充，特别是在处理特定领域术语和实体关系时提供额外的上下文信息。
