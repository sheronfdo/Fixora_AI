"""Typed API errors and a consistent error envelope."""
from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Raised anywhere in the app to produce a structured error response."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


# Convenience constructors for the documented error contract.
def unauthorized(message: str = "Invalid or missing credentials") -> ApiError:
    return ApiError(401, "unauthorized", message)


def forbidden(message: str = "You do not have access to this resource") -> ApiError:
    return ApiError(403, "forbidden", message)


def not_found(message: str = "Resource not found") -> ApiError:
    return ApiError(404, "not_found", message)


def unprocessable(message: str = "Insufficient data to complete the request") -> ApiError:
    return ApiError(422, "unprocessable", message)


def rate_limited(message: str = "Too many requests") -> ApiError:
    return ApiError(429, "rate_limited", message)


def upstream_unavailable(message: str = "Upstream service unavailable") -> ApiError:
    return ApiError(503, "upstream_unavailable", message)


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
