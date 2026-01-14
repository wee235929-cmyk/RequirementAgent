"""Orchestrator Agent with LangGraph workflow and LangSmith tracing."""
import os
import sys
from pathlib import Path
from typing import TypedDict, Annotated, Sequence, Optional, List, Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langsmith import traceable

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LLM_CONFIG, SYSTEM_PROMPTS, VALID_INTENTS
from modules.roles import select_role_prompt
from modules.memory import EnhancedConversationMemory
from rag import RAGIndexer, AgenticRAGChain, create_rag_system
from modules.research import DeepResearchWorkflow, create_deep_research_workflow
from utils import get_logger
from tools.chart import MermaidChartTool, should_generate_chart, should_auto_generate_diagram

logger = get_logger(__name__)

# =============================================================================
# LangSmith Tracing Configuration (loaded from .env)
# =============================================================================
# Note: LANGCHAIN_TRACING_V2, LANGCHAIN_PROJECT, and LANGCHAIN_API_KEY
# are configured in .env file and loaded via dotenv in config.py

# Development mode flag
DEV_MODE = os.getenv("RAAA_DEV_MODE", "false").lower() == "true"

class AgentState(TypedDict):
    """State for the orchestrator LangGraph workflow."""
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
    chain_of_thought: List[str]
    mermaid_chart: str

class OrchestratorAgent:
    def __init__(self, memory: Optional[EnhancedConversationMemory] = None, rag_indexer: Optional[RAGIndexer] = None):
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=LLM_CONFIG["temperature"]
        )
        
        self.memory = memory if memory is not None else EnhancedConversationMemory()
        
        if rag_indexer is not None:
            self.rag_indexer = rag_indexer
            self.rag_chain = AgenticRAGChain(rag_indexer)
        else:
            self.rag_indexer, self.rag_chain = create_rag_system()
        
        self.deep_research_workflow = create_deep_research_workflow()
        
        self.intent_detection_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPTS["intent_detection"]),
            ("human", "User role: {role}\nUser input: {user_input}\nHas uploaded files: {has_files}")
        ])
        
        self.general_chat_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPTS["general_chat"]),
            ("human", "{user_input}")
        ])
        
        self.graph = self._build_graph()
    
    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        workflow.add_node("detect_intent", self._detect_intent_node)
        workflow.add_node("requirements_generation", self._requirements_generation_node)
        workflow.add_node("rag_qa", self._rag_qa_node)
        workflow.add_node("deep_research", self._deep_research_node)
        workflow.add_node("general_chat", self._general_chat_node)
        
        workflow.add_edge(START, "detect_intent")
        
        workflow.add_conditional_edges(
            "detect_intent",
            self._route_intent,
            {
                "requirements_generation": "requirements_generation",
                "rag_qa": "rag_qa",
                "deep_research": "deep_research",
                "general_chat": "general_chat"
            }
        )
        
        workflow.add_edge("requirements_generation", END)
        workflow.add_edge("rag_qa", END)
        workflow.add_edge("deep_research", END)
        workflow.add_edge("general_chat", END)
        
        return workflow.compile()
    
    @traceable(name="detect_intent_node")
    def _detect_intent_node(self, state: AgentState) -> AgentState:
        """Detect user intent and route to appropriate node."""
        has_files = "yes" if state.get("uploaded_files") else "no"
        
        chain = self.intent_detection_prompt | self.llm
        result = chain.invoke({
            "role": state["role"],
            "user_input": state["user_input"],
            "has_files": has_files
        })
        
        intent = result.content.strip().lower()
        state["intent"] = intent if intent in VALID_INTENTS else "general_chat"
        
        # Record chain of thought
        thought = f"Thought: Detected intent '{state['intent']}' for input '{state['user_input'][:50]}...', routing to {state['intent']}_node"
        state["chain_of_thought"].append(thought)
        logger.info(thought)
        
        return state
    
    def _route_intent(self, state: AgentState) -> str:
        """Router function: routes to appropriate node based on intent."""
        intent = state["intent"]
        logger.info(f"Routing to: {intent}")
        return intent
    
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
            result = chain.invoke({
                "user_input": state["user_input"]
            })
            
            self.memory.add_message(state["user_input"], "user")
            self.memory.add_message(result.content, "assistant")
            
            state["response"] = f"**[Requirements Generation Mode - {state['role']}]**\n\n{result.content}"
            state["memory"] = {"summary": self.memory.get_summary()[:500]}
            
            # Determine if we should generate a diagram
            chart_tool = MermaidChartTool()
            should_generate = False
            diagram_type = "sequence"
            
            # Priority 1: User explicitly requested a diagram
            if should_generate_chart(state["user_input"]):
                thought = "Thought: User explicitly requested a diagram"
                state["chain_of_thought"].append(thought)
                logger.info(thought)
                should_generate = True
                diagram_type = chart_tool.detect_diagram_type(state["user_input"])
            else:
                # Priority 2: Auto-detect if requirements content suggests a diagram would help
                auto_generate, auto_type = should_auto_generate_diagram(result.content)
                if auto_generate:
                    thought = f"Thought: Requirements content suggests a {auto_type} diagram would be helpful"
                    state["chain_of_thought"].append(thought)
                    logger.info(thought)
                    should_generate = True
                    diagram_type = auto_type
            
            # Generate the diagram if needed
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
                use_restatement=True,
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
                
                response_parts = [
                    "**[Deep Research Mode]**\n",
                    f"✅ Research completed successfully!\n",
                    f"\n**Research Query:** {result['query']}\n",
                    f"\n**Research Tasks Completed:**\n{tasks_summary}\n",
                    f"\n---\n\n{result['report'][:2000]}{'...' if len(result.get('report', '')) > 2000 else ''}\n",
                    f"\n---\n\n📄 **PDF Report Generated:** `{result['pdf_path']}`"
                ]
                
                state["response"] = "".join(response_parts)
                state["pdf_path"] = result["pdf_path"]
                
                thought = f"Thought: Deep research completed, {len(result.get('tasks', []))} tasks executed"
                state["chain_of_thought"].append(thought)
                
            elif result["status"] == "error":
                state["response"] = f"**[Deep Research Mode]**\n\n❌ Research failed: {result.get('error', 'Unknown error')}"
                state["pdf_path"] = ""
                state["chain_of_thought"].append(f"Thought: Research failed - {result.get('error')}")
            else:
                state["response"] = f"**[Deep Research Mode]**\n\n⚠️ Research completed with status: {result['status']}"
                state["pdf_path"] = result.get("pdf_path", "")
            
            state["memory"] = {"summary": self.memory.get_summary()[:500]}
            self.memory.add_message(state["user_input"], "user")
            self.memory.add_message(state["response"], "assistant")
            
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
            result = chain.invoke({"user_input": state["user_input"]})
            
            self.memory.add_message(state["user_input"], "user")
            self.memory.add_message(result.content, "assistant")
            
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
            "chain_of_thought": [],
            "mermaid_chart": ""
        }
        
        final_state = self.graph.invoke(initial_state)
        
        return {
            "response": final_state["response"],
            "pdf_path": final_state.get("pdf_path", ""),
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
        """Detect intent without processing - for streaming decisions."""
        has_files_str = "yes" if has_files else "no"
        chain = self.intent_detection_prompt | self.llm
        result = chain.invoke({
            "role": role,
            "user_input": user_input,
            "has_files": has_files_str
        })
        intent = result.content.strip().lower()
        return intent if intent in VALID_INTENTS else "general_chat"
    
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
    
    def get_rag_chain(self) -> AgenticRAGChain:
        """Get the RAG chain instance for external access."""
        return self.rag_chain
    
    def clear_memory(self):
        """Clear conversation memory."""
        self.memory.clear_memory()
    
    def clear_rag_index(self):
        """Clear RAG index."""
        self.rag_indexer.clear_index()
