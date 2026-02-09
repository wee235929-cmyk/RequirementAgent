"""
API Routes for RAAA FastAPI backend.
"""
from .chat import router as chat_router
from .documents import router as documents_router
from .srs import router as srs_router
from .research import router as research_router
from .stats import router as stats_router

__all__ = [
    "chat_router",
    "documents_router", 
    "srs_router",
    "research_router",
    "stats_router",
]
