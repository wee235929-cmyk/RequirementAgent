"""
Deep Research Workflow using LangGraph.
Orchestrates Planner → Searcher → Writer agents.
"""
import sys
from pathlib import Path
from typing import Dict, Any

from langgraph.graph import StateGraph, START, END

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils import get_logger
from modules.research.agents import PlannerAgent, SearcherAgent, WriterAgent, ResearchState
from modules.research.pdf_generator import PDFReportGenerator

logger = get_logger(__name__)


class DeepResearchWorkflow:
    """
    LangGraph-based workflow for deep research.
    Orchestrates Planner → Searcher → Writer agents.
    """
    
    def __init__(self):
        self.planner = PlannerAgent()
        self.searcher = SearcherAgent()
        self.writer = WriterAgent()
        self.pdf_generator = PDFReportGenerator()
        
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the research workflow graph."""
        workflow = StateGraph(ResearchState)
        
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("searcher", self._searcher_node)
        workflow.add_node("writer", self._writer_node)
        workflow.add_node("pdf_generator", self._pdf_generator_node)
        
        workflow.add_edge(START, "planner")
        workflow.add_edge("planner", "searcher")
        workflow.add_conditional_edges(
            "searcher",
            self._should_continue_searching,
            {
                "continue": "searcher",
                "write": "writer"
            }
        )
        workflow.add_edge("writer", "pdf_generator")
        workflow.add_edge("pdf_generator", END)
        
        return workflow.compile()
    
    def _planner_node(self, state: ResearchState) -> ResearchState:
        """Execute the planner agent."""
        logger.info(f"[Planner] Planning research for: {state['query'][:50]}...")
        
        try:
            tasks = self.planner.plan(state["query"])
            state["tasks"] = tasks
            state["current_task_index"] = 0
            state["all_results"] = []
            state["status"] = "planning_complete"
            logger.info(f"[Planner] Generated {len(tasks)} tasks")
        except Exception as e:
            state["error"] = f"Planning failed: {str(e)}"
            state["status"] = "error"
            logger.error(f"[Planner] Error: {e}")
        
        return state
    
    def _searcher_node(self, state: ResearchState) -> ResearchState:
        """Execute the searcher agent for the current task."""
        current_idx = state["current_task_index"]
        tasks = state["tasks"]
        
        if current_idx >= len(tasks):
            state["status"] = "searching_complete"
            return state
        
        current_task = tasks[current_idx]
        logger.info(f"[Searcher] Executing task {current_idx + 1}/{len(tasks)}: {current_task['task'][:50]}...")
        
        try:
            result = self.searcher.search(current_task["task"])
            
            tasks[current_idx]["completed"] = True
            tasks[current_idx]["results"] = result
            state["tasks"] = tasks
            
            state["all_results"].append(f"**Task: {current_task['task']}**\n\n{result}")
            
            state["current_task_index"] = current_idx + 1
            state["status"] = "searching"
            
            logger.info(f"[Searcher] Task {current_idx + 1} completed")
            
        except Exception as e:
            logger.error(f"[Searcher] Error on task {current_idx + 1}: {e}")
            state["current_task_index"] = current_idx + 1
        
        return state
    
    def _should_continue_searching(self, state: ResearchState) -> str:
        """Determine if we should continue searching or move to writing."""
        current_idx = state["current_task_index"]
        total_tasks = len(state["tasks"])
        
        if current_idx < total_tasks:
            return "continue"
        else:
            return "write"
    
    def _writer_node(self, state: ResearchState) -> ResearchState:
        """Execute the writer agent to generate the report."""
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
        """Generate PDF from the report."""
        logger.info("[PDF] Generating PDF report...")
        
        try:
            if state.get("report"):
                pdf_path = self.pdf_generator.generate(
                    title=f"Research Report: {state['query'][:50]}",
                    content=state["report"]
                )
                state["pdf_path"] = pdf_path
                state["status"] = "complete"
                logger.info(f"[PDF] Report saved to: {pdf_path}")
            else:
                state["error"] = "No report content to generate PDF"
                state["status"] = "error"
        except Exception as e:
            state["error"] = f"PDF generation failed: {str(e)}"
            state["status"] = "error"
            logger.error(f"[PDF] Error: {e}")
        
        return state
    
    def invoke(self, query: str, progress_callback=None) -> Dict[str, Any]:
        """
        Execute the full research workflow.
        
        Args:
            query: Research query/topic
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary with report, pdf_path, and status
        """
        initial_state = ResearchState(
            query=query,
            tasks=[],
            current_task_index=0,
            all_results=[],
            report="",
            pdf_path="",
            status="started",
            error=""
        )
        
        try:
            if progress_callback:
                progress_callback("Starting research workflow...")
            
            final_state = self.graph.invoke(initial_state)
            
            return {
                "query": query,
                "tasks": final_state.get("tasks", []),
                "report": final_state.get("report", ""),
                "pdf_path": final_state.get("pdf_path", ""),
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
                "status": "error",
                "error": str(e)
            }


def create_deep_research_workflow() -> DeepResearchWorkflow:
    """Factory function to create the deep research workflow."""
    return DeepResearchWorkflow()
