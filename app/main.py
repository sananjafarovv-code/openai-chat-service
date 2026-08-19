import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.sessions import router as sessions_router
from app.core.config import get_settings
from app.core.exceptions import (
    OpenAIConfigurationError,
    OpenAIConnectionError,
    OpenAIQuotaError,
    OpenAIRateLimitError,
    OpenAIServiceError,
    OpenAITimeoutError,
    PricingNotConfiguredError,
    SessionNotFoundError,
)

settings = get_settings()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.include_router(sessions_router, prefix="/sessions", tags=["sessions"])


@app.exception_handler(SessionNotFoundError)
def handle_session_not_found(_: Request, exc: SessionNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(PricingNotConfiguredError)
def handle_pricing_not_configured(_: Request, exc: PricingNotConfiguredError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": str(exc)},
    )


@app.exception_handler(OpenAIConfigurationError)
def handle_openai_configuration(_: Request, exc: OpenAIConfigurationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)},
    )


@app.exception_handler(OpenAIQuotaError)
def handle_openai_quota(_: Request, exc: OpenAIQuotaError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)},
    )


@app.exception_handler(OpenAIRateLimitError)
def handle_openai_rate_limit(_: Request, exc: OpenAIRateLimitError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": str(exc)},
    )


@app.exception_handler(OpenAITimeoutError)
def handle_openai_timeout(_: Request, exc: OpenAITimeoutError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content={"detail": str(exc)},
    )


@app.exception_handler(OpenAIConnectionError)
def handle_openai_connection(_: Request, exc: OpenAIConnectionError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)},
    )


@app.exception_handler(OpenAIServiceError)
def handle_openai_service(_: Request, exc: OpenAIServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc)},
    )


@app.exception_handler(SQLAlchemyError)
def handle_database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error("Database request failed: type=%s", type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Database operation failed."},
    )


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
