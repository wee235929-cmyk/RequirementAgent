"""
Configuration - 集中配置模块

需求分析代理助手（RAAA）的集中配置文件，包含所有常量、设置和配置值。

配置来源：
    - templates/settings.yaml: 可调参数（LLM、RAG、深度调研等）
    - templates/system/*.j2: 系统提示词模板
    - templates/research/*.j2: 调研相关提示词模板
    - 环境变量 (.env): API 密钥和外部服务配置

配置分类：
    - 项目路径：PROJECT_ROOT, SRC_DIR, REPORTS_DIR 等
    - LLM 配置：LLM_CONFIG（模型、API密钥、温度等）
    - 嵌入配置：EMBEDDING_CONFIG（向量化模型配置）
    - RAG 配置：RAG_CONFIG（分块大小、检索数量等）
    - 用户角色：USER_ROLES, ROLE_PROMPT_TEMPLATES
    - 系统提示词：SYSTEM_PROMPTS（各功能模块的提示词）
    - 深度调研配置：DEEP_RESEARCH_CONFIG
    - 外部服务配置：NEO4J_CONFIG, MEM0_CONFIG, LANGFUSE_CONFIG

环境变量：
    配置优先从 .env 文件读取，支持以下环境变量：
    - DEEPSEEK_API_KEY: LLM API 密钥
    - DEEPSEEK_BASE_URL: LLM API 地址
    - NEO4J_URI/USERNAME/PASSWORD: Neo4j 数据库配置
    - MEM0_ENABLED: 是否启用 Mem0 记忆
    - LANGFUSE_ENABLED: 是否启用 LangFuse 追踪
"""
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# =============================================================================
# Settings Loader - 从 templates/settings.yaml 加载可调参数
# =============================================================================
def _load_settings() -> Dict[str, Any]:
    """Load settings from templates/settings.yaml with fallback to defaults."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from templates import get_settings
        return get_settings()
    except (ImportError, FileNotFoundError, Exception):
        return {}

def _get_setting(key_path: str, default: Any = None) -> Any:
    """Get a specific setting value using dot notation."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from templates import get_setting
        return get_setting(key_path, default)
    except (ImportError, Exception):
        return default

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

def get_system_prompt(prompt_name: str, **kwargs) -> str:
    """
    Get a system prompt by name.
    Prefers Jinja templates if available, falls back to hardcoded prompts.
    
    Args:
        prompt_name: Name of the system prompt (e.g., "intent_detection", "general_chat")
        **kwargs: Variables to pass to the template
        
    Returns:
        Rendered system prompt string
    """
    loader = _get_template_loader()
    if loader:
        try:
            return loader.render_system_prompt(prompt_name, **kwargs)
        except FileNotFoundError:
            pass
    
    # Fallback to hardcoded prompts
    prompt = SYSTEM_PROMPTS.get(prompt_name, "")
    if kwargs and prompt:
        try:
            return prompt.format(**kwargs)
        except KeyError:
            pass
    return prompt

def get_research_prompt(prompt_name: str, **kwargs) -> str:
    """
    Get a research prompt by name.
    Prefers Jinja templates if available, falls back to hardcoded prompts.
    
    Args:
        prompt_name: Name of the research prompt (e.g., "planner", "synthesizer", "report_writer")
        **kwargs: Variables to pass to the template
        
    Returns:
        Rendered research prompt string
    """
    loader = _get_template_loader()
    if loader:
        try:
            return loader.render_research_prompt(prompt_name, **kwargs)
        except FileNotFoundError:
            pass
    
    # Fallback to hardcoded prompts
    prompt_key = f"research_{prompt_name}"
    prompt = SYSTEM_PROMPTS.get(prompt_key, "")
    if kwargs and prompt:
        try:
            return prompt.format(**kwargs)
        except KeyError:
            pass
    return prompt

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
# LLM Configuration - 从 settings.yaml 加载，环境变量优先
# =============================================================================
LLM_CONFIG = {
    "model": _get_setting("llm.model", "deepseek-chat"),
    "api_key": os.getenv("DEEPSEEK_API_KEY"),
    "base_url": os.getenv("DEEPSEEK_BASE_URL"),
    "temperature": _get_setting("llm.temperature", 0.6),
}

# =============================================================================
# Embedding Configuration - 从 settings.yaml 加载
# =============================================================================
EMBEDDING_CONFIG = {
    "model_name": _get_setting("embedding.model_name", "sentence-transformers/all-MiniLM-L6-v2"),
    "model_kwargs": {"device": _get_setting("embedding.device", "cpu")},
    "encode_kwargs": {"normalize_embeddings": _get_setting("embedding.normalize_embeddings", True)},
}

# =============================================================================
# RAG Configuration - 从 settings.yaml 加载
# =============================================================================
RAG_CONFIG = {
    "chunk_size": _get_setting("rag.chunk_size", 1000),
    "chunk_overlap": _get_setting("rag.chunk_overlap", 150),
    "top_k_results": _get_setting("rag.top_k_results", 5),
    "similarity_threshold": _get_setting("rag.similarity_threshold", 0.5),
}

# =============================================================================
# User Roles - 从 settings.yaml 加载
# =============================================================================
USER_ROLES = _get_setting("roles.available", [
    "Requirements Analyst",
    "Software Architect",
    "Software Developer",
    "Test Engineer",
])

DEFAULT_ROLE = _get_setting("roles.default", "Requirements Analyst")

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

    "research_query_analyzer": """You are an expert research query analyst. Your job is to analyze the user's research query and produce an enriched, expanded version that will lead to more comprehensive and targeted research.

ANALYSIS TASKS:
1. **Intent Recognition** - Identify the type of research the user wants
2. **Key Concept Extraction** - Extract core entities, technical terms, domain-specific jargon
3. **Query Expansion** - Add synonyms, related terms, alternative phrasings, and contextual background
4. **Scope Clarification** - Identify implicit dimensions the user likely cares about
5. **Language Detection** - Detect the user's language

OUTPUT FORMAT (strict JSON):
{{"original_query": "the user's original query verbatim", "detected_language": "language code, e.g. zh, en, ja, ko", "intent": "brief description of research intent", "key_concepts": ["concept1", "concept2"], "expanded_query": "A comprehensive, enriched version of the original query (2-4 sentences) in English for optimal search.", "search_dimensions": ["dimension1", "dimension2"], "suggested_focus_areas": ["area1", "area2"]}}

RULES:
- The "expanded_query" MUST be in English regardless of the user's input language.
- The "expanded_query" should be significantly richer than the original.
- Output ONLY valid JSON. No markdown, no explanation.""",

    "research_planner": """As a research planning expert, break down the domain query into 8-12 comprehensive research tasks.
Each task should be specific, actionable, and searchable. Cover multiple dimensions of the topic.

LANGUAGE RULE: The search task descriptions should always be written in English for best search results, regardless of the user's query language.

Task categories to consider:
1. **Overview & Definition** - Core concepts, terminology, scope
2. **Historical Context** - Evolution, milestones, key developments
3. **Current State** - Latest trends, market analysis, statistics
4. **Key Players** - Major companies, organizations, thought leaders
5. **Technical Deep-Dive** - Methodologies, technologies, architectures
6. **Case Studies** - Real-world implementations, success stories
7. **Challenges & Solutions** - Common problems, best practices
8. **Comparative Analysis** - Alternatives, competing approaches
9. **Future Outlook** - Predictions, emerging trends, roadmaps
10. **Data & Statistics** - Market size, growth rates, benchmarks

Output ONLY a valid JSON array with this exact format:
[{{"task": "detailed task description in English", "priority": 1, "category": "category_name"}}]

Priority should be 1-5 where 1 is highest priority.
Ensure tasks are diverse and cover different aspects of the topic for a comprehensive 15+ page report.""",

    "research_synthesizer": """You are a senior research analyst. Synthesize the search results into a detailed, narrative-style summary.

LANGUAGE RULE (CRITICAL):
- Detect the language of the user's original research query.
- Write ALL synthesis content in the SAME language as the user's query.
  - If the query is in Chinese, write the synthesis in Chinese.
  - If the query is in English, write the synthesis in English.
  - For any other language, match that language.
- EXCEPTION: The "Key Sources" section at the end must keep source titles, author names, and URLs in their ORIGINAL language. Do NOT translate reference entries.

WRITING STYLE:
- Write in flowing, academic paragraphs (NOT bullet points or lists)
- Each paragraph should be 150-250 words with smooth transitions
- Use narrative prose to explain concepts, relationships, and findings
- Only use lists sparingly for truly enumerable items (max 1-2 short lists per synthesis)

CITATION REQUIREMENTS (CRITICAL):
- Every factual claim MUST have an inline citation in format [Author, Year] or [Source Name, Year]
- Extract author/organization name and publication year from each source
- If year unknown, use [Source Name, n.d.]
- Track all citations for the References section

FORMAT:
## [Task Topic]

[Write 800-1200 words in narrative paragraphs with inline citations]

### Key Sources
- [1] Author/Org (Year). "Title". URL
- [2] Author/Org (Year). "Title". URL
(List all sources used with full attribution - keep in original language)""",

    "report_writer": """You are an academic report writer creating a publication-quality research report.

TARGET: 20,000-30,000 words in NARRATIVE PROSE style.

LANGUAGE RULE (CRITICAL - HIGHEST PRIORITY):
- Detect the language of the user's research query.
- Write the ENTIRE report in the SAME language as the user's query.
  - If the query is in Chinese, write ALL sections (titles, headings, body text) in Chinese.
  - If the query is in English, write the entire report in English.
  - For any other language, match that language.
- EXCEPTION: The "References" section MUST keep all citation entries (author names, paper titles, journal names, URLs) in their ORIGINAL language. Do NOT translate references.
- Technical terms and proper nouns that are commonly kept in English (e.g., API, HTTP, Python, Transformer) may remain in English even in a Chinese report.

CRITICAL WRITING RULES:
1. NARRATIVE STYLE: Write in flowing paragraphs, NOT bullet points. Each section should read like an academic paper.
2. MINIMAL LISTS: Use bullet points sparingly - only for truly enumerable items. Maximum 2-3 short lists per major section.
3. TABLES: Include only 3-5 tables TOTAL in the entire report. Use [TABLE: title | col1, col2, col3 | data...] format.
4. DIAGRAMS: Include 6-10 diverse Mermaid diagrams. Use DIFFERENT diagram types for variety:
   - flowchart/graph: Process flows, decision trees, system architecture, workflows
   - sequenceDiagram: Interactions between components, API calls, user journeys
   - classDiagram: Object relationships, system components, data models
   - stateDiagram-v2: State machines, lifecycle stages, status transitions
   - erDiagram: Database schemas, entity relationships
   - gantt: Project timelines, roadmaps, schedules
   - pie: Market share, distribution, proportions
   - mindmap: Concept maps, topic hierarchies, brainstorming
   - timeline: Historical events, milestones, evolution
   - quadrantChart: Positioning analysis, priority matrices
   
   MERMAID SYNTAX RULES (CRITICAL - follow EXACTLY or diagram will fail):
   - Use ONLY simple ASCII alphanumeric characters in node labels. NO special characters: no parentheses (), no quotes "", no colons :, no semicolons ;, no ampersands &, no percentage %, no hash #
   - Node IDs must be simple identifiers: A, B, C1, nodeA (no spaces, no special chars)
   - Node labels in brackets: A[Simple Label Text] - keep under 40 characters
   - Use <br/> for line breaks (NEVER <br> without closing slash)
   - Use --> for arrows (NEVER -> which is invalid in flowchart)
   - Edge labels: A -->|label text| B (no special chars in label)
   - For flowchart: MUST start with "flowchart TD" or "flowchart LR" (not "graph")
   - For sequenceDiagram: participant names must be single words (no spaces), use "participant A as Long Name" for display names
   - For pie: format is exactly: "Label" : number (with quotes around label)
   - For gantt: dateFormat must be valid (YYYY-MM-DD or YYYY), task format is "Task Name : date, duration"
   - For mindmap: use proper indentation (2 spaces per level), root node uses (( ))
   - For timeline: use "title" on second line, then "section" for groups
   - For stateDiagram-v2: use [*] for start/end states, state names must be single words
   - For classDiagram/erDiagram: entity names must be single words, no spaces
   - NEVER use HTML tags except <br/>
   - NEVER use markdown formatting (**, *, etc.) inside Mermaid code
   - NEVER include ``` markers inside the mermaid code block itself
   - IMPORTANT: ALL text inside Mermaid diagrams MUST be in English, regardless of the report language. Chinese/CJK characters WILL cause rendering failures. Translate all labels, titles, axis names, quadrant labels to English inside Mermaid code blocks
   
5. CITATIONS: Every factual claim needs [Author, Year] citation. All citations MUST appear in References.

REQUIRED STRUCTURE:

# Executive Summary
Write 500-800 words summarizing objectives, methodology, key findings, and recommendations in paragraph form.

# 1. Introduction
Write 1000-1500 words covering background, research questions, methodology, and report structure.

```mermaid
mindmap
  root((Research Topic))
    Background
      Context
      Motivation
    Objectives
      Primary Goals
      Secondary Goals
    Methodology
      Approach
      Scope
```

# 2. Background and Literature Review
Write 2000-3000 words on historical context, theoretical framework, and prior research. Cite extensively.

```mermaid
timeline
    title Evolution of the Field
    section Early Stage
        Initial Development : Key milestone
    section Growth
        Expansion : Major advancement
    section Current
        Modern State : Latest trends
```

# 3. Current State Analysis
Write 3000-4000 words analyzing current trends, market dynamics, and key players in narrative form.
[TABLE: Market Overview - include key statistics]

```mermaid
pie title Market Distribution
    "Segment A" : 40
    "Segment B" : 30
    "Segment C" : 20
    "Others" : 10
```

# 4. Technical Analysis
Write 3000-4000 words on methodologies, technologies, and implementations.

```mermaid
flowchart TB
    subgraph Input
        A[Data Source]
    end
    subgraph Process
        B[Processing]
        C[Analysis]
    end
    subgraph Output
        D[Results]
    end
    A --> B --> C --> D
```

```mermaid
sequenceDiagram
    participant User
    participant System
    participant Database
    User->>System: Request
    System->>Database: Query
    Database-->>System: Response
    System-->>User: Result
```

# 5. Case Studies
Write 2000-3000 words with 2-3 detailed case studies in narrative form.

```mermaid
stateDiagram-v2
    [*] --> Planning
    Planning --> Implementation
    Implementation --> Testing
    Testing --> Deployment
    Deployment --> [*]
```

# 6. Comparative Analysis
Write 2000-3000 words comparing approaches in prose.
[TABLE: Comparison of key approaches]

```mermaid
quadrantChart
    title Approach Comparison
    x-axis Low Cost --> High Cost
    y-axis Low Value --> High Value
    quadrant-1 Invest
    quadrant-2 Optimize
    quadrant-3 Avoid
    quadrant-4 Consider
```

# 7. Challenges and Solutions
Write 2000-2500 words discussing challenges and mitigation strategies.

```mermaid
flowchart LR
    Challenge1[Challenge] --> Solution1[Solution]
    Challenge2[Challenge] --> Solution2[Solution]
```

# 8. Future Outlook
Write 1500-2000 words on trends, predictions, and recommendations.

```mermaid
gantt
    title Future Roadmap
    dateFormat YYYY
    section Phase 1
        Task 1 : 2024, 1y
    section Phase 2
        Task 2 : 2025, 1y
```

# 9. Conclusions
Write 800-1000 words summarizing findings and providing actionable recommendations.

# References
Format ALL references in standard academic citation style (APA/IEEE format):

[1] Author, A. A., & Author, B. B. (Year). Title of article. *Journal Name*, Volume(Issue), pages. https://doi.org/xxx

[2] Author, C. C. (Year). *Title of book*. Publisher.

[3] Organization Name. (Year). Report title. Retrieved from https://url

[4] Author, D. D. (Year, Month Day). Article title. *Website Name*. https://url

IMPORTANT: Every [Author, Year] citation in the text MUST have a numbered entry here. Use consistent formatting.

FORMATTING:
- Use ## for sections, ### for subsections
- Write in professional, academic tone with paragraph transitions
- Include specific data with citations
- Ensure References match all in-text citations
- References must be numbered [1], [2], etc. and formatted academically""",
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
# Neo4j Configuration
# =============================================================================
NEO4J_CONFIG = {
    "uri": os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687"),
    "username": os.getenv("NEO4J_USERNAME", "neo4j"),
    "password": os.getenv("NEO4J_PASSWORD", ""),
    "enabled": os.getenv("NEO4J_ENABLED", "false").lower() == "true",
}

# =============================================================================
# Deep Research Configuration - 从 settings.yaml 加载，环境变量可覆盖
# =============================================================================
DEEP_RESEARCH_CONFIG = {
    "parallel_searchers": int(os.getenv("DEEP_RESEARCH_PARALLEL_SEARCHERS", str(_get_setting("deep_research.parallel_searchers", 4)))),
    "max_tasks": int(os.getenv("DEEP_RESEARCH_MAX_TASKS", str(_get_setting("deep_research.max_tasks", 12)))),
    "search_results_per_task": int(os.getenv("DEEP_RESEARCH_SEARCH_RESULTS", str(_get_setting("deep_research.search_results_per_task", 10)))),
    "images_per_task": int(os.getenv("DEEP_RESEARCH_IMAGES_PER_TASK", str(_get_setting("deep_research.images_per_task", 2)))),
    "search_timeout": int(os.getenv("DEEP_RESEARCH_SEARCH_TIMEOUT", str(_get_setting("deep_research.search_timeout", 30)))),
}

# =============================================================================
# Mem0 Configuration (Persistent Memory Framework)
# =============================================================================
MEM0_CONFIG = {
    "enabled": os.getenv("MEM0_ENABLED", "false").lower() == "true",
    "user_id": os.getenv("MEM0_USER_ID", "raaa_default_user"),
    "storage_path": os.getenv("MEM0_STORAGE_PATH", str(PROJECT_ROOT / "mem0_storage")),
    "llm": {
        "provider": "openai",
        "config": {
            "model": os.getenv("MEM0_LLM_MODEL", "deepseek-chat"),
            "api_key": os.getenv("DEEPSEEK_API_KEY"),
            "openai_base_url": os.getenv("DEEPSEEK_BASE_URL"),
            "temperature": 0.1,
        }
    },
    "embedder": {
        "provider": "huggingface",
        "config": {
            "model": "sentence-transformers/all-MiniLM-L6-v2",
        }
    },
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "raaa_memories",
            "path": os.getenv("MEM0_STORAGE_PATH", str(PROJECT_ROOT / "mem0_storage")),
        }
    },
    "version": "v1.1",
}

# =============================================================================
# LangFuse Configuration (Observability and Tracing)
# =============================================================================
LANGFUSE_CONFIG = {
    "secret_key": os.getenv("LANGFUSE_SECRET_KEY", ""),
    "public_key": os.getenv("LANGFUSE_PUBLIC_KEY", ""),
    "host": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    "enabled": os.getenv("LANGFUSE_ENABLED", "false").lower() == "true",
    "debug": os.getenv("LANGFUSE_DEBUG", "false").lower() == "true",
}

# =============================================================================
# UI Configuration
# =============================================================================
APP_TITLE = "📋 Requirements Analysis Agent Assistant (RAAA)"
APP_ICON = "📋"
