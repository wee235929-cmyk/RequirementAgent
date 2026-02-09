"""
Deep Research Workflow - 深度调研工作流

基于 LangGraph 实现的多 Agent 协作工作流，用于自动化深度调研。

工作流程：
    1. QueryAnalyzer（查询分析扩写器）：对用户查询进行意图识别、概念提取和查询扩写
    2. Planner（规划器）：基于扩写后的查询拆解为 8-12 个可搜索的子任务
    3. Searcher（搜索器）：并行执行所有搜索任务，收集并综合信息
    4. Writer（写作器）：将搜索结果整合为结构化研究报告
    5. PDF Generator（PDF生成器）：将报告导出为 PDF 和 Word 文档

核心特性：
    - 并行搜索：多个子代理同时执行搜索任务，大幅缩短调研时间
    - 容错设计：单个任务失败不会中断整个工作流
    - 双格式输出：同时生成 PDF 和 Word 文档
"""
import sys
from pathlib import Path
from typing import Dict, Any

from langgraph.graph import StateGraph, START, END

# 添加项目根目录到路径，确保模块导入正常
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils import get_logger
from research.agents import (
    QueryAnalyzerAgent,
    PlannerAgent, 
    SearcherAgent, 
    WriterAgent, 
    ResearchState
)
from research.report_generator import PDFReportGenerator

logger = get_logger(__name__)


class DeepResearchWorkflow:
    """
    深度调研工作流主类
    
    基于 LangGraph 状态图实现，协调多个 Agent 完成完整的调研流程。
    采用并行搜索架构，显著提升调研效率。
    
    Attributes:
        planner: 任务规划代理，负责拆解调研问题
        searcher: 搜索代理，负责并行执行搜索任务
        writer: 写作代理，负责生成研究报告
        pdf_generator: PDF生成器，负责导出文档
        graph: 编译后的 LangGraph 状态图
    """
    
    def __init__(self):
        """初始化工作流，创建所有子代理并构建状态图"""
        self.query_analyzer = QueryAnalyzerAgent()
        self.planner = PlannerAgent()
        self.searcher = SearcherAgent()
        self.writer = WriterAgent()
        self.pdf_generator = PDFReportGenerator()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """
        构建 LangGraph 工作流状态图
        
        节点流程: query_analyzer → planner → parallel_searcher → writer → pdf_generator
        
        Returns:
            编译后的状态图，可直接调用 invoke() 执行
        """
        workflow = StateGraph(ResearchState)
        
        workflow.add_node("query_analyzer", self._query_analyzer_node)
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("parallel_searcher", self._parallel_searcher_node)
        workflow.add_node("writer", self._writer_node)
        workflow.add_node("pdf_generator", self._pdf_generator_node)
        
        workflow.add_edge(START, "query_analyzer")
        workflow.add_edge("query_analyzer", "planner")
        workflow.add_edge("planner", "parallel_searcher")
        workflow.add_edge("parallel_searcher", "writer")
        workflow.add_edge("writer", "pdf_generator")
        workflow.add_edge("pdf_generator", END)
        
        return workflow.compile()
    
    def _query_analyzer_node(self, state: ResearchState) -> ResearchState:
        """
        查询分析扩写节点：在规划之前对用户查询进行分析和扩写
        
        通过 LLM 对原始查询进行意图识别、关键概念提取、查询扩写，
        生成更丰富的英文查询以提升后续搜索质量。
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态，包含 expanded_query 和 query_analysis
        """
        logger.info(f"[QueryAnalyzer] Analyzing query: {state['query'][:50]}...")
        
        try:
            analysis = self.query_analyzer.analyze(state["query"])
            
            state["expanded_query"] = analysis.get("expanded_query", state["query"])
            state["query_analysis"] = analysis
            state["status"] = "query_analyzed"
            
            logger.info(
                f"[QueryAnalyzer] Expanded query: {state['expanded_query'][:80]}... "
                f"| Language: {analysis.get('detected_language', 'unknown')} "
                f"| Concepts: {len(analysis.get('key_concepts', []))}"
            )
        except Exception as e:
            # 降级处理：使用原始查询继续
            state["expanded_query"] = state["query"]
            state["query_analysis"] = {}
            state["status"] = "query_analyzed"
            logger.warning(f"[QueryAnalyzer] Failed, using original query: {e}")
        
        return state
    
    def _planner_node(self, state: ResearchState) -> ResearchState:
        """
        规划节点：将用户查询拆解为多个可执行的搜索任务
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态，包含任务列表
        """
        # 使用扩写后的查询进行任务规划（如果可用）
        planning_query = state.get("expanded_query") or state["query"]
        logger.info(f"[Planner] Planning research for: {planning_query[:50]}...")
        
        try:
            # 调用规划代理生成任务列表
            tasks = self.planner.plan(planning_query)
            
            # 初始化状态字段
            state["tasks"] = tasks
            state["current_task_index"] = 0
            state["all_results"] = []
            state["all_images"] = []
            state["all_tables"] = []
            state["status"] = "planning_complete"
            
            logger.info(f"[Planner] Generated {len(tasks)} tasks")
        except Exception as e:
            state["error"] = f"Planning failed: {str(e)}"
            state["status"] = "error"
            logger.error(f"[Planner] Error: {e}")
        
        return state
    
    def _parallel_searcher_node(self, state: ResearchState) -> ResearchState:
        """
        并行搜索节点：使用多个子代理并行执行所有搜索任务
        
        相比顺序执行，并行架构可将搜索时间缩短 3-4 倍。
        
        Args:
            state: 当前工作流状态，需包含 tasks 列表
            
        Returns:
            更新后的状态，包含搜索结果和图片
        """
        tasks = state["tasks"]
        
        if not tasks:
            state["status"] = "searching_complete"
            return state
        
        logger.info(f"[Parallel Searcher] Starting parallel execution of {len(tasks)} tasks...")
        
        try:
            # 并行执行所有搜索任务（传入原始查询以确定输出语言）
            results = self.searcher.search_tasks_parallel(tasks, original_query=state["query"])
            
            # 处理每个任务的搜索结果
            for idx, result in enumerate(results):
                if result is None:
                    continue
                
                category = result.get("category", "general")
                synthesis = result.get("synthesis", "")
                images = result.get("images", [])
                
                # 更新任务状态
                tasks[idx]["completed"] = result.get("success", False)
                tasks[idx]["results"] = synthesis
                tasks[idx]["images"] = images
                
                # 格式化结果供 Writer 使用
                formatted_result = self._format_task_result(
                    task_desc=result.get("task", ""),
                    category=category,
                    synthesis=synthesis,
                    task_index=idx
                )
                state["all_results"].append(formatted_result)
                
                # 收集图片信息
                for img in images:
                    img["category"] = category
                    img["task_index"] = idx
                    state["all_images"].append(img)
            
            state["tasks"] = tasks
            state["current_task_index"] = len(tasks)
            state["status"] = "searching_complete"
            
            successful = sum(1 for t in tasks if t.get("completed"))
            logger.info(f"[Parallel Searcher] Completed {successful}/{len(tasks)} tasks, collected {len(state['all_images'])} images")
            
        except Exception as e:
            state["error"] = f"Parallel search failed: {str(e)}"
            state["status"] = "error"
            logger.error(f"[Parallel Searcher] Error: {e}")
        
        return state
    
    def _format_task_result(self, task_desc: str, category: str, synthesis: str, task_index: int) -> str:
        """
        格式化单个任务的搜索结果，供 Writer 使用
        
        Args:
            task_desc: 任务描述
            category: 任务类别（如 overview, technical 等）
            synthesis: 搜索结果的综合摘要
            task_index: 任务索引（从0开始）
            
        Returns:
            格式化后的 Markdown 文本
        """
        category_title = category.replace('_', ' ').title()
        return (
            f"## Research Finding {task_index + 1}: {category_title}\n"
            f"**Research Focus:** {task_desc}\n\n"
            f"{synthesis}\n\n---\n"
        )
    
    def _writer_node(self, state: ResearchState) -> ResearchState:
        """
        写作节点：将所有搜索结果整合为结构化研究报告
        
        Args:
            state: 当前工作流状态，需包含 all_results 列表
            
        Returns:
            更新后的状态，包含完整报告
        """
        logger.info(f"[Writer] Generating report from {len(state['all_results'])} findings...")
        
        try:
            report = self.writer.write(state["query"], state["all_results"])
            state["report"] = report
            state["status"] = "writing_complete"
            logger.info("[Writer] Report generated successfully")
        except Exception as e:
            state["error"] = f"Writing failed: {str(e)}"
            state["status"] = "error"
            logger.error(f"[Writer] Error: {e}")
        
        return state
    
    def _pdf_generator_node(self, state: ResearchState) -> ResearchState:
        """
        PDF生成节点：将报告导出为 PDF 和 Word 文档
        
        Args:
            state: 当前工作流状态，需包含 report 内容
            
        Returns:
            更新后的状态，包含文件路径
        """
        logger.info("[PDF] Generating PDF and Word reports...")
        
        try:
            if not state.get("report"):
                state["error"] = "No report content to generate PDF"
                state["status"] = "error"
                return state
            
            # 生成 PDF 和 Word 双格式文档
            pdf_path, docx_path = self.pdf_generator.generate_both(
                title=f"Research Report: {state['query'][:50]}",
                content=state["report"],
                images=state.get("all_images", []),
                tables=state.get("all_tables", [])
            )
            
            state["pdf_path"] = pdf_path
            state["docx_path"] = docx_path or ""
            state["status"] = "complete"
            logger.info(f"[PDF] Reports saved: PDF={pdf_path}, DOCX={docx_path}")
            
        except Exception as e:
            state["error"] = f"PDF generation failed: {str(e)}"
            state["status"] = "error"
            logger.error(f"[PDF] Error: {e}")
        
        return state
    
    def invoke(self, query: str, progress_callback=None) -> Dict[str, Any]:
        """
        执行完整的深度调研工作流
        
        这是工作流的主入口方法，会依次执行：规划 → 搜索 → 写作 → PDF生成
        
        Args:
            query: 用户的调研问题/主题
            progress_callback: 可选的进度回调函数，用于向 UI 报告进度
            
        Returns:
            包含以下字段的字典：
            - query: 原始查询
            - tasks: 任务列表
            - report: 生成的报告内容
            - pdf_path: PDF 文件路径
            - docx_path: Word 文件路径
            - status: 执行状态（complete/error）
            - error: 错误信息（如有）
        """
        # 初始化工作流状态
        initial_state = ResearchState(
            query=query,
            expanded_query="",
            query_analysis={},
            tasks=[],
            current_task_index=0,
            all_results=[],
            all_images=[],
            all_tables=[],
            report="",
            pdf_path="",
            docx_path="",
            status="started",
            error=""
        )
        
        try:
            if progress_callback:
                progress_callback("Starting research workflow...")
            
            # 执行 LangGraph 状态图
            final_state = self.graph.invoke(initial_state)
            
            # 返回结果
            return {
                "query": query,
                "tasks": final_state.get("tasks", []),
                "report": final_state.get("report", ""),
                "pdf_path": final_state.get("pdf_path", ""),
                "docx_path": final_state.get("docx_path", ""),
                "status": final_state.get("status", "unknown"),
                "error": final_state.get("error", "")
            }
            
        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            return {
                "query": query,
                "tasks": [],
                "report": "",
                "pdf_path": "",
                "docx_path": "",
                "status": "error",
                "error": str(e)
            }


def create_deep_research_workflow() -> DeepResearchWorkflow:
    """
    工厂函数：创建深度调研工作流实例
    
    Returns:
        DeepResearchWorkflow 实例
    """
    return DeepResearchWorkflow()
