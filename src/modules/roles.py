import sys
from pathlib import Path
from typing import Dict

from langchain_core.prompts import PromptTemplate

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ROLE_PROMPT_TEMPLATES


ROLE_PROMPTS: Dict[str, PromptTemplate] = {
    role: PromptTemplate(
        input_variables=["focus", "history"],
        template=template
    )
    for role, template in ROLE_PROMPT_TEMPLATES.items()
}

def select_role_prompt(role: str) -> PromptTemplate:
    """
    Returns the corresponding PromptTemplate instance based on the user's selected role.
    
    Args:
        role: The name of the role (e.g., 'Requirements Analyst', 'Test Engineer')
        
    Returns:
        PromptTemplate instance for the specified role
        
    Raises:
        ValueError: If the role is not found in ROLE_PROMPTS
    """
    if role not in ROLE_PROMPTS:
        available_roles = ", ".join(ROLE_PROMPTS.keys())
        raise ValueError(f"Role '{role}' not found. Available roles: {available_roles}")
    
    return ROLE_PROMPTS[role]

def get_available_roles() -> list:
    """
    Returns a list of all available role names.
    
    Returns:
        List of role names
    """
    return list(ROLE_PROMPTS.keys())

def add_role_prompt(role_name: str, template: PromptTemplate) -> None:
    """
    Adds a new role prompt to the system (for extensibility).
    
    Args:
        role_name: Name of the new role
        template: PromptTemplate instance for the role
    """
    ROLE_PROMPTS[role_name] = template
