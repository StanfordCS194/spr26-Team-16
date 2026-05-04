"""FastAPI application factory."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from contexthub_backend.api.errors import (
    AuthError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
    auth_error_handler,
    forbidden_error_handler,
    not_found_error_handler,
    programming_error_handler,
    validation_error_handler,
)
from contexthub_backend.api.routes import auth as auth_routes
from contexthub_backend.api.routes import health as health_routes
from contexthub_backend.api.routes import pulls as pull_routes
from contexthub_backend.api.routes import pushes as push_routes
from contexthub_backend.api.routes import search as search_routes
from contexthub_backend.auth import dependencies as auth_deps
from contexthub_backend.config import settings


def create_app(engine: AsyncEngine | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Pass `engine` in tests to inject the test DB engine before any requests.
    """
    if engine is not None:
        auth_deps._set_engine(engine)

    app = FastAPI(
        title="ContextHub API",
        version=settings.app_version,
        docs_url="/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1):\d+$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    # Request-ID middleware
    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    # Exception handlers
    app.add_exception_handler(AuthError, auth_error_handler)
    app.add_exception_handler(ForbiddenError, forbidden_error_handler)
    app.add_exception_handler(NotFoundError, not_found_error_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(ProgrammingError, programming_error_handler)

    # Routers
    app.include_router(health_routes.router, prefix="/v1")
    app.include_router(auth_routes.router, prefix="/v1")
    app.include_router(push_routes.router, prefix="/v1")
    app.include_router(search_routes.router, prefix="/v1")
    app.include_router(pull_routes.router, prefix="/v1")

    return app
