"""
Research agents: Planner, Searcher, and Writer for deep research workflow.
"""
import sys
import json
from pathlib import Path
from typing import TypedDict, List

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import LLM_CONFIG, SYSTEM_PROMPTS
from utils import get_logger

logger = get_logger(__name__)


class ResearchTask(TypedDict):
    """Single research task structure."""
    task: str
    priority: int
    completed: bool
    results: str


class ResearchState(TypedDict):
    """State for the research workflow."""
    query: str
    tasks: List[ResearchTask]
    current_task_index: int
    all_results: List[str]
    report: str
    pdf_path: str
    status: str
    error: str


class PlannerAgent:
    """
    Planner Agent that breaks down research queries into specific tasks.
    """
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=LLM_CONFIG["temperature"]
        )
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPTS["research_planner"]),
            ("human", "Research query: {query}")
        ])
        
        self.chain = self.prompt | self.llm | StrOutputParser()
    
    def plan(self, query: str) -> List[ResearchTask]:
        """Generate research tasks from a query."""
        try:
            result = self.chain.invoke({"query": query})
            
            json_str = result
            if "```json" in result:
                json_str = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                json_str = result.split("```")[1].split("```")[0]
            
            start_idx = json_str.find("[")
            end_idx = json_str.rfind("]") + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = json_str[start_idx:end_idx]
            
            tasks_data = json.loads(json_str)
            
            tasks = []
            for t in tasks_data:
                tasks.append(ResearchTask(
                    task=t.get("task", ""),
                    priority=t.get("priority", 3),
                    completed=False,
                    results=""
                ))
            
            tasks.sort(key=lambda x: x["priority"])
            
            logger.info(f"Planner generated {len(tasks)} tasks for query: {query[:50]}...")
            return tasks
            
        except Exception as e:
            logger.error(f"Planner failed: {e}")
            return [ResearchTask(
                task=f"General research on: {query}",
                priority=1,
                completed=False,
                results=""
            )]


class SearcherAgent:
    """
    Searcher Agent that executes research tasks using web search.
    """
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=0.3
        )
        
        self.web_search = None
        self._init_search()
        
        self.synthesis_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPTS["research_synthesizer"]),
            ("human", "Research task: {task}\n\nSearch results:\n{search_results}")
        ])
        
        self.synthesis_chain = self.synthesis_prompt | self.llm | StrOutputParser()
    
    def _init_search(self):
        """Initialize web search tool."""
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            self.web_search = DDGS()
            logger.info("SearcherAgent: DuckDuckGo search initialized")
        except Exception as e:
            logger.warning(f"SearcherAgent: Web search not available: {e}")
    
    def search(self, task: str, max_results: int = 5) -> str:
        """Execute a search task and return synthesized results."""
        if not self.web_search:
            return f"[Search unavailable] Task: {task}"
        
        try:
            search_results = list(self.web_search.text(task, max_results=max_results))
            
            if not search_results:
                return f"No results found for: {task}"
            
            formatted_results = []
            for i, r in enumerate(search_results, 1):
                formatted_results.append(
                    f"[{i}] {r.get('title', 'No title')}\n"
                    f"    {r.get('body', 'No description')}\n"
                    f"    Source: {r.get('href', 'Unknown')}"
                )
            
            search_text = "\n\n".join(formatted_results)
            
            synthesis = self.synthesis_chain.invoke({
                "task": task,
                "search_results": search_text
            })
            
            logger.info(f"SearcherAgent completed task: {task[:50]}...")
            return synthesis
            
        except Exception as e:
            logger.error(f"Search failed for task '{task}': {e}")
            return f"Search error for task: {task}. Error: {str(e)}"


class WriterAgent:
    """
    Writer Agent that synthesizes research results into a coherent report.
    """
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=LLM_CONFIG["temperature"]
        )
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPTS["report_writer"]),
            ("human", "Research Query: {query}\n\nResearch Results:\n{results}")
        ])
        
        self.chain = self.prompt | self.llm | StrOutputParser()
    
    def write(self, query: str, results: List[str]) -> str:
        """Generate a research report from collected results."""
        try:
            combined_results = "\n\n---\n\n".join([
                f"**Finding {i+1}:**\n{r}" for i, r in enumerate(results)
            ])
            
            report = self.chain.invoke({
                "query": query,
                "results": combined_results
            })
            
            logger.info(f"WriterAgent generated report for: {query[:50]}...")
            return report
            
        except Exception as e:
            logger.error(f"Writer failed: {e}")
            return f"# Research Report\n\nError generating report: {str(e)}\n\n## Raw Results\n\n" + "\n\n".join(results)
