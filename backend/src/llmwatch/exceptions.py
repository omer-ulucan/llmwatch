"""
Module: exceptions.py
Purpose: Defines a customized exception hierarchy for the LLMWatch system.
WHY: Using custom exceptions allows the application layers to throw specific errors
without understanding the HTTP layer, ensuring clean separation of concerns.
These map to specific HTTP status codes in standard exception handlers.
"""


class LLMWatchException(Exception):
    """
    Base exception for all application-specific errors.

    Args:
        message (str): Human readable error message.
        code (str): System-readable error code.
    """

    def __init__(self, message: str, code: str = "INTERNAL_SERVER_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ValidationException(LLMWatchException):
    """Raised when input validation fails before hitting external services."""

    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")


class AuthenticationException(LLMWatchException):
    """Raised when authentication (JWT) fails or is missing."""

    def __init__(self, message: str = "Could not validate credentials"):
        super().__init__(message, code="AUTHENTICATION_FAILED")


class AuthorizationException(LLMWatchException):
    """Raised when an authenticated user lacks required permissions."""

    def __init__(self, message: str = "Not enough permissions"):
        super().__init__(message, code="AUTHORIZATION_FAILED")


class ResourceNotFoundException(LLMWatchException):
    """Raised when a specific requested resource is not found."""

    def __init__(self, message: str):
        super().__init__(message, code="RESOURCE_NOT_FOUND")


class ConflictException(LLMWatchException):
    """Raised when a request conflicts with existing state (e.g. duplicate email)."""

    def __init__(self, message: str):
        super().__init__(message, code="CONFLICT")


class LLMServiceException(LLMWatchException):
    """Raised when interactions with external LLM APIs fail."""

    def __init__(self, message: str, provider: str):
        super().__init__(message, code="LLM_SERVICE_ERROR")
        self.provider = provider


class DatabaseException(LLMWatchException):
    """Raised when a database operation fails, without exposing driver errors to clients."""

    def __init__(self, message: str):
        super().__init__(message, code="DATABASE_ERROR")
