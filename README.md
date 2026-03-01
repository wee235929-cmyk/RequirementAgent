# Deep Research 功能展示

## 简介

Deep Research 是 RequirementAgent 项目的核心功能之一，能够针对用户提出的任意研究问题，自动完成多源信息检索、内容综合分析，并生成结构完整、排版专业的深度研究报告（支持 PDF 和 Word 格式）。

该功能在 [DeepResearch-Bench Leaderboard](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard) 基准评测中 **排名第 12**。

---

## 结果示例

以下展示两份由 Deep Research 自动生成的研究报告。

### 报告一：Diamond Sutra（金刚经）深度研究

一份关于金刚般若波罗蜜经的综合性跨学科研究报告，涵盖佛学哲学、历史传承、现代应用等多维度分析，共 46 页。

**报告首页与正文：**

![报告一 - 首页与正文](../report1_a.png)

- 标题：*Deep Research: Create comprehensive, in-depth study notes for the Diamond Sutra*
- 包含执行摘要、历史与哲学基础、核心教义分析等章节
- 引用了历史手稿图片及学术文献
- 报告由 RAAA Deep Research 系统自动生成，日期 2026 年 2 月 20 日

**参考文献：**

![报告一 - 参考文献](../report1_b.png)

- 共 22 条参考文献，涵盖 Wikipedia、学术期刊（Springer、JSTOR）、Stanford 大学资源等
- 采用 APA 格式规范引用

---

### 报告二：需求工程技术发展调研

一份关于需求工程领域最新工具技术发展、标准体系及行业应用的中文深度调研报告，共 49 页。

**报告首页与正文：**

![报告二 - 首页与正文](../report2_a.png)

- 标题：*深度研究：需求工程最新的工具技术发展情况，标准概况等*
- 包含需求工程流程图（Mermaid 图表自动生成）
- 涵盖执行摘要、技术工具发展、国际标准体系、国内外对比分析等内容
- 报告由 RAAA 深度研究系统自动生成，日期 2026 年 2 月 27 日

**结论与参考文献：**

![报告二 - 结论与参考文献](../report2_b.png)

- 包含 AI 时代需求管理工具演进概念图
- 共 12 条参考文献，涵盖 Wikipedia、arXiv、学术期刊、技术博客等
- 支持中英文混合引用

---

## Benchmark 排名

| 评测平台 | 排名 | 链接 |
|---------|------|------|
| DeepResearch-Bench Leaderboard | **#12** | [查看排行榜](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard) |

---

## 功能特点

- **全自动研究流程**：从问题分析到报告生成，全程无需人工干预
- **多源信息融合**：并行搜索网络、学术文献、官方文档等多种信息源
- **多语言支持**：自动检测查询语言，支持中文、英文等多语言报告生成
- **专业排版输出**：自动生成包含图表、公式、表格的 PDF/Word 报告
- **领域自适应**：根据研究主题自动调整报告结构和写作风格

---

## 相关文档

- [Deep Research 核心架构与研究思路](./deep_research_architecture.md)
