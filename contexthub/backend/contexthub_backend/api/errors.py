"""Exception types and FastAPI exception handlers.

Error envelope shape (all error responses):
    { "error": { "code": str, "message": str, "request_id": str } }
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class AuthError(Exception):
    def __init__(self, message: str = "unauthorized") -> None:
        self.message = message
        super().__init__(message)


class ForbiddenError(Exception):
    def __init__(self, message: str = "forbidden") -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(Exception):
    def __init__(self, message: str = "not found") -> None:
        self.message = message
        super().__init__(message)


class ValidationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _err(status: int, code: str, message: str, request_id: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )


def _rid(request: Request) -> str:
    return request.state.request_id if hasattr(request.state, "request_id") else ""


async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    return _err(401, "unauthorized", exc.message, _rid(request))


async def forbidden_error_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
    return _err(403, "forbidden", exc.message, _rid(request))


async def not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return _err(404, "not_found", exc.message, _rid(request))


async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return _err(422, "validation_error", exc.message, _rid(request))
