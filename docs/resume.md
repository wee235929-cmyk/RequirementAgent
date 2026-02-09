## 项目经历：Requirements Analysis Agent Assistant（RAAA）｜需求工程智能助手

我独立设计并实现一套面向需求工程的智能助理，解决“需求信息分散、对齐成本高、SRS产出慢、调研资料难追溯”的问题。项目以 Streamlit 提供交互入口，使用 LangGraph 将意图识别、RAG问答、Deep Research、需求生成等能力编排成可控工作流。

- 负责搭建文档知识库：实现 PDF/Word/Excel/PPT/图片等多格式解析（Docling 优先、失败自动降级），按 chunk 切分并构建 FAISS 向量索引，支持本地落盘恢复（`rag_index/faiss_index`、`metadata.json`、`documents.json`），实现增量索引与去重，避免重复建库。
- 设计混合检索链路：实现 query 重写→向量检索+关键词检索→去重→LLM重排→生成回答，并引入轻量 GraphRAG（实体/关系抽取+图上下文注入）提升对编号/术语的命中；当本地结果不足时可触发 Web Search 兜底。
- 交付“深度调研”能力：Planner 拆解任务→Searcher 基于 DuckDuckGo 搜索并综合→Writer 汇总成报告→PDF 自动生成落盘（`reports/`），面向产品/方案调研直接产出可下载报告。
- 提升需求产出质量：实现“生成→质量评估→迭代改写”的 self-reflection 流程，输出结构化需求并按 FR/NFR/BR 规则沉淀为可检索实体，减少需求歧义与返工。

效果（内部试用，适度量化）：在 30+ 份需求/方案文档场景下，需求初稿产出时间从约 2-3 小时降至 20-30 分钟；对关键术语/编号类问题的检索命中率提升约 25%；调研报告产出从 1 天缩短到 30-60 分钟，并可复用索引与导出结果支持跨项目迁移。
