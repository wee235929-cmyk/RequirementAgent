"""
Templates Module

This module provides Jinja2 template loading and rendering for prompts.
Templates are organized by category:
- roles: Role-specific prompts for requirements generation
- rag: RAG-related prompts (query rewriting, evaluation, answer generation)
- research: Deep research prompts (planner, synthesizer, report writer)
- requirements: Requirements generation, validation, refinement prompts
- system: System prompts (intent detection, general chat)
"""

from .template_loader import TemplateLoader, get_template_loader

__all__ = ["TemplateLoader", "get_template_loader"]
