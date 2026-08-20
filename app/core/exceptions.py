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


class SessionGenerationConflictError(ApplicationError):
    """Raised when a session is reset while an interaction is in progress."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            f"Chat session '{session_id}' was reset while the message was being processed."
        )


class OpenAIConfigurationError(ApplicationError):
    """Raised when the OpenAI client cannot be configured."""


class OpenAIServiceError(ApplicationError):
    """Raised when the upstream OpenAI request fails."""


class OpenAITimeoutError(OpenAIServiceError):
    """Raised when the upstream OpenAI request times out."""


class OpenAIConnectionError(OpenAIServiceError):
    """Raised when the OpenAI API cannot be reached."""


class OpenAIRateLimitError(OpenAIServiceError):
    """Raised when OpenAI rejects a request because of a rate limit."""


class OpenAIQuotaError(OpenAIServiceError):
    """Raised when the OpenAI project has no available API credits."""
