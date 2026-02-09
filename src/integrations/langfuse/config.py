"""
LangFuse configuration module.
Loads configuration from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# LangFuse Configuration
# =============================================================================
LANGFUSE_CONFIG = {
    "secret_key": os.getenv("LANGFUSE_SECRET_KEY", ""),
    "public_key": os.getenv("LANGFUSE_PUBLIC_KEY", ""),
    "host": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    "enabled": os.getenv("LANGFUSE_ENABLED", "false").lower() == "true",
    "debug": os.getenv("LANGFUSE_DEBUG", "false").lower() == "true",
}


def is_configured() -> bool:
    """Check if LangFuse is properly configured with required credentials."""
    return bool(
        LANGFUSE_CONFIG["enabled"]
        and LANGFUSE_CONFIG["secret_key"]
        and LANGFUSE_CONFIG["public_key"]
    )
