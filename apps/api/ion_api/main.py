from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ion_api.db import create_database_engine
from ion_api.home import HomeService
from ion_api.home_routes import home_router
from ion_api.logging import configure_logging
from ion_api.migrations import upgrade_to_head
from ion_api.organizer import OrganizerService
from ion_api.organizer_routes import organizer_router
from ion_api.settings import Settings, load_settings
from ion_api.task_routes import task_router
from ion_api.tasks import TaskService
from ion_api.today import TodayService
from ion_api.today_routes import today_router

SESSION_HEADER = "X-Ion-Session"


def _base_app(settings: Settings) -> FastAPI:
    active_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        configure_logging(active_settings.log_path)
        logging.getLogger("ion").info("Ion local API started")
        yield
        logging.getLogger("ion").info("Ion local API stopped")

    app = FastAPI(title="Ion local API", version="0.0.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(_: Request, __: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": {"code": "validation", "blockers": []},
            },
        )

    return app


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the explicitly unauthenticated Phase 0B development API."""

    active_settings = settings or load_settings()
    app = _base_app(active_settings)
    # These exact origins are required only for Vite development and the Tauri
    # WebView. Wildcard CORS would violate the local-service boundary.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=[],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    engine = create_database_engine(active_settings.database_path)
    app.include_router(home_router(HomeService(engine)))
    app.include_router(task_router(TaskService(engine)))
    app.include_router(organizer_router(OrganizerService(engine)))
    app.include_router(today_router(TodayService(engine)))
    return app


def create_production_app(settings: Settings, session_token: str) -> FastAPI:
    """Create the fail-closed production API used only by the Rust owner."""

    if not session_token:
        raise ValueError("production session token is required")
    app = _base_app(settings)

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        supplied = request.headers.get(SESSION_HEADER, "")
        if not hmac.compare_digest(supplied, session_token):
            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    engine = create_database_engine(settings.database_path)
    app.include_router(home_router(HomeService(engine)))
    app.include_router(task_router(TaskService(engine)))
    app.include_router(organizer_router(OrganizerService(engine)))
    app.include_router(today_router(TodayService(engine)))
    return app


app = create_app()


def run() -> None:
    settings = load_settings()
    upgrade_to_head(settings.database_path)
    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    run()
