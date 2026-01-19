"""
Centralized configuration for the Requirements Analysis Agent Assistant.
Contains all constants, settings, and configuration values.

Supports Jinja2 templates for prompts when available, with fallback to hardcoded prompts.
"""
import os
from pathlib import Path
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Template Management (Optional - requires Jinja2)
# =============================================================================
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

def _get_template_loader():
    """Get template loader if Jinja2 is available."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from templates import get_template_loader
        return get_template_loader()
    except (ImportError, Exception):
        return None

def get_available_roles() -> List[str]:
    """
    Get list of available roles. 
    Prefers Jinja templates if available, falls back to hardcoded roles.
    """
    loader = _get_template_loader()
    if loader:
        roles = loader.get_available_roles()
        if roles:
            return roles
    return list(ROLE_PROMPT_TEMPLATES.keys())

def get_role_prompt(role_name: str, history: str = "", focus: str = "") -> str:
    """
    Get a role prompt by name.
    Prefers Jinja templates if available, falls back to hardcoded prompts.
    
    Args:
        role_name: Name of the role
        history: Conversation history
        focus: Focus area for requirements
        
    Returns:
        Rendered role prompt string
    """
    loader = _get_template_loader()
    if loader:
        try:
            return loader.get_role_prompt(role_name, history=history, focus=focus)
        except FileNotFoundError:
            pass
    
    # Fallback to hardcoded prompts
    template = ROLE_PROMPT_TEMPLATES.get(role_name, ROLE_PROMPT_TEMPLATES.get(DEFAULT_ROLE))
    return template.format(history=history, focus=focus)

# =============================================================================
# Project Paths
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
REPORTS_DIR = PROJECT_ROOT / "reports"
RAG_INDEX_DIR = PROJECT_ROOT / "rag_index"

# Ensure directories exist
REPORTS_DIR.mkdir(exist_ok=True)
RAG_INDEX_DIR.mkdir(exist_ok=True)

# =============================================================================
# LLM Configuration
# =============================================================================
LLM_CONFIG = {
    "model": "deepseek-chat",
    "api_key": os.getenv("DEEPSEEK_API_KEY"),
    "base_url": os.getenv("DEEPSEEK_BASE_URL"),
    "temperature": 0.7,
}

# =============================================================================
# Embedding Configuration
# =============================================================================
EMBEDDING_CONFIG = {
    "model_name": "sentence-transformers/all-MiniLM-L6-v2",
    "model_kwargs": {"device": "cpu"},
    "encode_kwargs": {"normalize_embeddings": True},
}

# =============================================================================
# RAG Configuration
# =============================================================================
RAG_CONFIG = {
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "top_k_results": 5,
    "similarity_threshold": 0.7,
}

# =============================================================================
# User Roles
# =============================================================================
USER_ROLES = [
    "Requirements Analyst",
    "Software Architect",
    "Software Developer",
    "Test Engineer",
]

DEFAULT_ROLE = "Requirements Analyst"

# =============================================================================
# Role Prompt Templates
# =============================================================================
ROLE_PROMPT_TEMPLATES = {
    "Requirements Analyst": """You are an experienced business analyst focused on identifying business objectives, user processes, stakeholder needs, and potential risks.

Based on the following conversation history and focus {focus}, analyze and generate or refine software requirements to ensure coverage of both functional and non-functional aspects.

History: {history}

Please provide clear, structured requirements that conform to ISO 29148 and IEEE-830 standards.""",

    "Software Architect": """You are a senior software architect focused on system design, architecture patterns, scalability, maintainability, and technical decisions.

Based on the following conversation history and focus {focus}, analyze the requirements and provide architectural recommendations, design patterns, and technical specifications.

History: {history}

Please provide comprehensive architectural guidance that ensures system quality and long-term maintainability.""",

    "Software Developer": """You are an experienced software developer focused on implementation details, code structure, APIs, data models, and development best practices.

Based on the following conversation history and focus {focus}, analyze the requirements and provide implementation guidance, technical specifications, and development recommendations.

History: {history}

Please provide practical development guidance that ensures code quality and efficient implementation.""",

    "Test Engineer": """You are a senior test engineer focused on test scenarios, boundary conditions, error handling, and quality assurance.

Based on the following conversation history and focus {focus}, generate test cases and verify the consistency of requirements.

History: {history}

Please provide comprehensive test cases, quality metrics, and validation strategies to ensure software quality.""",
}

# =============================================================================
# Supported File Types
# =============================================================================
SUPPORTED_FILE_TYPES = [
    "pdf", "docx", "doc", "pptx", "ppt", 
    "xlsx", "xls", "txt", "png", "jpg", "jpeg", "json"
]

# =============================================================================
# System Prompts
# =============================================================================
SYSTEM_PROMPTS = {
    "general_chat": """You are a helpful Requirements Analysis Agent Assistant.

You help project managers with:
- Software requirements generation (ISO 29148, IEEE-830)
- Document-based Q&A (RAG)
- Deep domain research

Respond helpfully to the user's message. If they seem unclear about what you can do, 
explain your capabilities.""",

    "intent_detection": """You are an intent classifier for a Requirements Analysis Agent Assistant.

Analyze the user's input and classify it into ONE of these intents:
1. requirements_generation - User wants to generate, refine, or discuss software requirements
2. rag_qa - User asks questions about uploaded documents or wants document-based answers
3. deep_research - User requests in-depth research on a specific domain or topic
4. general_chat - General conversation, greetings, or unclear intent

Respond with ONLY the intent name (requirements_generation, rag_qa, deep_research, or general_chat).
No explanation needed.""",

    "mixed_intent_detection": """You are an intent classifier for a Requirements Analysis Agent Assistant.

Analyze the user's input and determine if it involves MULTIPLE intents that should be executed in sequence.

Available intents:
1. rag_qa - User asks questions about uploaded documents or wants document-based answers
2. deep_research - User requests in-depth research on a specific domain or topic  
3. requirements_generation - User wants to generate software requirements
4. general_chat - General conversation, greetings, or unclear intent

Mixed intent patterns (use '+' to combine, order = execution order):
- rag_qa+requirements_generation: Search uploaded documents THEN generate requirements based on findings
- rag_qa+deep_research: Search documents THEN conduct deeper research on the topic
- deep_research+requirements_generation: Research a topic THEN generate requirements
- rag_qa+deep_research+requirements_generation: Full pipeline - search docs, research, then generate requirements

Examples:
- "Based on the uploaded specs, generate requirements for the login module" -> rag_qa+requirements_generation
- "Research authentication best practices and create requirements" -> deep_research+requirements_generation
- "What does the document say about user roles?" -> rag_qa (single intent)
- "Generate requirements for a payment system" -> requirements_generation (single intent)
- "Search the docs, research industry standards, then write requirements" -> rag_qa+deep_research+requirements_generation

Respond with ONLY the intent pattern. Use '+' to combine multiple intents in execution order.
If only one intent applies, respond with just that single intent name.
No explanation needed.""",

    "query_restatement": """You are a query optimization expert. If the original query might lead to inaccurate retrieval, restate it to a more accurate version. Otherwise, leave it as is.
Output only the restated query, nothing else.""",

    "rag_evaluation": """Evaluate if the RAG result can answer the user's query.

ONLY respond with "NEEDS_WEBSEARCH: <query>" if ALL of these conditions are met:
1. The RAG result contains NO relevant information at all, OR
2. The query explicitly asks about current events, real-time data, or information after 2024, OR
3. The user explicitly requests external/web information

Otherwise, respond with: SUFFICIENT

Default to SUFFICIENT if the RAG result has ANY relevant content. Do NOT request web search just because the answer could be more complete.""",

    "rag_answer": """You are a helpful assistant answering questions based on retrieved documents.
Use the provided context to give accurate, comprehensive answers.
If using web search results, clearly indicate which information comes from external sources.

Document Context:
{doc_context}

Graph Context:
{graph_context}

Web Search Results (if any):
{web_context}

Conversation History:
{history}""",

    "research_planner": """As a research planning expert, break down the domain query into 3-5 specific research tasks.
Each task should be actionable and searchable.

Examples of good tasks:
- "Search for current trends in [domain]"
- "Analyze competing products/solutions"
- "Find best practices and methodologies"
- "Research case studies and real-world applications"
- "Identify key challenges and solutions"

Output ONLY a valid JSON array with this exact format:
[{{"task": "description", "priority": 1}}]

Priority should be 1-5 where 1 is highest priority.""",

    "research_synthesizer": """You are a research analyst. Synthesize the search results into a coherent summary.
Focus on key findings, facts, and insights relevant to the research task.
Be concise but comprehensive. Include specific data points when available.""",

    "report_writer": """As a report writing expert, synthesize the following search results into a coherent research report.

The report should include:
1. **Executive Summary** - Brief overview of the research topic and key findings
2. **Introduction** - Background and context of the research query
3. **Main Findings** - Detailed analysis organized by topic/theme
4. **Key Insights** - Important takeaways and implications
5. **Conclusions** - Summary of findings and recommendations
6. **References** - Sources used in the research

Write in a professional, academic tone. Use clear headings and bullet points where appropriate.
Make the report comprehensive but readable.""",
}

# =============================================================================
# Valid Intents
# =============================================================================
VALID_INTENTS = [
    "requirements_generation",
    "rag_qa", 
    "deep_research",
    "general_chat"
]

# Mixed intent combinations (order matters for workflow execution)
# Format: "intent1+intent2" where intent1 executes first, then intent2
VALID_MIXED_INTENTS = [
    "rag_qa+requirements_generation",      # Search docs -> generate requirements
    "rag_qa+deep_research",                # Search docs -> deep research
    "deep_research+requirements_generation", # Research -> generate requirements
    "rag_qa+deep_research+requirements_generation",  # Full pipeline
]

# All valid intent patterns (single + mixed)
ALL_VALID_INTENTS = VALID_INTENTS + VALID_MIXED_INTENTS

# =============================================================================
# UI Configuration
# =============================================================================
APP_TITLE = "📋 Requirements Analysis Agent Assistant (RAAA)"
APP_ICON = "📋"
