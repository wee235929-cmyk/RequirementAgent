"""
Custom exceptions for the Requirements Analysis Agent Assistant.
Provides a hierarchy of exceptions for better error handling and debugging.
"""


class RAAAError(Exception):
    """Base exception for all RAAA errors."""
    
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self):
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ConfigurationError(RAAAError):
    """Raised when there's a configuration issue."""
    pass


class ParsingError(RAAAError):
    """Raised when document parsing fails."""
    pass


class IndexingError(RAAAError):
    """Raised when document indexing fails."""
    pass


class WorkflowError(RAAAError):
    """Raised when a workflow execution fails."""
    pass
