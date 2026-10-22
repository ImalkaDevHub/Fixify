import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError

from app.api.v1.health import router as health_router
from app.api.v1.projects import router as projects_router
from app.api.v1.scans import router as scans_router
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    description="Fixify project management and website scanning API",
    version="0.1.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, error: SQLAlchemyError) -> JSONResponse:
    # Registered as a normal handler so the response still passes through the CORS middleware.
    logger.error("Database error on %s %s", request.method, request.url.path, exc_info=error)
    if isinstance(error, OperationalError | InterfaceError):
        return JSONResponse({"detail": "The database is currently unavailable."}, status_code=503)
    return JSONResponse({"detail": "A database error occurred."}, status_code=500)


app.include_router(health_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(scans_router, prefix="/api/v1")
