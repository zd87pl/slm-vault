"""Custom exceptions for langchain-enclave."""


class EnclaveError(Exception):
    """Base exception for Enclave errors."""
    pass


class PolicyViolationError(EnclaveError):
    """Raised when agent violates access policy."""
    pass


class SecretNotFoundError(EnclaveError):
    """Raised when requested secret is not found."""
    pass


class AdapterNotFoundError(EnclaveError):
    """Raised when requested adapter is not found."""
    pass


class RateLimitExceededError(EnclaveError):
    """Raised when rate limit is exceeded."""
    pass


class AuthenticationError(EnclaveError):
    """Raised when API key authentication fails."""
    pass

