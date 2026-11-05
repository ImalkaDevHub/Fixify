import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.deps import CSRF_HEADER
from app.api.v1.ai import router as ai_router
from app.api.v1.auth import router as auth_router
from app.api.v1.fixes import router as fixes_router
from app.api.v1.github import router as github_router
from app.api.v1.health import router as health_router
from app.api.v1.platform import router as platform_router
from app.api.v1.projects import router as projects_router
from app.api.v1.scans import router as scans_router
from app.api.v1.users import router as users_router
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
]


class SecurityHeadersMiddleware:
    """Adds conservative headers to every API response (pure ASGI, so streaming is unaffected)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                headers.extend(item for item in _SECURITY_HEADERS if item[0] not in present)
                if b"cache-control" not in present:
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


app = FastAPI(
    title=settings.app_name,
    description="Fixify: website testing, AI analysis, and human-reviewed fixes",
    version="0.2.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)
app.add_middleware(SecurityHeadersMiddleware)
# The web app normally reaches the API through its own origin (Next.js rewrites), so CORS is
# only needed when the API is called directly from another trusted origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", CSRF_HEADER],
)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, error: SQLAlchemyError) -> JSONResponse:
    # Registered as a normal handler so the response still passes through the CORS middleware.
    logger.error("Database error on %s %s", request.method, request.url.path, exc_info=error)
    if isinstance(error, OperationalError | InterfaceError):
        return JSONResponse({"detail": "The database is currently unavailable."}, status_code=503)
    return JSONResponse({"detail": "A database error occurred."}, status_code=500)


for router in (
    health_router,
    auth_router,
    users_router,
    projects_router,
    scans_router,
    platform_router,
    ai_router,
    github_router,
    fixes_router,
):
    app.include_router(router, prefix="/api/v1")
