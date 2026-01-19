"""
Role management module with Jinja2 template support.

Roles can be defined in two ways:
1. Jinja2 templates in Template_management/role_management/*.j2 (preferred)
2. Hardcoded templates in config.py (fallback)

To add a new role, simply create a new .j2 file in the role_management folder.
"""
import sys
from pathlib import Path
from typing import Dict, Optional

from langchain_core.prompts import PromptTemplate

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ROLE_PROMPT_TEMPLATES, get_available_roles as config_get_roles, get_role_prompt

# Cache for dynamically created PromptTemplates
_role_prompts_cache: Dict[str, PromptTemplate] = {}

def _get_template_loader():
    """Get template loader if Jinja2 is available."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from templates import get_template_loader
        return get_template_loader()
    except (ImportError, Exception):
        return None

def select_role_prompt(role: str) -> PromptTemplate:
    """
    Returns the corresponding PromptTemplate instance based on the user's selected role.
    
    Prefers Jinja2 templates if available, falls back to hardcoded templates.
    
    Args:
        role: The name of the role (e.g., 'Requirements Analyst', 'Test Engineer')
        
    Returns:
        PromptTemplate instance for the specified role
        
    Raises:
        ValueError: If the role is not found
    """
    # Check cache first
    if role in _role_prompts_cache:
        return _role_prompts_cache[role]
    
    # Try Jinja2 template
    loader = _get_template_loader()
    if loader:
        template_name = role.lower().replace(" ", "_") + ".j2"
        if loader.template_exists(f"roles/{template_name}"):
            # Create a PromptTemplate that uses Jinja2 under the hood
            # We use a wrapper that calls the Jinja2 template
            jinja_template = _create_jinja_prompt_template(role, loader)
            _role_prompts_cache[role] = jinja_template
            return jinja_template
    
    # Fallback to hardcoded templates
    if role in ROLE_PROMPT_TEMPLATES:
        template = PromptTemplate(
            input_variables=["focus", "history"],
            template=ROLE_PROMPT_TEMPLATES[role]
        )
        _role_prompts_cache[role] = template
        return template
    
    available_roles = ", ".join(get_available_roles())
    raise ValueError(f"Role '{role}' not found. Available roles: {available_roles}")

def _create_jinja_prompt_template(role: str, loader) -> PromptTemplate:
    """
    Create a PromptTemplate that wraps a Jinja2 template.
    
    Args:
        role: Role name
        loader: Template loader instance
        
    Returns:
        PromptTemplate instance
    """
    # Read the raw template content and convert Jinja2 syntax to LangChain format
    template_name = role.lower().replace(" ", "_") + ".j2"
    template_path = loader.template_dir / "roles" / template_name
    
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove Jinja2 comments
    import re
    content = re.sub(r'\{#.*?#\}', '', content, flags=re.DOTALL)
    
    # Convert Jinja2 variable syntax to LangChain format
    # {{ variable }} -> {variable}
    content = re.sub(r'\{\{\s*(\w+)\s*\}\}', r'{\1}', content)
    
    return PromptTemplate(
        input_variables=["focus", "history"],
        template=content.strip()
    )

def get_available_roles() -> list:
    """
    Returns a list of all available role names.
    
    Combines roles from Jinja2 templates and hardcoded templates.
    
    Returns:
        List of role names
    """
    roles = set()
    
    # Get roles from Jinja2 templates
    loader = _get_template_loader()
    if loader:
        jinja_roles = loader.get_available_roles()
        roles.update(jinja_roles)
    
    # Add hardcoded roles
    roles.update(ROLE_PROMPT_TEMPLATES.keys())
    
    return sorted(list(roles))

def add_role_prompt(role_name: str, template: PromptTemplate) -> None:
    """
    Adds a new role prompt to the cache (for runtime extensibility).
    
    Note: For persistent roles, create a .j2 file in Template_management/role_management/
    
    Args:
        role_name: Name of the new role
        template: PromptTemplate instance for the role
    """
    _role_prompts_cache[role_name] = template

def clear_role_cache() -> None:
    """Clear the role prompts cache to reload templates."""
    _role_prompts_cache.clear()
