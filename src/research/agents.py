"""
Research Agents - 深度调研代理模块

本模块包含深度调研工作流所需的四个核心代理：
    - QueryAnalyzerAgent: 查询分析扩写代理，对用户查询进行意图识别、概念提取和扩写
    - PlannerAgent: 任务规划代理，将调研问题拆解为可执行的子任务
    - SearcherAgent: 搜索代理，并行执行网络搜索并综合结果
    - WriterAgent: 写作代理，将搜索结果整合为结构化研究报告

核心数据结构：
    - ResearchTask: 单个调研任务的结构定义
    - ResearchState: 工作流状态，在各代理间传递
"""
import sys
import json
from pathlib import Path
from typing import TypedDict, List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 添加项目路径以支持模块导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from config import LLM_CONFIG, SYSTEM_PROMPTS, DEEP_RESEARCH_CONFIG, get_research_prompt
from utils import get_logger
from integrations.langfuse import get_langfuse_handler, is_langfuse_enabled

logger = get_logger(__name__)


# =============================================================================
# 辅助函数
# =============================================================================

def _get_langfuse_callbacks(tags: List[str], operation: Optional[str] = None) -> list:
    """
    获取 LangFuse 回调处理器（如果已启用）
    
    Args:
        tags: 基础标签列表，如 ["raaa", "research", "planner"]
        operation: 可选的操作名称，会添加为 "op:xxx" 标签
        
    Returns:
        包含回调处理器的列表，如果未启用则返回空列表
    """
    if not is_langfuse_enabled():
        return []
    
    all_tags = tags.copy()
    if operation:
        all_tags.append(f"op:{operation}")
    
    handler = get_langfuse_handler(tags=all_tags)
    return [handler] if handler else []


# =============================================================================
# 数据结构定义
# =============================================================================

class ResearchTask(TypedDict):
    """
    单个调研任务的数据结构
    
    Attributes:
        task: 任务描述（可搜索的具体问题）
        priority: 优先级（1-5，1为最高）
        category: 任务类别（overview/technical/case_studies 等）
        completed: 是否已完成
        results: 搜索结果的综合摘要
        images: 相关图片列表
    """
    task: str
    priority: int
    category: str
    completed: bool
    results: str
    images: list


class ResearchState(TypedDict):
    """
    深度调研工作流的状态结构
    
    此状态在工作流的各个节点间传递，记录整个调研过程的数据。
    
    Attributes:
        query: 用户原始调研问题
        expanded_query: 经过分析扩写后的调研问题（英文，用于搜索优化）
        query_analysis: Query Analyzer 的完整分析结果（JSON 字典）
        tasks: 拆解后的任务列表
        current_task_index: 当前执行到的任务索引
        all_results: 所有任务的综合结果
        all_images: 收集的所有图片
        all_tables: 收集的所有表格数据
        report: 生成的研究报告
        pdf_path: PDF 文件路径
        docx_path: Word 文件路径
        status: 当前状态（started/query_analyzed/planning_complete/searching_complete/writing_complete/complete/error）
        error: 错误信息
    """
    query: str
    expanded_query: str
    query_analysis: dict
    tasks: List[ResearchTask]
    current_task_index: int
    all_results: List[str]
    all_images: List[dict]
    all_tables: List[dict]
    report: str
    pdf_path: str
    docx_path: str
    status: str
    error: str


# =============================================================================
# 代理类定义
# =============================================================================

class QueryAnalyzerAgent:
    """
    查询分析扩写代理
    
    在 Planner 之前对用户的原始查询进行分析和扩写，包括：
        - 意图识别：判断用户想要什么类型的调研
        - 关键概念提取：提取核心实体和术语
        - 查询扩写：补充背景信息、同义词、相关维度
        - 语言检测：标注用户输入语言
    
    扩写后的查询（英文）将用于后续的任务规划和搜索，
    以提升搜索覆盖面和结果质量。
    """
    
    _LANGFUSE_TAGS = ["raaa", "research", "query_analyzer"]
    
    def __init__(self):
        """初始化查询分析代理，配置 LLM 和提示模板"""
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=0.3
        )
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", get_research_prompt("query_analyzer") or SYSTEM_PROMPTS["research_query_analyzer"]),
            ("human", "Research query: {query}")
        ])
        
        self.chain = self.prompt | self.llm | StrOutputParser()
    
    def analyze(self, query: str) -> Dict[str, Any]:
        """
        分析并扩写用户的调研查询
        
        Args:
            query: 用户的原始调研问题
            
        Returns:
            包含以下字段的字典：
            - original_query: 原始查询
            - detected_language: 检测到的语言代码
            - intent: 调研意图描述
            - key_concepts: 关键概念列表
            - expanded_query: 扩写后的英文查询
            - search_dimensions: 搜索维度列表
            - suggested_focus_areas: 建议的重点方向
        """
        try:
            callbacks = _get_langfuse_callbacks(self._LANGFUSE_TAGS, "analyze")
            config = {"callbacks": callbacks} if callbacks else {}
            result = self.chain.invoke({"query": query}, config=config) if callbacks else self.chain.invoke({"query": query})
            
            json_str = self._extract_json(result)
            analysis = json.loads(json_str)
            
            # 确保必要字段存在
            analysis.setdefault("original_query", query)
            analysis.setdefault("expanded_query", query)
            analysis.setdefault("detected_language", "en")
            analysis.setdefault("key_concepts", [])
            analysis.setdefault("search_dimensions", [])
            analysis.setdefault("suggested_focus_areas", [])
            analysis.setdefault("intent", "")
            
            logger.info(
                f"QueryAnalyzer: '{query[:50]}...' -> expanded to: '{analysis['expanded_query'][:80]}...'"
            )
            logger.info(
                f"QueryAnalyzer: detected_language={analysis['detected_language']}, "
                f"key_concepts={analysis['key_concepts'][:5]}, "
                f"dimensions={len(analysis['search_dimensions'])}"
            )
            
            return analysis
            
        except Exception as e:
            logger.error(f"QueryAnalyzer failed: {e}")
            # 降级处理：返回原始查询作为扩写结果
            return {
                "original_query": query,
                "detected_language": "en",
                "intent": "general research",
                "key_concepts": [],
                "expanded_query": query,
                "search_dimensions": [],
                "suggested_focus_areas": []
            }
    
    def _extract_json(self, text: str) -> str:
        """
        从 LLM 输出中提取 JSON 对象
        
        Args:
            text: LLM 的原始输出
            
        Returns:
            提取出的 JSON 字符串
        """
        json_str = text
        
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0]
        
        start_idx = json_str.find("{")
        end_idx = json_str.rfind("}") + 1
        if start_idx != -1 and end_idx > start_idx:
            json_str = json_str[start_idx:end_idx]
        
        return json_str


class PlannerAgent:
    """
    任务规划代理
    
    负责将用户的调研问题拆解为 8-12 个具体、可搜索的子任务。
    每个任务会被分配优先级和类别，以便后续有序执行。
    
    任务类别包括：
        - overview: 概述与定义
        - historical: 历史背景
        - technical: 技术分析
        - case_studies: 案例研究
        - challenges: 挑战与解决方案
        - future_outlook: 未来展望
    """
    
    # LangFuse 追踪标签
    _LANGFUSE_TAGS = ["raaa", "research", "planner"]
    
    def __init__(self):
        """初始化规划代理，配置 LLM 和提示模板"""
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=LLM_CONFIG["temperature"]
        )
        
        # 优先从模板加载研究规划提示词
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", get_research_prompt("planner") or SYSTEM_PROMPTS["research_planner"]),
            ("human", "Research query: {query}")
        ])
        
        self.chain = self.prompt | self.llm | StrOutputParser()
    
    def plan(self, query: str) -> List[ResearchTask]:
        """
        将调研问题拆解为多个可执行的搜索任务
        
        Args:
            query: 用户的调研问题
            
        Returns:
            按优先级排序的任务列表
        """
        try:
            # 调用 LLM 生成任务列表
            callbacks = _get_langfuse_callbacks(self._LANGFUSE_TAGS, "plan")
            config = {"callbacks": callbacks} if callbacks else {}
            result = self.chain.invoke({"query": query}, config=config) if callbacks else self.chain.invoke({"query": query})
            
            # 解析 JSON 输出（支持 markdown 代码块格式）
            json_str = self._extract_json(result)
            tasks_data = json.loads(json_str)
            
            # 构建任务列表
            tasks = [
                ResearchTask(
                    task=t.get("task", ""),
                    priority=t.get("priority", 3),
                    category=t.get("category", "general"),
                    completed=False,
                    results="",
                    images=[]
                )
                for t in tasks_data
            ]
            
            # 按优先级排序（1 最高）
            tasks.sort(key=lambda x: x["priority"])
            
            logger.info(f"Planner generated {len(tasks)} tasks for query: {query[:50]}...")
            return tasks
            
        except Exception as e:
            logger.error(f"Planner failed: {e}")
            # 降级处理：返回单个通用任务
            return [ResearchTask(
                task=f"General research on: {query}",
                priority=1,
                category="general",
                completed=False,
                results="",
                images=[]
            )]
    
    def _extract_json(self, text: str) -> str:
        """
        从 LLM 输出中提取 JSON 数组
        
        支持以下格式：
            - ```json [...] ```
            - ``` [...] ```
            - 直接的 JSON 数组
            
        Args:
            text: LLM 的原始输出
            
        Returns:
            提取出的 JSON 字符串
        """
        json_str = text
        
        # 处理 markdown 代码块
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0]
        
        # 提取 JSON 数组部分
        start_idx = json_str.find("[")
        end_idx = json_str.rfind("]") + 1
        if start_idx != -1 and end_idx > start_idx:
            json_str = json_str[start_idx:end_idx]
        
        return json_str


class SubSearchAgent:
    """
    并行搜索子代理
    
    每个实例独立处理一个搜索任务，支持多线程并发执行。
    使用线程本地存储确保 DDGS 客户端的线程安全。
    
    搜索策略：
        1. 通用搜索：获取主要结果
        2. 学术搜索：从 arXiv、IEEE 等获取论文
        3. 文档搜索：从官方文档站点获取权威信息
        4. 图片搜索：获取相关图片素材
    """
    
    # 线程本地存储，用于存放每个线程独立的 DDGS 实例
    _thread_local = threading.local()
    
    def __init__(self, agent_id: int):
        """
        初始化子搜索代理
        
        Args:
            agent_id: 代理编号，用于日志追踪
        """
        self.agent_id = agent_id
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=0.3  # 较低温度以获得更稳定的综合结果
        )
        
        # 优先从模板加载研究综合提示词
        self.synthesis_prompt = ChatPromptTemplate.from_messages([
            ("system", get_research_prompt("synthesizer") or SYSTEM_PROMPTS["research_synthesizer"]),
            ("human", "Original user query: {original_query}\n\nResearch task: {task}\n\nSearch results:\n{search_results}\n\nIMPORTANT: Write the synthesis in the SAME language as the 'Original user query' above.")
        ])
        self.synthesis_chain = self.synthesis_prompt | self.llm | StrOutputParser()
    
    def _get_search_client(self):
        """
        获取线程本地的 DDGS 搜索客户端
        
        使用线程本地存储确保每个线程有独立的客户端实例，
        避免多线程并发时的竞态条件。
        
        Returns:
            DDGS 实例，如果初始化失败则返回 None
        """
        if not hasattr(self._thread_local, 'ddgs'):
            try:
                # 优先使用 ddgs 包，回退到 duckduckgo_search
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS
                self._thread_local.ddgs = DDGS()
            except Exception as e:
                logger.warning(f"SubSearchAgent-{self.agent_id}: Search init failed: {e}")
                self._thread_local.ddgs = None
        return self._thread_local.ddgs
    
    def execute_task(self, task: ResearchTask, task_index: int,
                     max_text_results: int = 10, max_images: int = 2,
                     timeout: int = 30, original_query: str = "") -> Dict[str, Any]:
        """
        执行单个调研任务的完整搜索流程
        
        流程：
            1. 执行通用网络搜索
            2. 执行学术资源搜索（arXiv、IEEE 等）
            3. 执行官方文档搜索
            4. 去重并格式化结果
            5. 调用 LLM 综合搜索结果
            6. 搜索相关图片
        
        Args:
            task: 要执行的调研任务
            task_index: 任务在列表中的索引
            max_text_results: 每次搜索的最大结果数
            max_images: 最大图片数
            timeout: 超时时间（秒）- 注意：当前未实际使用
            original_query: 用户原始查询（用于确定输出语言）
            
        Returns:
            包含 synthesis、images、success 等字段的结果字典
        """
        result = {
            "task_index": task_index,
            "task": task["task"],
            "category": task.get("category", "general"),
            "synthesis": "",
            "images": [],
            "success": False,
            "error": None
        }
        
        ddgs = self._get_search_client()
        if not ddgs:
            result["error"] = "Search client unavailable"
            result["synthesis"] = f"[Search unavailable] Task: {task['task']}"
            return result
        
        try:
            all_results = []
            
            # === 主搜索（带降级重试机制） ===
            primary_search_ok = False
            try:
                search_results = list(ddgs.text(task["task"], max_results=max_text_results))
                all_results.extend(search_results)
                primary_search_ok = True
            except Exception as primary_e:
                logger.warning(f"SubSearchAgent-{self.agent_id}: Primary search failed: {primary_e}")
                
                # 降级策略1：重新初始化搜索客户端后重试
                try:
                    self._thread_local.ddgs = None
                    ddgs = self._get_search_client()
                    if ddgs:
                        search_results = list(ddgs.text(task["task"], max_results=max_text_results))
                        all_results.extend(search_results)
                        primary_search_ok = True
                        logger.info(f"SubSearchAgent-{self.agent_id}: Retry with new client succeeded")
                except Exception:
                    pass
                
                # 降级策略2：简化查询后重试（取前60个字符，去掉复杂语法）
                if not primary_search_ok:
                    try:
                        import re as _re
                        simplified_query = _re.sub(r'[^\w\s]', ' ', task["task"])[:60].strip()
                        if simplified_query:
                            ddgs = self._get_search_client()
                            if ddgs:
                                search_results = list(ddgs.text(simplified_query, max_results=max_text_results))
                                all_results.extend(search_results)
                                primary_search_ok = True
                                logger.info(f"SubSearchAgent-{self.agent_id}: Simplified query search succeeded: {simplified_query[:30]}...")
                    except Exception:
                        pass
                
                # 降级策略3：仅使用关键词搜索
                if not primary_search_ok:
                    try:
                        keywords = " ".join(task["task"].split()[:5])
                        ddgs = self._get_search_client()
                        if ddgs:
                            search_results = list(ddgs.text(keywords, max_results=5))
                            all_results.extend(search_results)
                            primary_search_ok = True
                            logger.info(f"SubSearchAgent-{self.agent_id}: Keyword-only search succeeded: {keywords}")
                    except Exception as kw_e:
                        logger.warning(f"SubSearchAgent-{self.agent_id}: All search retries failed: {kw_e}")
            
            # === 学术搜索（已有降级：单个失败不影响整体） ===
            academic_queries = [
                f'{task["task"]} site:arxiv.org OR site:scholar.google.com OR site:researchgate.net',
                f'{task["task"]} site:ieee.org OR site:acm.org OR site:springer.com',
                f'{task["task"]} research paper PDF filetype:pdf'
            ]
            
            for aq in academic_queries[:2]:
                try:
                    academic_results = list(ddgs.text(aq, max_results=3))
                    all_results.extend(academic_results)
                except Exception:
                    pass
            
            # === 文档搜索（已有降级） ===
            doc_queries = [
                f'{task["task"]} site:docs.microsoft.com OR site:developer.mozilla.org OR site:docs.oracle.com',
                f'{task["task"]} official documentation guide',
                f'{task["task"]} site:github.com README OR documentation'
            ]
            
            for dq in doc_queries[:2]:
                try:
                    doc_results = list(ddgs.text(dq, max_results=3))
                    all_results.extend(doc_results)
                except Exception:
                    pass
            
            # === 去重 ===
            seen_urls = set()
            unique_results = []
            for r in all_results:
                url = r.get('href', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(r)
            
            # === 无搜索结果时的降级处理：使用 LLM 基于自身知识生成内容 ===
            if not unique_results:
                logger.warning(f"SubSearchAgent-{self.agent_id}: No search results for task {task_index + 1}, using LLM knowledge fallback")
                try:
                    fallback_prompt = ChatPromptTemplate.from_messages([
                        ("system", "You are a knowledgeable research assistant. When web search is unavailable, provide a comprehensive analysis based on your training knowledge. Clearly note that this content is based on general knowledge rather than live search results. Write in the same language as the user's original query."),
                        ("human", "Original user query: {original_query}\n\nResearch task: {task}\n\nNo web search results were available. Please provide a detailed analysis of this topic based on your knowledge. Include key concepts, important developments, and notable references where possible. Clearly indicate this is based on general knowledge.")
                    ])
                    fallback_chain = fallback_prompt | self.llm | StrOutputParser()
                    fallback_synthesis = fallback_chain.invoke({
                        "task": task["task"],
                        "original_query": original_query or task["task"]
                    })
                    result["synthesis"] = fallback_synthesis
                    result["success"] = True
                    result["error"] = "search_unavailable_llm_fallback"
                    return result
                except Exception as fallback_e:
                    logger.warning(f"SubSearchAgent-{self.agent_id}: LLM fallback also failed: {fallback_e}")
                    result["synthesis"] = f"No results found for: {task['task']}"
                    result["success"] = True
                    return result
            
            # === 格式化搜索结果 ===
            formatted_results = []
            for i, r in enumerate(unique_results, 1):
                url = r.get('href', 'Unknown')
                source_type = "General"
                if any(s in url for s in ['arxiv.org', 'scholar.google', 'researchgate', 'ieee.org', 'acm.org', 'springer']):
                    source_type = "Academic/Paper"
                elif any(s in url for s in ['docs.', 'developer.', 'documentation', 'github.com']):
                    source_type = "Official Docs"
                
                formatted_results.append(
                    f"[{i}] [{source_type}] {r.get('title', 'No title')}\n"
                    f"    {r.get('body', 'No description')}\n"
                    f"    Source: {url}"
                )
            
            search_text = "\n\n".join(formatted_results)
            
            # === 调用 LLM 综合搜索结果 ===
            callbacks = _get_langfuse_callbacks(
                ["raaa", "research", "subsearch", f"agent:{self.agent_id}"], 
                "synthesis"
            )
            config = {"callbacks": callbacks} if callbacks else {}
            invoke_params = {"task": task["task"], "search_results": search_text, "original_query": original_query or task["task"]}
            synthesis = self.synthesis_chain.invoke(
                invoke_params,
                config=config
            ) if callbacks else self.synthesis_chain.invoke(
                invoke_params
            )
            result["synthesis"] = synthesis
            
            # === 图片搜索（失败不影响整体） ===
            try:
                image_query = task["task"][:100] if len(task["task"]) > 100 else task["task"]
                image_results = list(ddgs.images(
                    image_query,
                    max_results=max_images,
                    safesearch="moderate"
                ))
                
                for img in image_results:
                    result["images"].append({
                        "url": img.get("image", ""),
                        "thumbnail": img.get("thumbnail", ""),
                        "title": img.get("title", "Image"),
                        "source": img.get("source", "Unknown"),
                        "query": image_query,
                        "category": result["category"],
                        "task_index": task_index
                    })
            except Exception as img_e:
                logger.warning(f"SubSearchAgent-{self.agent_id}: Image search failed: {img_e}")
            
            result["success"] = True
            logger.info(f"SubSearchAgent-{self.agent_id}: Completed task {task_index + 1}: {task['task'][:40]}...")
            
        except Exception as e:
            # === 最终降级：整个搜索流程失败，尝试 LLM 知识兜底 ===
            logger.error(f"SubSearchAgent-{self.agent_id}: Task {task_index + 1} failed: {e}")
            try:
                fallback_prompt = ChatPromptTemplate.from_messages([
                    ("system", "You are a knowledgeable research assistant. Web search failed. Provide analysis based on your training knowledge. Write in the same language as the user's original query."),
                    ("human", "Original user query: {original_query}\n\nResearch task: {task}\n\nWeb search encountered an error. Please provide what you know about this topic based on your training knowledge.")
                ])
                fallback_chain = fallback_prompt | self.llm | StrOutputParser()
                fallback_synthesis = fallback_chain.invoke({
                    "task": task["task"],
                    "original_query": original_query or task["task"]
                })
                result["synthesis"] = fallback_synthesis
                result["success"] = True
                result["error"] = f"search_failed_llm_fallback: {str(e)}"
            except Exception as fallback_e:
                result["error"] = str(e)
                result["synthesis"] = f"Search error for task: {task['task']}. Error: {str(e)}"
                logger.error(f"SubSearchAgent-{self.agent_id}: LLM fallback also failed: {fallback_e}")
        
        return result


class SearcherAgent:
    """
    搜索代理（主代理）
    
    负责协调多个 SubSearchAgent 并行执行搜索任务。
    采用线程池实现并发，显著提升搜索效率。
    
    配置项（来自 DEEP_RESEARCH_CONFIG）：
        - parallel_searchers: 并行子代理数量（默认 4）
        - search_results_per_task: 每任务搜索结果数（默认 10）
        - images_per_task: 每任务图片数（默认 2）
        - search_timeout: 搜索超时时间（默认 30秒）
    """
    
    # LangFuse 追踪标签
    _LANGFUSE_TAGS = ["raaa", "research", "searcher"]
    
    def __init__(self):
        """初始化搜索代理，创建子代理池"""
        # 从配置读取参数
        self.num_parallel = DEEP_RESEARCH_CONFIG.get("parallel_searchers", 4)
        self.max_text_results = DEEP_RESEARCH_CONFIG.get("search_results_per_task", 10)
        self.max_images = DEEP_RESEARCH_CONFIG.get("images_per_task", 2)
        self.timeout = DEEP_RESEARCH_CONFIG.get("search_timeout", 30)
        
        # 创建子代理池
        self.sub_agents = [SubSearchAgent(i) for i in range(self.num_parallel)]
        
        # 配置 LLM（用于向后兼容的单任务搜索）
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=0.3
        )
        
        # 优先从模板加载研究综合提示词
        self.synthesis_prompt = ChatPromptTemplate.from_messages([
            ("system", get_research_prompt("synthesizer") or SYSTEM_PROMPTS["research_synthesizer"]),
            ("human", "Original user query: {original_query}\n\nResearch task: {task}\n\nSearch results:\n{search_results}\n\nIMPORTANT: Write the synthesis in the SAME language as the 'Original user query' above.")
        ])
        self.synthesis_chain = self.synthesis_prompt | self.llm | StrOutputParser()
        
        # 初始化搜索客户端（用于向后兼容）
        self.web_search = None
        self._init_search()
        
        logger.info(f"SearcherAgent initialized with {self.num_parallel} parallel sub-agents")
    
    def _init_search(self):
        """初始化搜索客户端（用于向后兼容的单任务搜索）"""
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            self.web_search = DDGS()
        except Exception as e:
            logger.warning(f"SearcherAgent: Web search not available: {e}")
    
    def search_tasks_parallel(self, tasks: List[ResearchTask], original_query: str = "") -> List[Dict[str, Any]]:
        """
        并行执行多个调研任务
        
        使用线程池将任务分发给子代理并行执行，结果按原始顺序返回。
        
        Args:
            tasks: 要执行的任务列表
            original_query: 用户原始查询（用于确定输出语言）
            
        Returns:
            结果列表，每个元素包含 synthesis、images、success 等字段
        """
        if not tasks:
            return []
        
        results = [None] * len(tasks)
        
        logger.info(f"SearcherAgent: Starting parallel execution of {len(tasks)} tasks with {self.num_parallel} workers")
        
        with ThreadPoolExecutor(max_workers=self.num_parallel) as executor:
            # 提交所有任务到线程池
            future_to_task = {}
            for idx, task in enumerate(tasks):
                # 轮询分配子代理
                agent = self.sub_agents[idx % self.num_parallel]
                future = executor.submit(
                    agent.execute_task,
                    task,
                    idx,
                    self.max_text_results,
                    self.max_images,
                    self.timeout,
                    original_query
                )
                future_to_task[future] = idx
            
            # 收集结果（按完成顺序）
            for future in as_completed(future_to_task):
                task_idx = future_to_task[future]
                try:
                    result = future.result(timeout=self.timeout + 10)
                    results[task_idx] = result
                except Exception as e:
                    logger.error(f"SearcherAgent: Task {task_idx + 1} execution error: {e}")
                    # 失败时返回错误结果
                    results[task_idx] = {
                        "task_index": task_idx,
                        "task": tasks[task_idx]["task"],
                        "category": tasks[task_idx].get("category", "general"),
                        "synthesis": f"Task execution failed: {str(e)}",
                        "images": [],
                        "success": False,
                        "error": str(e)
                    }
        
        successful = sum(1 for r in results if r and r.get("success"))
        logger.info(f"SearcherAgent: Parallel execution complete. {successful}/{len(tasks)} tasks successful")
        
        return results
    
    # =========================================================================
    # 以下方法为向后兼容保留，当前工作流不使用
    # =========================================================================
    
    def search_images(self, query: str, max_results: int = 3) -> List[dict]:
        """[向后兼容] 单独搜索图片"""
        if not self.web_search:
            return []
        
        try:
            image_results = list(self.web_search.images(
                query, 
                max_results=max_results,
                safesearch="moderate"
            ))
            
            return [
                {
                    "url": img.get("image", ""),
                    "thumbnail": img.get("thumbnail", ""),
                    "title": img.get("title", "Image"),
                    "source": img.get("source", "Unknown"),
                    "query": query
                }
                for img in image_results
            ]
            
        except Exception as e:
            logger.warning(f"Image search failed for '{query}': {e}")
            return []
    
    def search(self, task: str, max_results: int = 10) -> str:
        """[向后兼容] 执行单个搜索任务"""
        if not self.web_search:
            return f"[Search unavailable] Task: {task}"
        
        try:
            search_results = list(self.web_search.text(task, max_results=max_results))
            
            if not search_results:
                return f"No results found for: {task}"
            
            formatted_results = [
                f"[{i}] {r.get('title', 'No title')}\n"
                f"    {r.get('body', 'No description')}\n"
                f"    Source: {r.get('href', 'Unknown')}"
                for i, r in enumerate(search_results, 1)
            ]
            
            search_text = "\n\n".join(formatted_results)
            
            # 调用 LLM 综合结果
            callbacks = _get_langfuse_callbacks(self._LANGFUSE_TAGS, "synthesis")
            config = {"callbacks": callbacks} if callbacks else {}
            invoke_params = {"task": task, "search_results": search_text, "original_query": task}
            synthesis = self.synthesis_chain.invoke(
                invoke_params,
                config=config
            ) if callbacks else self.synthesis_chain.invoke(
                invoke_params
            )
            
            return synthesis
            
        except Exception as e:
            logger.error(f"Search failed for task '{task}': {e}")
            return f"Search error for task: {task}. Error: {str(e)}"
    
    def search_with_images(self, task: str, max_text_results: int = 10, max_images: int = 2) -> dict:
        """[向后兼容] 执行综合搜索（文本+图片）"""
        synthesis = self.search(task, max_results=max_text_results)
        image_query = task[:100] if len(task) > 100 else task
        images = self.search_images(image_query, max_results=max_images)
        
        return {"synthesis": synthesis, "images": images}


class WriterAgent:
    """
    写作代理
    
    负责将搜索结果整合为结构化的研究报告。
    支持两种生成模式：
        1. 一次性生成：内容较少时直接生成完整报告
        2. 分段生成：内容较多时按章节逐段生成，确保完整性
    
    报告结构：
        - Executive Summary（执行摘要）
        - Introduction（引言）
        - Background and Literature Review（背景与文献综述）
        - Current State Analysis（现状分析）
        - Technical Analysis（技术分析）
        - Case Studies（案例研究）
        - Comparative Analysis（对比分析）
        - Challenges and Solutions（挑战与解决方案）
        - Future Outlook（未来展望）
        - Conclusions（结论）
        - References（参考文献）
    """
    
    # LangFuse 追踪标签
    _LANGFUSE_TAGS = ["raaa", "research", "writer"]
    
    # 报告章节定义：(section_id, section_title, section_instructions)
    REPORT_SECTIONS = [
        ("executive_summary", "Executive Summary", "Write 500-800 words in NARRATIVE PARAGRAPHS summarizing objectives, methodology, key findings, and recommendations. NO bullet points. Include a ```mermaid mindmap``` showing research structure."),
        ("introduction", "1. Introduction", "Write 1000-1500 words in flowing paragraphs covering background, research questions, methodology, and report structure. Include a ```mermaid flowchart``` showing research methodology."),
        ("literature_review", "2. Background and Literature Review", "Write 2000-3000 words in academic prose on historical context, theoretical framework, and prior research. Cite sources with [Author, Year]. Include a ```mermaid timeline``` showing field evolution."),
        ("current_state", "3. Current State Analysis", "Write 3000-4000 words analyzing current trends and key players in NARRATIVE form. Include ONE table for key statistics. Add a ```mermaid pie``` chart for market distribution."),
        ("technical_analysis", "4. Technical Analysis", "Write 3000-4000 words on methodologies and technologies in paragraphs. Include a ```mermaid flowchart``` for system architecture and a ```mermaid sequenceDiagram``` for component interactions."),
        ("case_studies", "5. Case Studies", "Write 2000-3000 words with 2-3 detailed case studies in NARRATIVE form. Include a ```mermaid stateDiagram-v2``` showing implementation lifecycle."),
        ("comparative_analysis", "6. Comparative Analysis", "Write 2000-3000 words comparing approaches in prose. Include ONE comparison table. Add a ```mermaid quadrantChart``` for positioning analysis."),
        ("challenges", "7. Challenges and Solutions", "Write 2000-2500 words discussing challenges and solutions in flowing paragraphs. Include a ```mermaid flowchart LR``` showing challenge-solution mappings."),
        ("future_outlook", "8. Future Outlook", "Write 1500-2000 words on trends and predictions in narrative style. Include a ```mermaid gantt``` chart for projected timeline/roadmap."),
        ("conclusions", "9. Conclusions", "Write 800-1000 words summarizing findings and recommendations in paragraphs. NO bullet points."),
        ("references", "References", """Format ALL references in standard academic citation style (APA/IEEE). Use numbered format:

[1] Author, A. A., & Author, B. B. (Year). Title of article. *Journal Name*, Volume(Issue), pages. https://doi.org/xxx
[2] Author, C. C. (Year). *Title of book*. Publisher.
[3] Organization Name. (Year). Report title. Retrieved from https://url
[4] Author, D. D. (Year, Month Day). Article title. *Website Name*. https://url

IMPORTANT: Every [Author, Year] citation in the text MUST have a numbered entry here. Do NOT use paragraph format - use numbered list format.
IMPORTANT: Do NOT translate any reference entries. Keep all author names, titles, journal names, and URLs in their ORIGINAL language.""")
    ]
    
    def __init__(self):
        """初始化写作代理，配置 LLM 和提示模板"""
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=LLM_CONFIG["temperature"],
            max_tokens=8000  # 较大的 token 限制以支持长报告生成
        )
        
        # 分段生成的提示模板
        self.section_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a professional academic report writer. Write the specified section of a research report.

LANGUAGE RULE (CRITICAL - HIGHEST PRIORITY):
- Detect the language of the user's research query (the "Research Topic").
- Write the section in the SAME language as the user's query.
  - If the query is in Chinese, write the section in Chinese (headings, body text, all content).
  - If the query is in English, write the section in English.
  - For any other language, match that language.
- EXCEPTION: The "References" section MUST keep all citation entries (author names, paper titles, journal names, URLs) in their ORIGINAL language. Do NOT translate references.
- Technical terms and proper nouns commonly kept in English (e.g., API, HTTP, Python, Transformer) may remain in English.

CRITICAL WRITING STYLE:
- Write in NARRATIVE PARAGRAPHS, not bullet points or lists
- Each paragraph should be 150-250 words with smooth transitions between ideas
- Use academic prose style - explain concepts, relationships, and findings in flowing text
- Only use bullet points sparingly for truly enumerable items (max 1-2 short lists per section)
- Tables should be rare - only include if data truly requires tabular format

CITATION REQUIREMENTS:
- Include inline citations [Author, Year] for all factual claims
- Every citation must correspond to a source in the research findings

MERMAID DIAGRAMS (include 1-2 per section, use DIVERSE types):
Use ```mermaid code blocks with CORRECT syntax:
- flowchart TD/LR: Process flows, decision trees, architectures
- sequenceDiagram: Component interactions, API flows
- classDiagram: Object relationships, data models
- stateDiagram-v2: State machines, lifecycle stages
- erDiagram: Entity relationships, database schemas
- pie: Market share, distributions
- gantt: Timelines, roadmaps
- mindmap: Concept hierarchies
- timeline: Historical events, milestones

MERMAID SYNTAX RULES (CRITICAL - follow EXACTLY or diagram will fail):
- Use ONLY simple ASCII alphanumeric text in node labels. NO special characters: no (), no "", no :, no ;, no &, no %, no #
- Node IDs must be simple identifiers: A, B, C1, nodeA (no spaces, no special chars)
- Node labels in brackets: A[Simple Label] - keep under 40 characters
- Use <br/> for line breaks (NEVER <br> without closing slash)
- Use --> for arrows (NEVER -> in flowchart)
- Edge labels: A -->|label| B (no special chars in label)
- For flowchart: start with "flowchart TD" or "flowchart LR" (not "graph")
- For sequenceDiagram: participant names must be single words, use "participant A as Long Name"
- For pie: "Label" : number (quotes around label)
- For stateDiagram-v2: state names must be single words, use [*] for start/end
- NEVER use HTML tags except <br/>
- NEVER use markdown formatting inside Mermaid code
- IMPORTANT: ALL text inside Mermaid diagrams MUST be in English, regardless of the report language. Chinese/CJK characters will cause rendering failures. Translate all labels, titles, axis names to English inside Mermaid code blocks

FORMAT:
- Use ## for section header, ### for subsections
- Write the COMPLETE section without truncation
- Ensure professional, academic tone throughout"""),
            ("human", """Research Topic: {query}

Section to Write: {section_title}
Instructions: {section_instructions}

Research Findings to Incorporate:
{results}

IMPORTANT: Write this section in the SAME language as the Research Topic above. If the topic is in Chinese, write in Chinese. If in English, write in English.

Write the complete {section_title} section in narrative paragraph style with proper citations:""")
        ])
        
        self.section_chain = self.section_prompt | self.llm | StrOutputParser()
        
        # 一次性生成的提示模板
        # 优先从模板加载报告写作提示词
        self.full_prompt = ChatPromptTemplate.from_messages([
            ("system", get_research_prompt("report_writer") or SYSTEM_PROMPTS["report_writer"]),
            ("human", "Research Query: {query}\n\nResearch Results:\n{results}\n\nIMPORTANT: Write the entire report in the SAME language as the Research Query above. If the query is in Chinese, write in Chinese. If in English, write in English. The References section must keep all citation entries in their ORIGINAL language - do NOT translate references.")
        ])
        self.full_chain = self.full_prompt | self.llm | StrOutputParser()
    
    def write(self, query: str, results: List[str]) -> str:
        """
        生成研究报告
        
        根据内容量自动选择生成模式：
            - 内容 > 50000 字符：使用分段生成
            - 生成结果 < 15000 字符：补充使用分段生成
            
        Args:
            query: 调研问题
            results: 搜索结果列表
            
        Returns:
            完整的研究报告（Markdown 格式）
        """
        try:
            # 合并所有搜索结果
            combined_results = "\n\n---\n\n".join([
                f"**Finding {i+1}:**\n{r}" for i, r in enumerate(results)
            ])
            
            # 内容过多时使用分段生成
            if len(combined_results) > 50000:
                logger.info("WriterAgent: Using section-by-section generation for large content")
                return self._write_by_sections(query, combined_results)
            
            # 尝试一次性生成
            callbacks = _get_langfuse_callbacks(self._LANGFUSE_TAGS, "full_report")
            config = {"callbacks": callbacks} if callbacks else {}
            report = self.full_chain.invoke(
                {"query": query, "results": combined_results},
                config=config
            ) if callbacks else self.full_chain.invoke(
                {"query": query, "results": combined_results}
            )
            
            # 报告过短时补充分段生成
            if len(report) < 15000:
                logger.warning("WriterAgent: Report seems short, supplementing with section generation")
                return self._write_by_sections(query, combined_results)
            
            logger.info(f"WriterAgent generated report ({len(report)} chars) for: {query[:50]}...")
            return report
            
        except Exception as e:
            logger.error(f"Writer failed: {e}")
            return self._generate_fallback_report(query, results, str(e))
    
    def _write_by_sections(self, query: str, combined_results: str) -> str:
        """
        分段生成报告
        
        逐章节调用 LLM 生成内容，确保长报告的完整性。
        每个章节独立生成，失败不会影响其他章节。
        
        Args:
            query: 调研问题
            combined_results: 合并后的搜索结果
            
        Returns:
            完整的研究报告
        """
        report_parts = [f"# {query}\n"]
        
        # 限制传入 LLM 的结果长度，避免超出 token 限制
        truncated_results = combined_results[:30000]
        
        for section_id, section_title, section_instructions in self.REPORT_SECTIONS:
            try:
                logger.info(f"WriterAgent: Generating section '{section_title}'...")
                
                # 调用 LLM 生成章节内容
                callbacks = _get_langfuse_callbacks(self._LANGFUSE_TAGS, f"section_{section_id}")
                invoke_params = {
                    "query": query,
                    "section_title": section_title,
                    "section_instructions": section_instructions,
                    "results": truncated_results
                }
                
                if callbacks:
                    section_content = self.section_chain.invoke(invoke_params, config={"callbacks": callbacks})
                else:
                    section_content = self.section_chain.invoke(invoke_params)
                
                # 确保章节有标题
                if not section_content.strip().startswith("#"):
                    section_content = f"# {section_title}\n\n{section_content}"
                
                report_parts.append(section_content)
                report_parts.append("\n\n")
                
            except Exception as e:
                logger.warning(f"WriterAgent: Section '{section_title}' failed: {e}")
                report_parts.append(f"# {section_title}\n\n[Section generation failed: {str(e)}]\n\n")
        
        full_report = "".join(report_parts)
        logger.info(f"WriterAgent: Section-by-section report complete ({len(full_report)} chars)")
        return full_report
    
    def _generate_fallback_report(self, query: str, results: List[str], error: str) -> str:
        """
        生成降级报告
        
        当正常报告生成失败时，直接将原始搜索结果组织为简单报告。
        
        Args:
            query: 调研问题
            results: 搜索结果列表
            error: 错误信息（用于记录，当前未在报告中显示）
            
        Returns:
            简化的研究报告
        """
        parts = [
            f"# {query}\n\n",
            "*Note: Automated report generation encountered an issue. Below are the raw research findings.*\n\n",
            "---\n\n"
        ]
        
        for i, result in enumerate(results):
            parts.append(f"## Finding {i + 1}\n\n{result}\n\n---\n\n")
        
        return "".join(parts)
