"""
Jinja2 Template Loader for prompt management.

Provides utilities to load and render Jinja2 templates from the templates folder.
Also supports loading settings from settings.yaml for centralized configuration.
"""

from pathlib import Path
from typing import Dict, Any, Optional
import json

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# Template directory root
TEMPLATE_ROOT = Path(__file__).parent

# Settings cache
_settings_cache: Optional[Dict[str, Any]] = None
_settings_mtime: float = 0


class TemplateLoader:
    """
    Loads and renders Jinja2 templates for prompts.
    
    Usage:
        loader = TemplateLoader()
        prompt = loader.render("roles/requirements_analyst.j2", history="...", focus="...")
    """
    
    _instance: Optional["TemplateLoader"] = None
    
    def __init__(self, template_dir: Optional[Path] = None):
        """
        Initialize the template loader.
        
        Args:
            template_dir: Root directory for templates. Defaults to templates folder.
        """
        if not JINJA2_AVAILABLE:
            raise ImportError(
                "Jinja2 is required for template management. "
                "Please install it: pip install Jinja2"
            )
        
        self.template_dir = template_dir or TEMPLATE_ROOT
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(enabled_extensions=(), default=False),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        
        # Cache for loaded role configs
        self._role_config_cache: Dict[str, Dict] = {}
    
    def render(self, template_path: str, **kwargs) -> str:
        """
        Render a template with the given variables.
        
        Args:
            template_path: Relative path to template (e.g., "roles/requirements_analyst.j2")
            **kwargs: Variables to pass to the template
            
        Returns:
            Rendered template string
        """
        try:
            template = self.env.get_template(template_path)
            return template.render(**kwargs)
        except TemplateNotFound:
            raise FileNotFoundError(f"Template not found: {template_path}")
    
    def get_role_prompt(self, role_name: str, history: str = "", focus: str = "") -> str:
        """
        Get a rendered role prompt by role name.
        
        Args:
            role_name: Name of the role (e.g., "Requirements Analyst")
            history: Conversation history
            focus: Focus area for requirements
            
        Returns:
            Rendered role prompt
        """
        # Convert role name to template filename
        template_name = role_name.lower().replace(" ", "_") + ".j2"
        template_path = f"roles/{template_name}"
        
        return self.render(template_path, history=history, focus=focus)
    
    def get_available_roles(self) -> list:
        """
        Get list of available roles from the roles folder.
        
        Returns:
            List of role names
        """
        role_dir = self.template_dir / "roles"
        if not role_dir.exists():
            return []
        
        roles = []
        for template_file in role_dir.glob("*.j2"):
            # Skip base template
            if template_file.name.startswith("_"):
                continue
            # Convert filename to role name
            role_name = template_file.stem.replace("_", " ").title()
            roles.append(role_name)
        
        return sorted(roles)
    
    def get_role_config(self, role_name: str) -> Dict[str, Any]:
        """
        Get role configuration from JSON file if exists.
        
        Args:
            role_name: Name of the role
            
        Returns:
            Role configuration dictionary
        """
        if role_name in self._role_config_cache:
            return self._role_config_cache[role_name]
        
        config_name = role_name.lower().replace(" ", "_") + ".json"
        config_path = self.template_dir / "roles" / config_name
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self._role_config_cache[role_name] = config
                return config
        
        return {}
    
    def render_system_prompt(self, prompt_name: str, **kwargs) -> str:
        """
        Render a system prompt template.
        
        Args:
            prompt_name: Name of the system prompt (e.g., "intent_detection", "general_chat")
            **kwargs: Variables to pass to the template
            
        Returns:
            Rendered prompt string
        """
        template_path = f"system/{prompt_name}.j2"
        return self.render(template_path, **kwargs)
    
    def render_rag_prompt(self, prompt_name: str, **kwargs) -> str:
        """
        Render a RAG-related prompt template.
        
        Args:
            prompt_name: Name of the RAG prompt (e.g., "query_rewrite", "evaluation", "answer")
            **kwargs: Variables to pass to the template
            
        Returns:
            Rendered prompt string
        """
        template_path = f"rag/{prompt_name}.j2"
        return self.render(template_path, **kwargs)
    
    def render_research_prompt(self, prompt_name: str, **kwargs) -> str:
        """
        Render a research-related prompt template.
        
        Args:
            prompt_name: Name of the research prompt (e.g., "planner", "synthesizer", "report_writer")
            **kwargs: Variables to pass to the template
            
        Returns:
            Rendered prompt string
        """
        template_path = f"research/{prompt_name}.j2"
        return self.render(template_path, **kwargs)
    
    def template_exists(self, template_path: str) -> bool:
        """
        Check if a template exists.
        
        Args:
            template_path: Relative path to template
            
        Returns:
            True if template exists
        """
        full_path = self.template_dir / template_path
        return full_path.exists()


# Singleton instance
_loader_instance: Optional[TemplateLoader] = None


def get_template_loader() -> Optional[TemplateLoader]:
    """
    Get the singleton TemplateLoader instance.
    
    Returns:
        TemplateLoader instance, or None if Jinja2 is not available
    """
    global _loader_instance
    
    if not JINJA2_AVAILABLE:
        return None
    
    if _loader_instance is None:
        _loader_instance = TemplateLoader()
    
    return _loader_instance


def is_jinja2_available() -> bool:
    """Check if Jinja2 is available."""
    return JINJA2_AVAILABLE


def is_yaml_available() -> bool:
    """Check if PyYAML is available."""
    return YAML_AVAILABLE


def get_settings(reload: bool = False) -> Dict[str, Any]:
    """
    Load settings from settings.yaml.
    
    Settings are cached and only reloaded if the file has been modified
    or if reload=True is specified.
    
    Args:
        reload: Force reload settings from file
        
    Returns:
        Settings dictionary
        
    Raises:
        ImportError: If PyYAML is not installed
        FileNotFoundError: If settings.yaml doesn't exist
    """
    global _settings_cache, _settings_mtime
    
    if not YAML_AVAILABLE:
        raise ImportError(
            "PyYAML is required for settings management. "
            "Please install it: pip install pyyaml"
        )
    
    settings_path = TEMPLATE_ROOT / "settings.yaml"
    
    if not settings_path.exists():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")
    
    # Check if file has been modified
    current_mtime = settings_path.stat().st_mtime
    
    if _settings_cache is None or reload or current_mtime > _settings_mtime:
        with open(settings_path, 'r', encoding='utf-8') as f:
            _settings_cache = yaml.safe_load(f)
        _settings_mtime = current_mtime
    
    return _settings_cache


def get_setting(key_path: str, default: Any = None) -> Any:
    """
    Get a specific setting value using dot notation.
    
    Args:
        key_path: Dot-separated path to the setting (e.g., "rag.chunk_size")
        default: Default value if setting not found
        
    Returns:
        Setting value or default
        
    Example:
        chunk_size = get_setting("rag.chunk_size", 1000)
        temperature = get_setting("llm.temperature", 0.7)
    """
    try:
        settings = get_settings()
        keys = key_path.split(".")
        value = settings
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    except (ImportError, FileNotFoundError):
        return default
