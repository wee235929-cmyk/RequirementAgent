"""
Centralized logging configuration for the Requirements Analysis Agent Assistant.
"""
import logging
import sys
from pathlib import Path
from typing import Optional


_loggers = {}

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    format_string: str = LOG_FORMAT
) -> None:
    """
    Configure the root logger for the application.
    
    Args:
        level: Logging level (default: INFO)
        log_file: Optional path to log file
        format_string: Log message format
    """
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format=format_string,
        datefmt=LOG_DATE_FORMAT,
        handlers=handlers,
        force=True
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with the given name.
    
    Args:
        name: Logger name (typically __name__ of the module)
        
    Returns:
        Configured logger instance
    """
    if name not in _loggers:
        logger = logging.getLogger(name)
        _loggers[name] = logger
    return _loggers[name]
