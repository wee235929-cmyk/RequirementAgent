"""
Orchestrator Agent - 编排代理

基于 LangGraph 实现的智能编排代理，负责协调整个系统的工作流程。

主要职责：
    1. 意图识别：分析用户输入，判断需要执行的任务类型
    2. 工作流路由：根据意图将请求路由到对应的处理节点
    3. 混合意图处理：支持多步骤工作流（如：搜索文档 → 生成需求）
    4. 会话管理：维护对话历史和上下文

支持的意图类型：
    - requirements_generation: 需求生成
    - rag_qa: 基于文档的问答
    - deep_research: 深度调研
    - general_chat: 通用对话
    - 混合意图: 如 rag_qa+requirements_generation

工作流架构：
    START → detect_intent → [route] → [processing_node] → END
                              ↓
                        mixed_intent_orchestrator (循环执行多步骤)
"""
import os
import sys
from pathlib import Path
from typing import TypedDict, Annotated, Sequence, Optional, List, Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langsmith import traceable

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import LLM_CONFIG, SYSTEM_PROMPTS, VALID_INTENTS, LANGFUSE_CONFIG, get_system_prompt
from integrations.langfuse import get_langfuse_handler, is_langfuse_enabled, create_session_handler
from requirements.roles import select_role_prompt
from memory import EnhancedConversationMemory
from rag import RAGIndexer, AgenticRAGChain, create_rag_system
from research import DeepResearchWorkflow, create_deep_research_workflow
from utils import get_logger
from tools.chart import MermaidChartTool, should_generate_chart

logger = get_logger(__name__)

# =============================================================================
# LangSmith Tracing Configuration (loaded from .env)
# =============================================================================
# Note: LANGCHAIN_TRACING_V2, LANGCHAIN_PROJECT, and LANGCHAIN_API_KEY
# are configured in .env file and loaded via dotenv in config.py

# 开发模式标志
DEV_MODE = os.getenv("RAAA_DEV_MODE", "false").lower() == "true"

# LangFuse 追踪面板 URL
LANGFUSE_DASHBOARD_URL = LANGFUSE_CONFIG.get("host", "https://cloud.langfuse.com")


# =============================================================================
# 状态定义
# =============================================================================

class AgentState(TypedDict):
    """
    编排代理的工作流状态
    
    此状态在 LangGraph 工作流的各个节点间传递，记录整个处理过程的数据。
    
    基础字段：
        messages: 对话消息列表
        user_input: 用户原始输入
        intent: 检测到的意图
        role: 用户角色（如 Requirements Analyst）
        role_prompt: 角色对应的提示词
        response: 最终响应内容
        uploaded_files: 上传的文件列表
        conversation_history: 对话历史摘要
        memory: 记忆数据
        focus: 需求聚焦点
        pdf_path: 生成的 PDF 路径
        docx_path: 生成的 Word 路径
        chain_of_thought: 思维链记录
        mermaid_chart: 生成的 Mermaid 图表
        
    混合意图字段：
        is_mixed_intent: 是否为混合意图
        intent_sequence: 意图执行序列
        current_intent_index: 当前执行到的意图索引
        intermediate_results: 中间步骤的结果
    """
    messages: Annotated[Sequence[BaseMessage], "The messages in the conversation"]
    user_input: str
    intent: str
    role: str
    role_prompt: str
    response: str
    uploaded_files: list
    conversation_history: str
    memory: Dict[str, Any]
    focus: str
    pdf_path: str
    docx_path: str
    chain_of_thought: List[str]
    mermaid_chart: str
    # 混合意图支持
    is_mixed_intent: bool
    intent_sequence: List[str]
    current_intent_index: int
    intermediate_results: Dict[str, Any]


# =============================================================================
# 编排代理类
# =============================================================================

class OrchestratorAgent:
    """
    编排代理主类
    
    基于 LangGraph 实现的智能编排代理，负责：
        - 意图识别与路由
        - 协调各功能模块（RAG、深度调研、需求生成）
        - 管理对话记忆
        - 支持混合意图的多步骤工作流
    
    Attributes:
        llm: LLM 实例
        memory: 对话记忆管理器
        rag_indexer: RAG 索引器
        rag_chain: RAG 问答链
        deep_research_workflow: 深度调研工作流
        graph: 编译后的 LangGraph 状态图
    """
    
    def __init__(self, memory: Optional[EnhancedConversationMemory] = None, 
                 rag_indexer: Optional[RAGIndexer] = None):
        """
        初始化编排代理
        
        Args:
            memory: 可选的对话记忆实例，不传则创建新实例
            rag_indexer: 可选的 RAG 索引器，不传则创建新实例
        """
        # 初始化 LLM
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=LLM_CONFIG["temperature"]
        )
        
        # LangFuse 追踪配置
        self._langfuse_enabled = is_langfuse_enabled()
        self._session_id = None
        if self._langfuse_enabled:
            logger.info("LangFuse tracing enabled for OrchestratorAgent")
        
        # 初始化对话记忆
        self.memory = memory if memory is not None else EnhancedConversationMemory()
        
        # 初始化 RAG 系统
        if rag_indexer is not None:
            self.rag_indexer = rag_indexer
            self.rag_chain = AgenticRAGChain(rag_indexer)
        else:
            self.rag_indexer, self.rag_chain = create_rag_system()
        
        # 初始化深度调研工作流
        self.deep_research_workflow = create_deep_research_workflow()
        
        # 意图检测提示模板 - 优先从模板加载
        self.intent_detection_prompt = ChatPromptTemplate.from_messages([
            ("system", get_system_prompt("intent_detection") or SYSTEM_PROMPTS["intent_detection"]),
            ("human", "User role: {role}\nUser input: {user_input}\nHas uploaded files: {has_files}")
        ])
        
        # 混合意图检测提示模板 - 优先从模板加载
        self.mixed_intent_detection_prompt = ChatPromptTemplate.from_messages([
            ("system", get_system_prompt("mixed_intent_detection") or SYSTEM_PROMPTS["mixed_intent_detection"]),
            ("human", "User role: {role}\nUser input: {user_input}\nHas uploaded files: {has_files}")
        ])
        
        # 通用对话提示模板 - 优先从模板加载
        self.general_chat_prompt = ChatPromptTemplate.from_messages([
            ("system", get_system_prompt("general_chat") or SYSTEM_PROMPTS["general_chat"]),
            ("human", "{user_input}")
        ])
        
        # 构建 LangGraph 工作流
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """
        构建 LangGraph 工作流状态图
        
        工作流结构：
            START → detect_intent → [条件路由] → [处理节点] → END
                                        ↓
                                  mixed_intent_orchestrator (循环)
        
        Returns:
            编译后的状态图
        """
        workflow = StateGraph(AgentState)
        
        # 添加处理节点
        workflow.add_node("detect_intent", self._detect_intent_node)
        workflow.add_node("requirements_generation", self._requirements_generation_node)
        workflow.add_node("rag_qa", self._rag_qa_node)
        workflow.add_node("deep_research", self._deep_research_node)
        workflow.add_node("general_chat", self._general_chat_node)
        workflow.add_node("mixed_intent_orchestrator", self._mixed_intent_orchestrator_node)
        
        # 设置入口边
        workflow.add_edge(START, "detect_intent")
        
        # 意图检测后的条件路由
        workflow.add_conditional_edges(
            "detect_intent",
            self._route_intent,
            {
                "requirements_generation": "requirements_generation",
                "rag_qa": "rag_qa",
                "deep_research": "deep_research",
                "general_chat": "general_chat",
                "mixed_intent": "mixed_intent_orchestrator"
            }
        )
        
        # 混合意图编排器的循环路由
        workflow.add_conditional_edges(
            "mixed_intent_orchestrator",
            self._route_mixed_intent,
            {"continue": "mixed_intent_orchestrator", "end": END}
        )
        
        # 单一意图处理节点直接结束
        workflow.add_edge("requirements_generation", END)
        workflow.add_edge("rag_qa", END)
        workflow.add_edge("deep_research", END)
        workflow.add_edge("general_chat", END)
        
        return workflow.compile()
    
    def _get_langfuse_callbacks(self, intent: str = None, role: str = None) -> List:
        """Get LangFuse callbacks if enabled."""
        if not self._langfuse_enabled:
            return []
        
        handler = create_session_handler(
            session_id=self._session_id,
            intent=intent,
            role=role,
        )
        return [handler] if handler else []
    
    def _invoke_with_langfuse(self, chain, inputs: dict, intent: str = None, role: str = None):
        """Invoke a chain with LangFuse callbacks if enabled."""
        callbacks = self._get_langfuse_callbacks(intent, role)
        if callbacks:
            return chain.invoke(inputs, config={"callbacks": callbacks})
        return chain.invoke(inputs)
    
    @traceable(name="detect_intent_node")
    def _detect_intent_node(self, state: AgentState) -> AgentState:
        """Detect user intent (single or mixed) and route to appropriate node."""
        has_files = "yes" if state.get("uploaded_files") else "no"
        
        # Use mixed intent detection prompt for more comprehensive detection
        chain = self.mixed_intent_detection_prompt | self.llm
        result = self._invoke_with_langfuse(
            chain,
            {"role": state["role"], "user_input": state["user_input"], "has_files": has_files},
            intent="intent_detection",
            role=state.get("role")
        )
        
        detected_intent = result.content.strip().lower()
        
        # Check if it's a mixed intent (contains '+')
        if '+' in detected_intent:
            # Parse the intent sequence
            intent_parts = [i.strip() for i in detected_intent.split('+')]
            # Validate all parts are valid intents
            valid_parts = [i for i in intent_parts if i in VALID_INTENTS and i != 'general_chat']
            
            if len(valid_parts) >= 2:
                # Valid mixed intent
                state["is_mixed_intent"] = True
                state["intent_sequence"] = valid_parts
                state["current_intent_index"] = 0
                state["intent"] = detected_intent
                state["intermediate_results"] = {}
                
                thought = f"Thought: Detected MIXED intent '{detected_intent}' -> workflow: {' -> '.join(valid_parts)}"
                state["chain_of_thought"].append(thought)
                logger.info(thought)
            else:
                # Fallback to single intent if mixed parsing fails
                state["is_mixed_intent"] = False
                state["intent_sequence"] = []
                state["intent"] = valid_parts[0] if valid_parts else "general_chat"
                thought = f"Thought: Mixed intent parsing failed, using single intent '{state['intent']}'"
                state["chain_of_thought"].append(thought)
                logger.info(thought)
        else:
            # Single intent
            state["is_mixed_intent"] = False
            state["intent_sequence"] = []
            state["intent"] = detected_intent if detected_intent in VALID_INTENTS else "general_chat"
            
            thought = f"Thought: Detected single intent '{state['intent']}' for input '{state['user_input'][:50]}...'"
            state["chain_of_thought"].append(thought)
            logger.info(thought)
        
        return state
    
    def _route_intent(self, state: AgentState) -> str:
        """Router function: routes to appropriate node based on intent."""
        if state.get("is_mixed_intent") and state.get("intent_sequence"):
            logger.info(f"Routing to mixed_intent_orchestrator for sequence: {state['intent_sequence']}")
            return "mixed_intent"
        
        intent = state["intent"]
        logger.info(f"Routing to: {intent}")
        return intent
    
    def _route_mixed_intent(self, state: AgentState) -> str:
        """Router for mixed intent orchestrator - continue or end."""
        current_idx = state.get("current_intent_index", 0)
        intent_sequence = state.get("intent_sequence", [])
        
        # Continue if there are more steps to execute OR if finalization hasn't run yet
        # Finalization runs when current_idx == len(intent_sequence) and response is empty
        if current_idx < len(intent_sequence):
            return "continue"
        
        # Check if finalization has already run (response is populated)
        if not state.get("response"):
            # Need one more iteration to finalize
            return "continue"
        
        return "end"
    
    @traceable(name="requirements_generation_node")
    def _requirements_generation_node(self, state: AgentState) -> AgentState:
        """Generate requirements based on user input and role."""
        try:
            thought = f"Thought: Generating requirements as {state['role']} for focus '{state.get('focus', state['user_input'])[:50]}...'"
            state["chain_of_thought"].append(thought)
            logger.info(thought)
            
            role_prompt = select_role_prompt(state["role"])
            
            formatted_prompt = role_prompt.format(
                focus=state.get("focus", state["user_input"]),
                history=state.get("conversation_history", "No previous conversation.")
            )
            state["role_prompt"] = formatted_prompt
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", formatted_prompt),
                ("human", "{user_input}")
            ])
            
            chain = prompt | self.llm
            result = self._invoke_with_langfuse(
                chain,
                {"user_input": state["user_input"]},
                intent="requirements_generation",
                role=state.get("role")
            )
            
            self.memory.add_message(state["user_input"], "user")
            self.memory.add_message(result.content, "assistant")
            
            if self.memory.is_mem0_enabled():
                self.memory.store_conversation_to_mem0(
                    state["user_input"], result.content,
                    metadata={"intent": "requirements_generation", "role": state["role"]}
                )
            
            state["response"] = f"**[Requirements Generation Mode - {state['role']}]**\n\n{result.content}"
            state["memory"] = {"summary": self.memory.get_summary()[:500]}
            
            # Determine if we should generate a diagram
            # IMPORTANT: Only generate diagrams when user EXPLICITLY requests one
            # Auto-generation is disabled to avoid unnecessary diagram creation
            chart_tool = MermaidChartTool()
            should_generate = False
            diagram_type = "sequence"
            
            # Only generate diagram if user explicitly requested it
            if should_generate_chart(state["user_input"]):
                thought = "Thought: User explicitly requested a diagram"
                state["chain_of_thought"].append(thought)
                logger.info(thought)
                should_generate = True
                diagram_type = chart_tool.detect_diagram_type(state["user_input"])
            # Note: Auto-detection logic (should_auto_generate_diagram) is intentionally NOT used here
            # to avoid generating diagrams when user didn't explicitly request them
            
            # Generate the diagram only if explicitly requested
            if should_generate:
                thought = f"Thought: Generating {diagram_type} Mermaid chart"
                state["chain_of_thought"].append(thought)
                logger.info(thought)
                
                mermaid_code = chart_tool.generate(result.content, diagram_type)
                state["mermaid_chart"] = mermaid_code
                state["response"] += f"\n\n---\n\n**📊 Generated {diagram_type.title()} Diagram:**\n\n{mermaid_code}"
                
                thought = f"Thought: Generated {diagram_type} diagram successfully"
                state["chain_of_thought"].append(thought)
                logger.info(thought)
            
            thought = f"Thought: Requirements generated successfully, {len(result.content)} chars"
            state["chain_of_thought"].append(thought)
            logger.info(thought)
            
        except Exception as e:
            error_thought = f"Thought: Error in requirements generation: {str(e)}"
            state["chain_of_thought"].append(error_thought)
            logger.error(error_thought)
            state["response"] = f"**[Error]** Failed to generate requirements: {str(e)}"
        
        return state
    
    @traceable(name="rag_qa_node")
    def _rag_qa_node(self, state: AgentState) -> AgentState:
        """Process RAG-based Q&A queries."""
        try:
            thought = f"Thought: Processing RAG Q&A for query '{state['user_input'][:50]}...'"
            state["chain_of_thought"].append(thought)
            logger.info(thought)
            
            index_stats = self.rag_indexer.get_index_stats()
            
            if not index_stats.get("has_vectorstore") or index_stats.get("indexed_files", 0) == 0:
                state["response"] = "**[RAG Q&A Mode]**\n\n⚠️ No documents have been indexed yet. Please upload and index documents in the sidebar first."
                state["chain_of_thought"].append("Thought: No documents indexed, returning early")
                return state
            
            history = state.get("conversation_history", "")
            
            result = self.rag_chain.invoke(
                query=state["user_input"],
                history=history,
                use_rewriting=True,
                use_graph=True,
                use_websearch=True
            )
            
            response_parts = ["**[RAG Q&A Mode]**\n"]
            response_parts.append(result.get("answer", "No answer generated."))
            
            if result.get("sources"):
                response_parts.append("\n\n---\n**📄 Document Sources:**")
                for i, src in enumerate(result["sources"][:3], 1):
                    response_parts.append(f"\n{i}. **{src['filename']}** (chunk {src['chunk']})")
                    response_parts.append(f"\n   > {src['preview'][:150]}...")
            
            if result.get("graph_entities"):
                entities = result["graph_entities"][:5]
                response_parts.append(f"\n\n**🔗 Related Entities:** {', '.join(entities)}")
            
            if result.get("web_search_triggered") and result.get("web_sources"):
                response_parts.append("\n\n**🌐 Web Search Results:**")
                for src in result["web_sources"][:2]:
                    response_parts.append(f"\n- [{src['title']}]({src['href']})")
            
            if result.get("query_restated"):
                response_parts.append("\n\n*Query was optimized for better retrieval.*")
            
            state["response"] = "".join(response_parts)
            state["memory"] = {"summary": self.memory.get_summary()[:500]}
            
            self.memory.add_message(state["user_input"], "user")
            self.memory.add_message(result.get("answer", ""), "assistant")
            
            if self.memory.is_mem0_enabled():
                self.memory.store_conversation_to_mem0(
                    state["user_input"], result.get("answer", ""),
                    metadata={"intent": "rag_qa", "sources_count": len(result.get("sources", []))}
                )
            
            thought = f"Thought: RAG Q&A completed, found {len(result.get('sources', []))} sources"
            state["chain_of_thought"].append(thought)
            logger.info(thought)
            
        except Exception as e:
            error_thought = f"Thought: Error in RAG Q&A: {str(e)}"
            state["chain_of_thought"].append(error_thought)
            logger.error(error_thought)
            state["response"] = f"**[RAG Q&A Mode]**\n\n❌ Error processing query: {str(e)}\n\nPlease ensure documents are properly indexed."
        
        return state
    
    @traceable(name="deep_research_node")
    def _deep_research_node(self, state: AgentState) -> AgentState:
        """Conduct deep research on a topic."""
        try:
            thought = f"Thought: Starting deep research for '{state['user_input'][:50]}...'"
            state["chain_of_thought"].append(thought)
            logger.info(thought)
            
            result = self.deep_research_workflow.invoke(state["user_input"])
            
            if result["status"] == "complete" and result.get("pdf_path"):
                tasks_summary = "\n".join([
                    f"  {i+1}. {t['task']}" 
                    for i, t in enumerate(result.get("tasks", []))
                ])
                
                report_files = f"📄 **PDF Report:** `{result['pdf_path']}`"
                if result.get("docx_path"):
                    report_files += f"\n📝 **Word Report:** `{result['docx_path']}`"
                
                response_parts = [
                    "**[Deep Research Mode]**\n",
                    f"✅ Research completed successfully!\n",
                    f"\n**Research Query:** {result['query']}\n",
                    f"\n**Research Tasks Completed:**\n{tasks_summary}\n",
                    f"\n---\n\n{result['report'][:2000]}{'...' if len(result.get('report', '')) > 2000 else ''}\n",
                    f"\n---\n\n{report_files}"
                ]
                
                state["response"] = "".join(response_parts)
                state["pdf_path"] = result["pdf_path"]
                state["docx_path"] = result.get("docx_path", "")
                
                thought = f"Thought: Deep research completed, {len(result.get('tasks', []))} tasks executed"
                state["chain_of_thought"].append(thought)
                
            elif result["status"] == "error":
                state["response"] = f"**[Deep Research Mode]**\n\n❌ Research failed: {result.get('error', 'Unknown error')}"
                state["pdf_path"] = ""
                state["docx_path"] = ""
                state["chain_of_thought"].append(f"Thought: Research failed - {result.get('error')}")
            else:
                state["response"] = f"**[Deep Research Mode]**\n\n⚠️ Research completed with status: {result['status']}"
                state["pdf_path"] = result.get("pdf_path", "")
                state["docx_path"] = result.get("docx_path", "")
            
            state["memory"] = {"summary": self.memory.get_summary()[:500]}
            self.memory.add_message(state["user_input"], "user")
            self.memory.add_message(state["response"], "assistant")
            
            if self.memory.is_mem0_enabled():
                self.memory.store_conversation_to_mem0(
                    state["user_input"], state["response"][:2000],
                    metadata={"intent": "deep_research", "has_pdf": bool(result.get("pdf_path"))}
                )
            
        except Exception as e:
            error_thought = f"Thought: Error in deep research: {str(e)}"
            state["chain_of_thought"].append(error_thought)
            logger.error(error_thought)
            state["response"] = f"**[Deep Research Mode]**\n\n❌ Error: {str(e)}"
            state["pdf_path"] = ""
        
        return state
    
    @traceable(name="general_chat_node")
    def _general_chat_node(self, state: AgentState) -> AgentState:
        """Handle general chat conversations."""
        try:
            thought = f"Thought: Processing general chat for '{state['user_input'][:50]}...'"
            state["chain_of_thought"].append(thought)
            logger.info(thought)
            
            chain = self.general_chat_prompt | self.llm
            result = self._invoke_with_langfuse(
                chain,
                {"user_input": state["user_input"]},
                intent="general_chat",
                role=state.get("role")
            )
            
            self.memory.add_message(state["user_input"], "user")
            self.memory.add_message(result.content, "assistant")
            
            if self.memory.is_mem0_enabled():
                self.memory.store_conversation_to_mem0(
                    state["user_input"], result.content,
                    metadata={"intent": "general_chat"}
                )
            
            state["response"] = result.content
            state["memory"] = {"summary": self.memory.get_summary()[:500]}
            
            thought = f"Thought: General chat completed, {len(result.content)} chars response"
            state["chain_of_thought"].append(thought)
            logger.info(thought)
            
        except Exception as e:
            error_thought = f"Thought: Error in general chat: {str(e)}"
            state["chain_of_thought"].append(error_thought)
            logger.error(error_thought)
            state["response"] = f"**[Error]** Failed to process request: {str(e)}"
        
        return state
    
    @traceable(name="mixed_intent_orchestrator_node")
    def _mixed_intent_orchestrator_node(self, state: AgentState) -> AgentState:
        """
        Orchestrate mixed intent workflows by executing intents in sequence.
        Each intent's output becomes context for the next intent.
        """
        intent_sequence = state.get("intent_sequence", [])
        current_idx = state.get("current_intent_index", 0)
        
        if current_idx >= len(intent_sequence):
            # All intents processed, finalize response
            return self._finalize_mixed_intent_response(state)
        
        current_intent = intent_sequence[current_idx]
        total_steps = len(intent_sequence)
        
        thought = f"Thought: Mixed intent step {current_idx + 1}/{total_steps}: Executing '{current_intent}'"
        state["chain_of_thought"].append(thought)
        logger.info(thought)
        
        try:
            # Execute the current intent and capture results
            if current_intent == "rag_qa":
                state = self._execute_rag_step(state)
            elif current_intent == "deep_research":
                state = self._execute_research_step(state)
            elif current_intent == "requirements_generation":
                state = self._execute_requirements_step(state)
            
            # Move to next intent
            state["current_intent_index"] = current_idx + 1
            
            thought = f"Thought: Completed step {current_idx + 1}/{total_steps}, intermediate result stored"
            state["chain_of_thought"].append(thought)
            logger.info(thought)
            
        except Exception as e:
            error_thought = f"Thought: Error in mixed intent step '{current_intent}': {str(e)}"
            state["chain_of_thought"].append(error_thought)
            logger.error(error_thought)
            state["intermediate_results"][f"{current_intent}_error"] = str(e)
            state["current_intent_index"] = current_idx + 1
        
        return state
    
    def _execute_rag_step(self, state: AgentState) -> AgentState:
        """Execute RAG search as part of mixed intent workflow."""
        thought = "Thought: [RAG Step] Searching documents for relevant context..."
        state["chain_of_thought"].append(thought)
        logger.info(thought)
        
        index_stats = self.rag_indexer.get_index_stats()
        
        if not index_stats.get("has_vectorstore") or index_stats.get("indexed_files", 0) == 0:
            state["intermediate_results"]["rag_qa"] = {
                "status": "no_documents",
                "context": "",
                "sources": [],
                "message": "No documents indexed. Proceeding with user query only."
            }
            return state
        
        history = state.get("conversation_history", "")
        result = self.rag_chain.invoke(
            query=state["user_input"],
            history=history,
            use_rewriting=True,
            use_graph=True,
            use_websearch=False  # Don't web search in mixed intent - let deep_research handle that
        )
        
        # Store RAG results for downstream intents
        state["intermediate_results"]["rag_qa"] = {
            "status": "success",
            "answer": result.get("answer", ""),
            "context": result.get("answer", ""),  # Use answer as context for next step
            "sources": result.get("sources", []),
            "graph_entities": result.get("graph_entities", [])
        }
        
        thought = f"Thought: [RAG Step] Found {len(result.get('sources', []))} sources"
        state["chain_of_thought"].append(thought)
        logger.info(thought)
        
        return state
    
    def _execute_research_step(self, state: AgentState) -> AgentState:
        """Execute deep research as part of mixed intent workflow."""
        thought = "Thought: [Research Step] Conducting deep research..."
        state["chain_of_thought"].append(thought)
        logger.info(thought)
        
        # Build research query with context from previous steps
        research_query = state["user_input"]
        if "rag_qa" in state.get("intermediate_results", {}):
            rag_context = state["intermediate_results"]["rag_qa"].get("context", "")
            if rag_context:
                research_query = f"{state['user_input']}\n\nContext from documents:\n{rag_context[:1000]}"
        
        result = self.deep_research_workflow.invoke(research_query)
        
        state["intermediate_results"]["deep_research"] = {
            "status": result.get("status", "unknown"),
            "report": result.get("report", ""),
            "tasks": result.get("tasks", []),
            "pdf_path": result.get("pdf_path", ""),
            "docx_path": result.get("docx_path", "")
        }
        
        if result.get("pdf_path"):
            state["pdf_path"] = result["pdf_path"]
        if result.get("docx_path"):
            state["docx_path"] = result["docx_path"]
        
        thought = f"Thought: [Research Step] Research completed with {len(result.get('tasks', []))} tasks"
        state["chain_of_thought"].append(thought)
        logger.info(thought)
        
        return state
    
    def _execute_requirements_step(self, state: AgentState) -> AgentState:
        """Execute requirements generation as part of mixed intent workflow."""
        thought = "Thought: [Requirements Step] Generating requirements based on gathered context..."
        state["chain_of_thought"].append(thought)
        logger.info(thought)
        
        # Build enhanced context from previous steps
        context_parts = []
        intermediate = state.get("intermediate_results", {})
        
        if "rag_qa" in intermediate:
            rag_result = intermediate["rag_qa"]
            if rag_result.get("context"):
                context_parts.append(f"**Document Analysis:**\n{rag_result['context'][:2000]}")
            if rag_result.get("sources"):
                sources_text = ", ".join([s.get("filename", "Unknown") for s in rag_result["sources"][:5]])
                context_parts.append(f"**Referenced Documents:** {sources_text}")
        
        if "deep_research" in intermediate:
            research_result = intermediate["deep_research"]
            if research_result.get("report"):
                context_parts.append(f"**Research Findings:**\n{research_result['report'][:2000]}")
        
        enhanced_context = "\n\n".join(context_parts) if context_parts else ""
        
        # Generate requirements with enhanced context
        role_prompt = select_role_prompt(state["role"])
        focus = state.get("focus", state["user_input"])
        
        if enhanced_context:
            focus = f"{focus}\n\n---\n**Gathered Context:**\n{enhanced_context}"
        
        formatted_prompt = role_prompt.format(
            focus=focus,
            history=state.get("conversation_history", "No previous conversation.")
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", formatted_prompt),
            ("human", "{user_input}")
        ])
        
        chain = prompt | self.llm
        result = self._invoke_with_langfuse(
            chain,
            {"user_input": state["user_input"]},
            intent="requirements_generation_step",
            role=state.get("role")
        )
        
        state["intermediate_results"]["requirements_generation"] = {
            "status": "success",
            "content": result.content,
            "context_used": bool(enhanced_context)
        }
        
        # Check for diagram generation - ONLY when user explicitly requests
        # Auto-generation is disabled to avoid unnecessary diagram creation
        chart_tool = MermaidChartTool()
        if should_generate_chart(state["user_input"]):
            diagram_type = chart_tool.detect_diagram_type(state["user_input"])
            mermaid_code = chart_tool.generate(result.content, diagram_type)
            state["intermediate_results"]["requirements_generation"]["mermaid_chart"] = mermaid_code
            state["mermaid_chart"] = mermaid_code
        # Note: Auto-detection logic (should_auto_generate_diagram) is intentionally NOT used here
        # to avoid generating diagrams when user didn't explicitly request them
        
        thought = f"Thought: [Requirements Step] Generated {len(result.content)} chars of requirements"
        state["chain_of_thought"].append(thought)
        logger.info(thought)
        
        return state
    
    def _finalize_mixed_intent_response(self, state: AgentState) -> AgentState:
        """Compile final response from all mixed intent steps."""
        intermediate = state.get("intermediate_results", {})
        intent_sequence = state.get("intent_sequence", [])
        
        thought = f"Thought: Finalizing mixed intent response for workflow: {' -> '.join(intent_sequence)}"
        state["chain_of_thought"].append(thought)
        logger.info(thought)
        
        response_parts = [f"**[Mixed Intent Workflow: {' → '.join(intent_sequence)}]**\n"]
        
        # Add RAG results if present
        if "rag_qa" in intermediate:
            rag = intermediate["rag_qa"]
            if rag.get("status") == "success":
                response_parts.append("\n---\n### 📄 Document Analysis\n")
                if rag.get("sources"):
                    response_parts.append(f"*Found {len(rag['sources'])} relevant document sections*\n")
                # Don't include full RAG answer if requirements follow - it's used as context
                if "requirements_generation" not in intent_sequence:
                    response_parts.append(f"\n{rag.get('answer', '')}\n")
            elif rag.get("status") == "no_documents":
                response_parts.append("\n⚠️ *No documents indexed - proceeding with query only*\n")
        
        # Add research results if present
        if "deep_research" in intermediate:
            research = intermediate["deep_research"]
            if research.get("status") == "complete":
                response_parts.append("\n---\n### 🔬 Research Findings\n")
                if research.get("tasks"):
                    response_parts.append(f"*Completed {len(research['tasks'])} research tasks*\n")
                # Truncate if requirements follow
                report = research.get("report", "")
                if "requirements_generation" in intent_sequence:
                    response_parts.append(f"\n{report[:1500]}{'...' if len(report) > 1500 else ''}\n")
                else:
                    response_parts.append(f"\n{report[:3000]}{'...' if len(report) > 3000 else ''}\n")
                if research.get("pdf_path"):
                    response_parts.append(f"\n📄 **Full Report:** `{research['pdf_path']}`\n")
        
        # Add requirements results if present (this is usually the final output)
        if "requirements_generation" in intermediate:
            req = intermediate["requirements_generation"]
            if req.get("status") == "success":
                response_parts.append(f"\n---\n### 📋 Generated Requirements ({state['role']})\n")
                if req.get("context_used"):
                    response_parts.append("*Requirements generated based on document analysis and research*\n")
                response_parts.append(f"\n{req.get('content', '')}\n")
                
                if req.get("mermaid_chart"):
                    response_parts.append(f"\n---\n**📊 Generated Diagram:**\n\n{req['mermaid_chart']}")
        
        state["response"] = "".join(response_parts)
        
        # Update memory
        self.memory.add_message(state["user_input"], "user")
        self.memory.add_message(state["response"], "assistant")
        state["memory"] = {"summary": self.memory.get_summary()[:500]}
        
        if self.memory.is_mem0_enabled():
            self.memory.store_conversation_to_mem0(
                state["user_input"], state["response"][:2000],
                metadata={"intent": "mixed_intent", "workflow": " -> ".join(intent_sequence)}
            )
        
        thought = f"Thought: Mixed intent workflow completed successfully"
        state["chain_of_thought"].append(thought)
        logger.info(thought)
        
        return state
    
    @traceable(name="orchestrator_process")
    def process(self, user_input: str, role: str, uploaded_files: list = None, focus: str = "") -> dict:
        """
        Process user input and return response with optional PDF path.
        
        Returns:
            dict with 'response', 'pdf_path', 'intent', 'chain_of_thought' keys
        """
        conversation_history = self.memory.get_summary()
        
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "user_input": user_input,
            "intent": "",
            "role": role,
            "role_prompt": "",
            "response": "",
            "uploaded_files": uploaded_files or [],
            "conversation_history": conversation_history,
            "memory": {},
            "focus": focus if focus else user_input,
            "pdf_path": "",
            "docx_path": "",
            "chain_of_thought": [],
            "mermaid_chart": "",
            # Mixed intent support
            "is_mixed_intent": False,
            "intent_sequence": [],
            "current_intent_index": 0,
            "intermediate_results": {}
        }
        
        final_state = self.graph.invoke(initial_state)
        
        return {
            "response": final_state["response"],
            "pdf_path": final_state.get("pdf_path", ""),
            "docx_path": final_state.get("docx_path", ""),
            "intent": final_state.get("intent", ""),
            "chain_of_thought": final_state.get("chain_of_thought", []),
            "mermaid_chart": final_state.get("mermaid_chart", "")
        }
    
    @traceable(name="orchestrator_invoke")
    def invoke(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invoke the orchestrator with a dictionary input.
        Accepts {'input': query} or {'input': query, 'role': role, ...}
        
        Args:
            input_dict: Dictionary with 'input' key (required) and optional keys:
                - role: User role (default: 'Requirements Analyst')
                - uploaded_files: List of uploaded files
                - focus: Focus area for requirements
        
        Returns:
            Dictionary with response, intent, chain_of_thought, etc.
        """
        query = input_dict.get("input", "")
        role = input_dict.get("role", "Requirements Analyst")
        uploaded_files = input_dict.get("uploaded_files", [])
        focus = input_dict.get("focus", "")
        
        return self.process(
            user_input=query,
            role=role,
            uploaded_files=uploaded_files,
            focus=focus
        )
    
    def detect_intent(self, user_input: str, role: str, has_files: bool = False) -> str:
        """
        Detect intent without processing - for streaming decisions.
        Returns single intent or mixed intent pattern (e.g., 'rag_qa+requirements_generation').
        """
        has_files_str = "yes" if has_files else "no"
        # Use mixed intent detection for comprehensive detection
        chain = self.mixed_intent_detection_prompt | self.llm
        result = chain.invoke({
            "role": role,
            "user_input": user_input,
            "has_files": has_files_str
        })
        detected_intent = result.content.strip().lower()
        
        # Validate the detected intent
        if '+' in detected_intent:
            # Mixed intent - validate all parts
            intent_parts = [i.strip() for i in detected_intent.split('+')]
            valid_parts = [i for i in intent_parts if i in VALID_INTENTS and i != 'general_chat']
            if len(valid_parts) >= 2:
                return '+'.join(valid_parts)
            elif valid_parts:
                return valid_parts[0]
            return "general_chat"
        
        return detected_intent if detected_intent in VALID_INTENTS else "general_chat"
    
    def is_mixed_intent(self, intent: str) -> bool:
        """Check if an intent string represents a mixed intent."""
        return '+' in intent and len(intent.split('+')) >= 2
    
    def stream_general_chat(self, user_input: str):
        """Stream response for general chat - yields chunks."""
        chain = self.general_chat_prompt | self.llm
        full_response = ""
        
        for chunk in chain.stream({"user_input": user_input}):
            if hasattr(chunk, 'content') and chunk.content:
                full_response += chunk.content
                yield chunk.content
        
        self.memory.add_message(user_input, "user")
        self.memory.add_message(full_response, "assistant")
    
    def get_memory(self) -> EnhancedConversationMemory:
        """Get the memory instance for external access."""
        return self.memory
    
    def get_rag_indexer(self) -> RAGIndexer:
        """Get the RAG indexer instance for external access."""
        return self.rag_indexer
    
    def clear_memory(self):
        """Clear conversation memory."""
        self.memory.clear_memory()
    
    def clear_rag_index(self):
        """Clear RAG index."""
        self.rag_indexer.clear_index()
