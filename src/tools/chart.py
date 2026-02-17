"""
Mermaid Chart Generation Tool.
Uses LLM to generate Mermaid diagrams from requirements.
"""
import sys
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LLM_CONFIG
from utils import get_logger

logger = get_logger(__name__)

# =============================================================================
# Mermaid Chart Prompts
# =============================================================================

MERMAID_SEQUENCE_PROMPT = """Based on the following requirements, generate a Mermaid sequence diagram code describing the user flow.

Requirements:
{requirements}

Instructions:
1. Identify the main actors (users, systems, services)
2. Map out the sequence of interactions
3. Include key decision points and alternative flows
4. Use proper Mermaid sequence diagram syntax
5. CRITICAL: ALL text in the diagram (participant names, messages, notes) MUST be in the SAME language as the requirements. If requirements are in Chinese, use Chinese. If in English, use English. Do NOT mix languages - be consistent throughout.

Output ONLY the Mermaid code block, no explanations. Start with ```mermaid and end with ```."""

MERMAID_FLOWCHART_PROMPT = """Based on the following requirements, generate a Mermaid flowchart diagram code describing the system flow.

Requirements:
{requirements}

Instructions:
1. Identify the main processes and decision points
2. Map out the flow from start to end
3. Include conditional branches where applicable
4. Use proper Mermaid flowchart syntax (flowchart TD or flowchart LR)
5. CRITICAL: ALL text in the diagram (node labels, edge labels, titles) MUST be in the SAME language as the requirements. If requirements are in Chinese, use Chinese. If in English, use English. Do NOT mix languages - be consistent throughout.

Output ONLY the Mermaid code block, no explanations. Start with ```mermaid and end with ```."""

MERMAID_CLASS_PROMPT = """Based on the following requirements, generate a Mermaid class diagram code describing the system structure.

Requirements:
{requirements}

Instructions:
1. Identify the main entities/classes
2. Define their attributes and methods
3. Show relationships between classes
4. Use proper Mermaid class diagram syntax
5. CRITICAL: ALL text in the diagram (class names, attributes, methods, relationships) MUST be in the SAME language as the requirements. If requirements are in Chinese, use Chinese. If in English, use English. Do NOT mix languages - be consistent throughout.

Output ONLY the Mermaid code block, no explanations. Start with ```mermaid and end with ```."""

MERMAID_ER_PROMPT = """Based on the following requirements, generate a Mermaid ER diagram code describing the data model.

Requirements:
{requirements}

Instructions:
1. Identify the main entities
2. Define their attributes
3. Show relationships with cardinality
4. Use proper Mermaid ER diagram syntax
5. CRITICAL: ALL text in the diagram (entity names, attribute names, relationship labels) MUST be in the SAME language as the requirements. If requirements are in Chinese, use Chinese. If in English, use English. Do NOT mix languages - be consistent throughout.

Output ONLY the Mermaid code block, no explanations. Start with ```mermaid and end with ```."""


class MermaidChartTool:
    """Tool for generating Mermaid diagrams from requirements."""
    
    DIAGRAM_TYPES = {
        "sequence": MERMAID_SEQUENCE_PROMPT,
        "flowchart": MERMAID_FLOWCHART_PROMPT,
        "class": MERMAID_CLASS_PROMPT,
        "er": MERMAID_ER_PROMPT,
    }
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=0.3  # Lower temperature for more consistent diagram output
        )
    
    @traceable(name="generate_mermaid_chart")
    def generate(
        self, 
        requirements: str, 
        diagram_type: str = "sequence"
    ) -> str:
        """
        Generate a Mermaid diagram from requirements.
        
        Args:
            requirements: The requirements text to visualize
            diagram_type: Type of diagram ('sequence', 'flowchart', 'class', 'er')
        
        Returns:
            Mermaid code string (including ```mermaid markers)
        """
        if diagram_type not in self.DIAGRAM_TYPES:
            diagram_type = "sequence"
        
        prompt_template = self.DIAGRAM_TYPES[diagram_type]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert at creating Mermaid diagrams. Generate clean, valid Mermaid syntax. IMPORTANT: Always use English for ALL text in diagrams (labels, titles, names, descriptions). Never use Chinese or other CJK characters as they cause rendering failures."),
            ("human", prompt_template)
        ])
        
        chain = prompt | self.llm
        
        try:
            logger.info(f"Generating {diagram_type} diagram from requirements")
            result = chain.invoke({"requirements": requirements})
            
            mermaid_code = result.content.strip()
            
            # Ensure proper formatting
            if not mermaid_code.startswith("```mermaid"):
                mermaid_code = f"```mermaid\n{mermaid_code}"
            if not mermaid_code.endswith("```"):
                mermaid_code = f"{mermaid_code}\n```"
            
            logger.info(f"Generated {diagram_type} diagram successfully")
            return mermaid_code
            
        except Exception as e:
            logger.error(f"Error generating Mermaid diagram: {e}")
            return f"```mermaid\ngraph TD\n    A[Error] --> B[Failed to generate diagram: {str(e)}]\n```"
    
    def detect_diagram_type(self, user_input: str) -> str:
        """
        Detect the appropriate diagram type from user input.
        
        Args:
            user_input: User's request text
        
        Returns:
            Diagram type string
        """
        user_lower = user_input.lower()
        
        # Check flowchart FIRST (before sequence, since "flow" is substring)
        if any(word in user_lower for word in ["flowchart", "flow chart", "process flow", "workflow", "流程图"]):
            return "flowchart"
        # Then check sequence diagram
        elif any(word in user_lower for word in ["sequence", "时序", "interaction", "user flow", "交互"]):
            return "sequence"
        # Class diagram
        elif any(word in user_lower for word in ["class", "类图", "structure", "object", "uml", "对象"]):
            return "class"
        # ER diagram
        elif any(word in user_lower for word in ["er", "entity", "database", "data model", "实体", "数据模型"]):
            return "er"
        # Use case diagram (new)
        elif any(word in user_lower for word in ["use case", "用例", "actor", "参与者"]):
            return "sequence"  # Mermaid doesn't have native use case, use sequence
        else:
            return "sequence"  # Default


@traceable(name="generate_mermaid_chart_function")
def generate_mermaid_chart(
    requirements: str, 
    diagram_type: str = "sequence"
) -> str:
    """
    Convenience function to generate a Mermaid chart.
    
    Args:
        requirements: The requirements text to visualize
        diagram_type: Type of diagram ('sequence', 'flowchart', 'class', 'er')
    
    Returns:
        Mermaid code string
    """
    tool = MermaidChartTool()
    return tool.generate(requirements, diagram_type)


def should_generate_chart(user_input: str) -> bool:
    """
    Check if user is requesting a chart/diagram.
    
    Args:
        user_input: User's input text
    
    Returns:
        True if user wants a chart
    """
    chart_keywords = [
        # English keywords
        "chart", "diagram", "visualize", "visualization",
        "mermaid", "sequence diagram", "flowchart", "flow chart",
        "class diagram", "er diagram", "entity relationship",
        "draw", "show me a diagram", "generate diagram",
        "use case", "uml", "workflow", "process flow",
        # Chinese keywords
        "图", "流程", "时序", "类图", "用例", "画", "绘制",
        "可视化", "示意图", "架构图", "数据流"
    ]
    
    user_lower = user_input.lower()
    return any(keyword in user_lower for keyword in chart_keywords)


def should_auto_generate_diagram(requirements_text: str) -> tuple[bool, str]:
    """
    Determine if a diagram should be auto-generated based on requirements content.
    Returns (should_generate, diagram_type).
    
    Args:
        requirements_text: The generated requirements text
    
    Returns:
        Tuple of (should_generate: bool, diagram_type: str)
    """
    text_lower = requirements_text.lower()
    
    # Check for user flow / interaction patterns
    flow_indicators = [
        "user flow", "user journey", "interaction", "step 1", "step 2",
        "first,", "then,", "next,", "finally,", "workflow",
        "用户流程", "交互流程", "步骤"
    ]
    if any(ind in text_lower for ind in flow_indicators):
        return True, "sequence"
    
    # Check for process / decision patterns
    process_indicators = [
        "if ", "else ", "decision", "branch", "condition",
        "process", "procedure", "algorithm",
        "如果", "否则", "判断", "条件"
    ]
    if any(ind in text_lower for ind in process_indicators):
        return True, "flowchart"
    
    # Check for entity / data model patterns
    entity_indicators = [
        "entity", "table", "database", "field", "attribute",
        "relationship", "foreign key", "primary key",
        "实体", "表", "字段", "属性", "关系"
    ]
    if any(ind in text_lower for ind in entity_indicators):
        return True, "er"
    
    # Check for class / object patterns
    class_indicators = [
        "class ", "object", "method", "property", "inheritance",
        "interface", "abstract", "implement",
        "类", "对象", "方法", "属性", "继承"
    ]
    if any(ind in text_lower for ind in class_indicators):
        return True, "class"
    
    return False, ""
