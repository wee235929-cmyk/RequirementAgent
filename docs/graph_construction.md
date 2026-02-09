# Knowledge Graph Construction Report

## 1. 概述
本项目采用一种增量式的 GraphRAG (Graph-enhanced Retrieval-Augmented Generation) 方法构建知识图谱。该过程集成在 `RAGIndexer` 类中，主要负责从文档中提取实体（Entities）和关系（Relationships），并支持两种存储后端：
- **Neo4j 图数据库**（推荐）：提供完整的图数据库功能，支持复杂的图查询
- **JSON 文件存储**（默认）：轻量级存储，无需额外依赖

核心代码位于：
- `src/rag/indexer.py` - RAG 索引器主类
- `src/rag/neo4j_store.py` - Neo4j 图存储实现

## 2. 存储后端配置

### 2.1 Neo4j 存储（推荐）

要启用 Neo4j 存储，需要在 `.env` 文件中配置：

```bash
# Neo4j Configuration
NEO4J_URI=neo4j://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password_here
NEO4J_ENABLED=true
```

**Neo4j 优势**：
- 原生图数据库，支持复杂的图遍历查询
- 支持全文索引，实体搜索更高效
- 可视化友好，可通过 Neo4j Browser 查看图谱
- 支持 Cypher 查询语言进行高级查询
- 更好的扩展性和性能

**Neo4j 安装**：
1. 下载并安装 [Neo4j Desktop](https://neo4j.com/download/)
2. 创建新的 DBMS 并启动
3. 配置 `.env` 文件中的连接信息

### 2.2 JSON 文件存储（默认）

如果未配置 Neo4j 或 `NEO4J_ENABLED=false`，系统将自动使用 JSON 文件存储：
- 存储位置：`rag_index/graph_index.json`
- 无需额外依赖
- 适合小规模项目或快速原型开发

## 3. 构建流程详解

知识图谱的构建主要通过 `build_graph_index` 方法完成，具体步骤如下：

### 3.1 初始化与检查
- **文档检查**：首先检查系统中是否已索引文档 (`self.documents`)。如果没有文档，流程终止。
- **存储后端选择**：根据配置自动选择 Neo4j 或 JSON 存储
- **增量更新检查**：系统维护一个 `_graph_doc_count` 计数器。
  - 如果 `force_rebuild=True`，则重置图谱（包括清空 Neo4j 数据库），从头开始处理所有文档。
  - 如果并非强制重建，系统会计算 `start_idx`，仅处理尚未进入图谱的新文档。
  - 如果所有文档都已处理 (`start_idx >= len(self.documents`)，则跳过构建。

### 3.2 实体抽取 (Entity Extraction)
针对需要处理的新文档，系统采用 LLM 进行实体和关系的抽取。

- **采样策略**：
  目前代码中采用了一种采样策略 (`sample_docs`)，仅处理新文档中的前 20 篇 (`new_docs[:min(20, len(new_docs))]`)。这可能是为了控制 token 消耗或处理时间的优化策略。

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
  4. **如果使用 Neo4j**：立即将实体和关系写入 Neo4j 数据库。

### 3.3 数据聚合与存储

#### Neo4j 存储
当启用 Neo4j 时：
- 实体作为 `Entity` 节点存储，包含属性：`name`, `type`, `created_at`, `source`
- 关系作为边存储，关系类型根据抽取结果动态创建
- 自动创建索引以优化查询性能
- 同时保存 JSON 备份文件

#### JSON 存储
- **聚合**：将新抽取的实体和关系添加到现有的集合中。
  - 实体列表去重 (`list(set(entities))`)。
  - 关系列表直接追加。
- **状态更新**：更新 `document_count` 以记录已处理的文档数量。
- **持久化**：将最终的图谱数据保存到 `graph_index.json` 文件中。

## 4. 数据结构

### 4.1 Neo4j 数据模型

```cypher
// 实体节点
(:Entity {
  name: "EntityName",
  type: "REQUIREMENT|TECHNOLOGY|CONCEPT|TABLE",
  created_at: datetime(),
  updated_at: datetime(),
  source: "document_filename"
})

// 关系边
(:Entity)-[:RELATES_TO {
  type: "original_relation_type",
  created_at: datetime(),
  source: "document_filename"
}]->(:Entity)
```

**实体类型自动检测**：
- `REQUIREMENT`: 匹配 `[A-Z]{2,}-\d+` 模式（如 REQ-001, LGT-004）
- `TABLE`: 包含 "TABLE" 或 "表" 关键词
- `TECHNOLOGY`: 包含 API, DATABASE, SERVER 等技术关键词
- `CONCEPT`: 默认类型

### 4.2 JSON 数据结构

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

## 5. 检索应用 (Graph Search)

构建好的图谱主要通过 `graph_search` 方法用于增强检索。系统会自动选择合适的后端：

### 5.1 Neo4j 检索
当使用 Neo4j 时，`Neo4jGraphStore.graph_search()` 方法提供：
1. **全文索引搜索**：利用 Neo4j 全文索引快速匹配实体
2. **ID 精确匹配**：支持需求 ID 等特定格式的精确查询
3. **关系遍历**：自动获取匹配实体的相关关系

### 5.2 JSON 检索
当使用 JSON 存储时：
1. **ID 匹配**：利用正则表达式 (`[A-Z]{2,}-\d+`) 匹配查询中的特定 ID
2. **关键词匹配**：
   - 检查查询词是否出现在实体名称中
   - 检查实体名称的组成部分是否出现在查询中
3. **上下文构建**：
   - 提取匹配到的实体
   - 提取与这些实体相关的关系（三元组）
   - 将这些信息格式化为文本上下文 (`Graph context`)

## 6. API 参考

### 6.1 Neo4jGraphStore 类

```python
from src.rag.neo4j_store import Neo4jGraphStore, create_neo4j_store

# 创建实例（使用配置文件中的设置）
store = create_neo4j_store()

# 或手动指定连接参数
store = Neo4jGraphStore(
    uri="neo4j://127.0.0.1:7687",
    username="neo4j",
    password="password"
)

# 添加实体
store.add_entities(["Entity1", "Entity2"], source_doc="document.pdf")

# 添加关系
store.add_relationships([
    ["Entity1", "relates_to", "Entity2"]
], source_doc="document.pdf")

# 搜索实体
results = store.search_entities("query", limit=15)

# 图搜索（兼容 RAGIndexer 接口）
result = store.graph_search("query")
# 返回: {"entities": [...], "relationships": [...], "context": "...", "found": True}

# 获取统计信息
stats = store.get_stats()
# 返回: {"connected": True, "entity_count": 100, "relationship_count": 50, ...}

# 导出为字典（兼容 JSON 格式）
data = store.export_to_dict()

# 从字典导入
store.import_from_dict(data)

# 清空图谱
store.clear_graph()

# 关闭连接
store.close()
```

### 6.2 RAGIndexer 图相关方法

```python
from src.rag import RAGIndexer

indexer = RAGIndexer()

# 构建图索引（自动选择 Neo4j 或 JSON）
indexer.build_graph_index(force_rebuild=False)

# 图搜索
result = indexer.graph_search("query")

# 获取索引统计（包含 Neo4j 信息）
stats = indexer.get_index_stats()
# 返回包含: graph_storage, neo4j_connected, neo4j_entity_count 等

# 清空索引（包括 Neo4j 图）
indexer.clear_index()
```

## 7. 总结

本项目的 GraphRAG 实现具有以下特点：
- **双存储后端**：支持 Neo4j 图数据库和 JSON 文件存储，可根据需求选择
- **增量式**：支持随新文档加入自动更新图谱
- **混合检索**：在 `hybrid_search` 和 `graph_first_search` 中，图谱检索结果被用作向量检索和关键词检索的补充
- **无缝切换**：通过配置即可在 Neo4j 和 JSON 存储之间切换，无需修改代码
- **向后兼容**：即使启用 Neo4j，也会保留 JSON 备份文件
