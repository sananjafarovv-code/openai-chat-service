class ApplicationError(Exception):
    """Base exception for expected application errors."""


class SessionNotFoundError(ApplicationError):
    """Raised when a requested chat session does not exist."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Chat session '{session_id}' was not found.")


class PricingNotConfiguredError(ApplicationError):
    """Raised when no pricing is configured for a requested model."""

    def __init__(self, model: str) -> None:
        super().__init__(f"Pricing is not configured for model '{model}'.")


class OpenAIConfigurationError(ApplicationError):
    """Raised when the OpenAI client cannot be configured."""


class OpenAIServiceError(ApplicationError):
    """Raised when the upstream OpenAI request fails."""
