# Mermaid 图表构建流程

本文档详细描述 RequirementAgent 项目中 Mermaid 图表的完整构建流程，包括生成、语法修复、渲染和错误处理机制。

## 概述

Mermaid 图表在 Deep Research 报告生成过程中用于可视化研究内容，支持 20+ 种图表类型：

**核心图表**：flowchart、sequenceDiagram、classDiagram、stateDiagram-v2、erDiagram、gantt

**数据可视化**：pie、xychart-beta、quadrantChart、sankey-beta

**概念与层次**：mindmap、timeline、journey

**技术与架构**：gitGraph、C4Context/C4Container/C4Component、architecture-beta、requirementDiagram、block-beta

## 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Mermaid 图表构建流程                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐         ┌──────────────────────────┐                 │
│  │   LLM 生成    │────────▶│     直接渲染尝试          │                 │
│  │  Mermaid 代码 │         │  _try_render_with_fix   │                 │
│  └──────────────┘         └──────────────────────────┘                 │
│                                        │                                │
│                           ┌────────────┴────────────┐                  │
│                           ▼                         ▼                   │
│                      ┌─────────┐              ┌─────────┐              │
│                      │  成功   │              │  失败   │              │
│                      └─────────┘              └─────────┘              │
│                           │                         │                   │
│                           ▼                         ▼                   │
│                      返回图片                 基本语法修复              │
│                                                    │                    │
│                                       ┌────────────┴────────────┐      │
│                                       ▼                         ▼       │
│                                  ┌─────────┐              ┌─────────┐  │
│                                  │  成功   │              │  失败   │  │
│                                  └─────────┘              └─────────┘  │
│                                       │                         │       │
│                                       ▼                         ▼       │
│                                  返回图片              LLM 语法修复     │
│                                                      （最多3次）        │
│                                                            │            │
│                                               ┌────────────┴──────┐    │
│                                               ▼                   ▼     │
│                                          ┌─────────┐        ┌─────────┐│
│                                          │  成功   │        │  失败   ││
│                                          └─────────┘        └─────────┘│
│                                               │                   │     │
│                                               ▼                   ▼     │
│                                          返回图片          返回代码块   │
│                                                         （供回退显示）  │
└─────────────────────────────────────────────────────────────────────────┘

渲染方法优先级：
  1. 本地 CLI (mmdc) - 支持中文，无网络依赖
  2. Kroki.io API - 在线服务
  3. mermaid.ink API - 备用在线服务
```

## 核心组件

### 1. LLM 图表生成 (`src/tools/chart.py`)

`MermaidChartTool` 类负责调用 LLM 生成 Mermaid 代码。

**支持的图表类型：**
- `sequence` - 时序图
- `flowchart` - 流程图
- `class` - 类图
- `er` - ER 实体关系图

**关键提示词规则：**
- 所有图表内容必须使用英文（避免 CJK 渲染问题）
- 使用简单的 ASCII 字符作为节点标签
- 遵循 Mermaid 语法规范

```python
from tools.chart import MermaidChartTool

chart_tool = MermaidChartTool()
mermaid_code = chart_tool.generate(
    requirements="用户登录流程描述...",
    diagram_type="sequence"
)
```

### 2. 语法修复 (`src/research/report_generator.py`)

#### `_fix_mermaid_syntax(mermaid_code: str) -> str`

修复 LLM 生成的常见语法错误，**不替换 CJK 字符**（保留原始语义）。

**修复内容：**
- 移除错误的 ``` 标记
- `<br>` → `<br/>` 转换
- `graph TD` → `flowchart TD` 转换
- `->` → `-->` 箭头修复（flowchart 中）
- 多行节点标签修复
- 边标签引号清理
- 特殊字符移除（`"`, `'`, `(`, `)`, `{`, `}`, `#`, `&`, `;`, `%`）
- Markdown 格式标记移除（`**`, `*`）
- HTML 标签移除（除 `<br/>`）
- 中文标点 → 英文标点转换

#### `_fix_mermaid_via_llm(mermaid_code: str, attempt: int) -> Optional[str]`

**仅在基本语法修复失败后调用**，使用 LLM 智能修复 Mermaid 语法错误。

**特点：**
- 最多调用 3 次
- 低温度 (0.1) 以获得稳定结果
- 保留原始内容（包括中文）
- 只修复语法错误，不改变语义

### 3. 渲染方法 (`src/research/report_generator.py`)

#### 渲染优先级

1. **本地 CLI (`_render_mermaid_via_cli`)**
   - 使用 `mmdc` (Mermaid CLI)
   - **优点：** 支持 CJK 字符、无网络依赖、速度快
   - **安装：** `npm install -g @mermaid-js/mermaid-cli`

2. **Kroki.io (`_render_mermaid_via_kroki`)**
   - 在线渲染服务
   - 支持 GET（压缩编码）和 POST 两种方式
   - **限制：** 不支持 CJK 字符

3. **mermaid.ink (`_render_mermaid_via_ink`)**
   - 备用在线渲染服务
   - Base64 编码
   - **限制：** 不支持 CJK 字符

#### `_try_render_with_fix(mermaid_code: str) -> Tuple[Optional[bytes], str]`

渲染策略（只在失败时修复）：

```
Step 1: 直接渲染原始代码
    ↓ 成功 → 返回 (图片数据, 代码)
    ↓ 失败
Step 2: 基本语法修复 → 尝试渲染
    ↓ 成功 → 返回 (图片数据, 修复后代码)
    ↓ 失败
Step 3: LLM 语法修复（最多3次）→ 尝试渲染
    ↓ 成功 → 返回 (图片数据, LLM修复后代码)
    ↓ 失败
返回 (None, 最终代码) → 供回退显示
```

**注意：** 渲染失败时不再返回 None，而是返回 Mermaid 代码供报告中回退显示。

### 4. 图表处理入口

#### 报告中的 Mermaid 代码块

`_process_mermaid_code_blocks(content: str) -> str`

自动查找报告内容中的 ` ```mermaid ` 代码块，渲染为图片并替换为图片引用。

#### 动态图表生成

`_render_mermaid_to_image(mermaid_type: str, description: str, context: str = "") -> Optional[str]`

根据描述动态生成 Mermaid 图表，用于 `[MERMAID: type | description]` 标记。

## 配置与提示词

### 提示词位置

| 文件 | 用途 |
|------|------|
| `src/tools/chart.py` | 4 种图表类型的生成提示词 |
| `templates/research/report_writer.j2` | 报告写作模板中的 Mermaid 规则 |
| `src/config.py` | 硬编码的 report_writer 备用提示词 |
| `src/research/agents.py` | 分段写作的 Mermaid 规则 |
| `templates/settings.yaml` | 报告生成参数配置 |

### 关键提示词规则

所有提示词都包含以下关键指令：

```
CRITICAL: ALL text in the diagram (labels, titles, names) MUST be in English.
Even if the requirements are in Chinese or another non-English language,
translate all labels to English. CJK characters will cause rendering failures.
```

## 错误处理

### 常见错误及解决方案

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| 400 Bad Request (Kroki) | CJK 字符或语法错误 | LLM 语法修复 |
| 语法错误 | LLM 生成不规范 | 基本语法修复 → LLM 修复 |
| 渲染超时 | 网络问题 | 尝试其他渲染器 |
| 全部失败 | 无法修复的错误 | 返回代码块供回退显示 |

### 日志

渲染过程会记录详细日志：

```python
logger.info("Mermaid rendered successfully with original code")
logger.info("Mermaid rendered successfully after basic syntax fix")
logger.info("Mermaid rendered successfully after LLM fix (attempt 1)")
logger.warning("LLM fix attempt 1 returned no changes")
logger.warning("All Mermaid render attempts failed, returning code for fallback display")
```

## 最佳实践

### 1. 安装本地 CLI（推荐）

```bash
npm install -g @mermaid-js/mermaid-cli
```

安装后可直接渲染中文内容，无需 CJK 替换。

### 2. 提示词优化

在自定义提示词中明确要求使用英文：

```
Generate a Mermaid diagram with ALL labels in English.
Do NOT use Chinese or other CJK characters.
```

### 3. 图表类型选择

| 场景 | 推荐类型 |
|------|----------|
| 用户交互流程 | `sequenceDiagram` |
| 系统架构 | `flowchart` |
| 数据模型 | `erDiagram` |
| 对象关系 | `classDiagram` |
| 状态转换 | `stateDiagram-v2` |
| 项目时间线 | `gantt` |
| 数据分布 | `pie` |
| 概念层次 | `mindmap` |
| 历史事件 | `timeline` |
| 优先级矩阵 | `quadrantChart` |

## 测试

运行全类型测试脚本：

```bash
python tests/test_mermaid_all_types.py
```

测试覆盖 10 种图表类型 × 2 种语言（中/英）= 20 个测试用例。

## 文件结构

```
src/
├── tools/
│   └── chart.py                    # MermaidChartTool - LLM 图表生成
├── research/
│   └── report_generator.py         # 渲染管道核心逻辑
│       ├── _fix_mermaid_syntax()           # 基本语法修复（仅在渲染失败时调用）
│       ├── _fix_mermaid_via_llm()          # LLM 智能语法修复（最多3次）
│       ├── _try_render_with_fix()          # 渲染入口（失败时返回代码）
│       ├── _try_all_renderers()            # 尝试所有渲染器
│       ├── _render_mermaid_via_cli()       # 本地 CLI 渲染
│       ├── _render_mermaid_via_kroki()     # Kroki API 渲染
│       └── _render_mermaid_via_ink()       # mermaid.ink 渲染
└── config.py                       # 提示词配置

templates/research/
└── report_writer.j2                # 报告写作模板（含 Mermaid 规则）

tests/
└── test_mermaid_all_types.py       # 全类型渲染测试

reports/image_cache/
└── mermaid_*.png                   # 渲染后的图片缓存
```

## 版本历史

- **v1.0**: 初始实现，使用 Kroki/mermaid.ink 渲染
- **v1.1**: 添加 CJK 字符处理，避免空标签
- **v1.2**: 重构为渐进式策略，优先保留原始内容
- **v1.3**: 添加本地 CLI 渲染支持，支持中文原生渲染
- **v2.0**: 重构渲染策略
  - 只在渲染失败时才进行语法修复
  - 添加 LLM 智能语法修复（最多3次）
  - 移除 CJK 替换、简化复杂元素、激进简化策略
  - 渲染失败时返回代码块供回退显示
