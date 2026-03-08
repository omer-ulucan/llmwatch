"""
Tests for the custom exception hierarchy in exceptions.py.
"""

from exceptions import (
    LLMWatchException,
    ValidationException,
    AuthenticationException,
    AuthorizationException,
    ResourceNotFoundException,
    LLMServiceException,
    DatabaseException,
)


class TestLLMWatchException:
    def test_default_code(self):
        exc = LLMWatchException("something broke")
        assert exc.message == "something broke"
        assert exc.code == "INTERNAL_SERVER_ERROR"
        assert str(exc) == "something broke"

    def test_custom_code(self):
        exc = LLMWatchException("bad", code="CUSTOM_CODE")
        assert exc.code == "CUSTOM_CODE"

    def test_is_exception(self):
        exc = LLMWatchException("err")
        assert isinstance(exc, Exception)


class TestValidationException:
    def test_code(self):
        exc = ValidationException("invalid input")
        assert exc.code == "VALIDATION_ERROR"
        assert exc.message == "invalid input"

    def test_inherits_base(self):
        assert issubclass(ValidationException, LLMWatchException)


class TestAuthenticationException:
    def test_default_message(self):
        exc = AuthenticationException()
        assert exc.message == "Could not validate credentials"
        assert exc.code == "AUTHENTICATION_FAILED"

    def test_custom_message(self):
        exc = AuthenticationException("Token expired")
        assert exc.message == "Token expired"


class TestAuthorizationException:
    def test_default_message(self):
        exc = AuthorizationException()
        assert exc.message == "Not enough permissions"
        assert exc.code == "AUTHORIZATION_FAILED"


class TestResourceNotFoundException:
    def test_code(self):
        exc = ResourceNotFoundException("User not found")
        assert exc.code == "RESOURCE_NOT_FOUND"


class TestLLMServiceException:
    def test_provider_stored(self):
        exc = LLMServiceException("timeout", provider="qwen")
        assert exc.code == "LLM_SERVICE_ERROR"
        assert exc.provider == "qwen"
        assert exc.message == "timeout"


class TestDatabaseException:
    def test_code(self):
        exc = DatabaseException("connection lost")
        assert exc.code == "DATABASE_ERROR"
        assert exc.message == "connection lost"
