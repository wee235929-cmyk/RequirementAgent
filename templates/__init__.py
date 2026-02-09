"""
Templates Module

This module provides Jinja2 template loading and rendering for prompts,
as well as centralized settings management via settings.yaml.

Templates are organized by category:
- roles: Role-specific prompts for requirements generation
- rag: RAG-related prompts (query rewriting, evaluation, answer generation)
- research: Deep research prompts (planner, synthesizer, report writer)
- requirements: Requirements generation, validation, refinement prompts
- system: System prompts (intent detection, general chat)

Settings:
- settings.yaml: Centralized configuration for all tunable parameters
"""

from .template_loader import (
    TemplateLoader, 
    get_template_loader,
    get_settings,
    get_setting,
    is_jinja2_available,
    is_yaml_available,
)

__all__ = [
    "TemplateLoader", 
    "get_template_loader",
    "get_settings",
    "get_setting",
    "is_jinja2_available",
    "is_yaml_available",
]
