# Deep Research 功能流程说明

本文档详细说明本项目的 **Deep Research（深度调研）** 功能从用户输入到生成 PDF 报告的完整执行链路、工作流结构、各 Agent 的职责、状态数据结构、以及关键的错误处理与产物落盘方式。

> 相关代码位置：
>
>- API 入口：`api/routes/research.py`
>- Orchestrator 路由与节点实现：`src/core/orchestrator.py`
>- Deep Research 工作流：`src/research/workflow.py`
>- Planner/Searcher/Writer Agents：`src/research/agents.py`
>- 报告生成（PDF/Word）：`src/research/report_generator.py`
>- Prompt 配置：`src/config.py` + `templates/research/*.j2`（调研提示词模板）
>- 参数配置：`templates/settings.yaml`（deep_research 配置项）

---

## 1. 功能概述

Deep Research 用于把一个“宽泛的调研问题”自动拆解为若干可执行任务，并通过网络搜索收集资料，再把结果综合成结构化研究报告，同时生成 PDF 文件供下载。

该能力本质上是一个 **LangGraph 工作流**，由多个角色明确的子 Agent 组成：

- **PlannerAgent**：把用户 query 分解为 **8-12 个** research tasks（JSON 数组），覆盖多个维度
- **SearcherAgent**：对每个 task 执行 Web Search（DuckDuckGo，每个任务 **10 条结果**），并对搜索结果做二次综合（synthesis），同时**搜索相关图片**
- **WriterAgent**：汇总所有 task 的产出，生成**15-20 页**的详细报告（目标 **25,000-35,000 字**）
- **PDFReportGenerator**：把报告文本转成 PDF 并落盘到 `reports/`，**支持图片嵌入和表格渲染**

### 1.1 增强功能（v2.0）

| 功能 | 原版 | 增强版 |
|-----|------|-------|
| 研究任务数量 | 3-5 个 | 8-12 个 |
| 每任务搜索结果 | 5 条 | 10 条 |
| 报告篇幅 | ~6 页 | 15-20 页 (3w+ 字) |
| 图片支持 | ❌ | ✅ 自动搜索并嵌入 |
| 表格支持 | ❌ | ✅ Markdown 表格渲染 |
| 任务分类 | 无 | 按类别组织（概述/历史/技术/案例等） |
| **搜索执行** | 顺序执行 | **并行执行（4个子代理）** |
| **输出格式** | 仅 PDF | **PDF + Word 双格式** |
| **报告格式** | 普通格式 | **学术论文格式** |

### 1.2 并行搜索架构（v2.1）

为大幅缩短研究时间，SearcherAgent 现在采用**并行子代理架构**：

```
┌─────────────────────────────────────────────────────────┐
│                    SearcherAgent                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              ThreadPoolExecutor                  │    │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐     │    │
│  │  │SubSearch-0│ │SubSearch-1│ │SubSearch-2│ ... │    │
│  │  │  Task 0   │ │  Task 1   │ │  Task 2   │     │    │
│  │  │  Task 4   │ │  Task 5   │ │  Task 6   │     │    │
│  │  └───────────┘ └───────────┘ └───────────┘     │    │
│  └─────────────────────────────────────────────────┘    │
│                         ↓                                │
│              格式化综合所有结果                           │
└─────────────────────────────────────────────────────────┘
```

**配置项**（`templates/settings.yaml` 或环境变量）：

| 配置 | 环境变量 | 默认值 | 说明 |
|-----|---------|-------|------|
| `parallel_searchers` | `DEEP_RESEARCH_PARALLEL_SEARCHERS` | 4 | 并行子代理数量 |
| `max_tasks` | `DEEP_RESEARCH_MAX_TASKS` | 12 | 最大任务数 |
| `search_results_per_task` | `DEEP_RESEARCH_SEARCH_RESULTS` | 10 | 每任务搜索结果数 |
| `images_per_task` | `DEEP_RESEARCH_IMAGES_PER_TASK` | 2 | 每任务图片数 |
| `search_timeout` | `DEEP_RESEARCH_SEARCH_TIMEOUT` | 30 | 搜索超时(秒) |

---

## 2. 从 API 到 Deep Research：触发与入口

### 2.1 用户请求
用户通过 React 前端发送请求到 `api/routes/research.py` 的 `/api/research/start` 端点。

### 2.2 意图识别与处理策略
在 `api/routes/chat.py` 中，输入会先进行意图判断：

- 如果是 `general_chat`：走流式输出（streaming）
- 如果是 `deep_research` 或“混合意图”（mixed intents）：走异步后台任务处理
- 否则走标准处理

对 Deep Research 来说，API 使用：

- `api/routes/research.py` → `start_research()`
  - 创建后台线程执行调研任务
  - 前端轮询 `/api/research/status` 获取进度
  - 完成后提供 PDF/Word 下载

### 2.3 Orchestrator 内部路由
在 `src/core/orchestrator.py` 中，`OrchestratorAgent` 是 LangGraph 的编排器：

- `detect_intent_node`：调用 LLM 做 intent classification
- 根据 intent 路由到节点：
  - `requirements_generation`
  - `rag_qa`
  - `deep_research`
  - `general_chat`

当 intent 为 `deep_research` 时，进入：

- `OrchestratorAgent._deep_research_node()`

---

## 3. Orchestrator 的 Deep Research 节点做了什么

代码位置：`src/core/orchestrator.py` → `_deep_research_node()`

### 3.1 主要职责
该节点主要负责：

- 调用 Deep Research 工作流：
  - `result = self.deep_research_workflow.invoke(state["user_input"])`
- 将工作流结果转为对用户友好的输出：
  - 展示 query
  - 展示完成的 task 列表
  - 展示报告正文的前 2000 字预览
  - 展示 PDF 文件路径（如生成成功）
- 写入 memory：
  - 把用户输入与最终响应写入对话记忆（用于后续上下文）

### 3.2 结果展示格式
当 `result["status"] == "complete"` 且存在 `pdf_path`：

- 输出标题前缀：`**[Deep Research Mode]**`
- 拼接：
  - `Research Query`
  - `Research Tasks Completed`（来自 tasks）
  - `report` 的片段预览（前 2000 字）
  - `PDF Report Generated: <pdf_path>`

否则：

- 如果 status 为 `error`：展示失败原因
- 其他 status：给出警告性提示

---

## 4. Deep Research 工作流结构（LangGraph）

代码位置：`src/research/workflow.py`

### 4.1 状态结构：ResearchState
工作流使用 `ResearchState` 作为全局状态（TypedDict），关键字段：

- `query`: 原始调研问题
- `tasks`: 任务列表（ResearchTask）
- `current_task_index`: 当前执行到第几个 task
- `all_results`: 每个 task 的综合输出累积
- `all_images`: **[新增]** 收集的所有图片信息列表
- `all_tables`: **[新增]** 收集的所有表格数据列表
- `report`: Writer 输出的完整报告
- `pdf_path`: PDF 文件路径（字符串）
- `status`: 当前阶段标识（started/planning_complete/searching/writing_complete/complete/error 等）
- `error`: 错误信息

### 4.2 单个任务结构：ResearchTask
每个 task 结构：

- `task`: 任务描述
- `priority`: 优先级（1-5，1 最高）
- `category`: **[新增]** 任务类别（overview/historical/technical/case_studies 等）
- `completed`: 是否完成
- `results`: 搜索与综合后的文本结果
- `images`: **[新增]** 该任务搜索到的图片列表

### 4.3 工作流图（节点与边）
工作流由 4 个节点组成：

- `planner` → `searcher` → `writer` → `pdf_generator`

其中 `searcher` 有条件边（循环）：

- 如果 `current_task_index < len(tasks)`：继续 `searcher`
- 否则：进入 `writer`

这形成了一个“任务列表迭代执行”的循环结构。

### 4.4 工作流入口：invoke()
`DeepResearchWorkflow.invoke(query)` 会创建初始状态：

- `tasks=[]`
- `current_task_index=0`
- `all_results=[]`
- `report=""`
- `pdf_path=""`
- `status="started"`
- `error=""`

然后执行：

- `final_state = self.graph.invoke(initial_state)`

最后返回一个便于上层展示的 dict：

- `query`, `tasks`, `report`, `pdf_path`, `status`, `error`

> 代码里提供了 `progress_callback` 参数，但目前在具体节点执行中并未系统性使用，仅在 invoke 开头有一个可选回调调用。

---

## 5. PlannerAgent：任务规划阶段（Planning）

代码位置：`src/research/agents.py` → `PlannerAgent`

### 5.1 使用的 Prompt
Planner 使用：

- `SYSTEM_PROMPTS["research_planner"]`

该 prompt 要求模型输出一个 JSON 数组：

```json
[{"task": "...", "priority": 1}]
```

并强调任务应该“可执行、可搜索”。

### 5.2 输出解析与容错
Planner 的 `plan()` 对 LLM 输出做了较强的“容错解析”：

- 支持模型输出带 ```json code fence``` 或 ``` code fence```
- 支持从输出中截取第一个 `[` 到最后一个 `]` 的内容
- 解析失败则 fallback 为单任务：
  - `General research on: <query>`

### 5.3 任务排序
Planner 会对任务按 `priority` 升序排序（优先级 1 最先执行）。

工作流随后将：

- `state["tasks"] = tasks`
- `state["current_task_index"] = 0`
- `state["status"] = "planning_complete"`

---

## 6. SearcherAgent：搜索与综合阶段（Searching + Synthesis）

代码位置：`src/research/agents.py` → `SearcherAgent`

### 6.1 搜索引擎与依赖
Searcher 使用 DuckDuckGo：

- 依赖：`ddgs`（或旧包 `duckduckgo_search` 作为 fallback）
- 调用：`self.web_search.text(task, max_results=5)`

如果 Web Search 不可用（初始化失败），`search()` 会返回：

- `[Search unavailable] Task: <task>`

### 6.2 结果格式化（给综合 LLM 的输入）
Searcher 将每条搜索结果格式化为：

- 标号（[1], [2], ...）
- title
- body（摘要）
- href（Source URL）

然后把这些拼成一段 `search_text`。

### 6.3 二次综合（Synthesis）
仅有搜索结果列表通常噪声大，因此 Searcher 还会用 LLM 做“二次综合”：

- Prompt：`SYSTEM_PROMPTS["research_synthesizer"]`
- 输入：
  - `task`
  - `search_results`（格式化后的搜索结果文本）
- 输出：一个面向该 task 的“可读摘要/要点综合”

Searcher 返回的是 **synthesis 文本**，不是原始搜索结果列表。

### 6.4 工作流如何更新状态
`workflow.py` 的 `_searcher_node()` 会：

- 取当前任务 `tasks[current_task_index]`
- 执行 `SearcherAgent.search(task)` 得到 `result`
- 更新 task：
  - `completed=True`
  - `results=result`
- 追加到 `all_results`：
  - 以 `**Task: ...**\n\n<result>` 的格式保存
- `current_task_index += 1`
- `status = "searching"`

异常处理：如果某个 task 搜索失败，会记录日志并直接推进到下一个 task（不会中断整个 workflow）。

---

## 7. WriterAgent：报告生成阶段（Writing）

代码位置：`src/research/agents.py` → `WriterAgent`

### 7.1 使用的 Prompt 与报告结构
Writer 使用：

- `SYSTEM_PROMPTS["report_writer"]`

该 prompt 明确要求报告包含：

1. Executive Summary
2. Introduction
3. Main Findings
4. Key Insights
5. Conclusions
6. References

因此你在 UI 上看到的深度调研报告通常是一个结构化长文本。

### 7.2 输入组织方式
Writer 会把 `all_results` 组织为：

- `Finding 1`, `Finding 2`, ...
- Findings 之间用 `---` 分隔

然后把 `query + combined_results` 一起交给 LLM。

### 7.3 工作流状态更新
Writer 成功时：

- `state["report"] = report`
- `status = "writing_complete"`

失败时：

- `status = "error"`
- `error = "Writing failed: ..."`

---

## 8. PDF 生成阶段（PDFReportGenerator）

代码位置：`src/research/report_generator.py`

### 8.1 产物目录
PDF 输出目录默认是：

- `REPORTS_DIR`（来自 `src/config.py`）
- 通常对应项目根目录下的 `reports/`

### 8.2 文件命名
如果不指定 filename，则自动生成：

- `research_report_<YYYYMMDD_HHMMSS>.pdf`

### 8.3 文本转 PDF 的规则
该实现采用 reportlab，将“markdown-like”文本逐行转换为 PDF 段落：

- `# `：视为大标题
- `## `：视为二级标题
- `### `：加粗小标题
- `- ` / `* `：转为项目符号（以 `•` 输出）
- 其他行：普通正文

这意味着：

- Writer 输出若遵循 markdown 样式，会在 PDF 中呈现更好的层级结构。

### 8.4 工作流状态更新
`workflow.py` 的 `_pdf_generator_node()`：

- 若 `report` 非空：
  - 调用 `PDFReportGenerator.generate(...)`
  - `state["pdf_path"] = <path>`
  - `status = "complete"`
- 否则：
  - `status = "error"`
  - `error = "No report content to generate PDF"`

---

## 9. UI 层的展示与下载

当 Deep Research 完成并生成 PDF/Word 报告：

- React 前端通过 `/api/research/status` 轮询任务状态
- 完成后通过 `/api/research/download/{task_id}` 下载报告
- 支持 PDF 和 Word 双格式下载

---

## 10. 关键限制与可扩展点（面向维护者）

- **无缓存**：同一 task 的 web search 每次都会重新请求（没有做结果缓存/去重）
- **引用追踪较弱**：
  - Searcher 在 synthesis 时把 URL 当作“Source”文本输入，但 Writer 的最终报告不保证逐条保留引用
  - 如果需要严格可追溯引用，可考虑把每个 task 的原始结果（含 URL 列表）也纳入 Writer 的输入，并在 prompt 强制输出 References
- **容错策略偏“不断推进”**：
  - 搜索失败不会中断 workflow，而是推进下一个任务
  - 这有利于完成率，但可能导致报告某部分缺失
- **progress_callback 未全面贯通**：
  - 代码保留了进度回调接口，但目前 UI 仅使用 spinner
  - 若要更细粒度进度条，可在 planner/searcher/writer/pdf 节点中补充回调调用

---

## 11. 相关文件索引
- `api/routes/research.py` - 调研 API 入口
- `src/research/agents.py` - Planner/Searcher/Writer 代理
- `src/research/workflow.py` - LangGraph 工作流
- `src/research/report_generator.py` - PDF/Word 报告生成器
- `src/core/orchestrator.py` - 编排代理
- `src/config.py` - 配置文件
- `templates/settings.yaml` - 参数配置
- `templates/research/*.j2` - 调研提示词模板
