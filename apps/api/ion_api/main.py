from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from ion_api.logging import configure_logging
from ion_api.settings import Settings, load_settings

SESSION_HEADER = "X-Ion-Session"


def _base_app(settings: Settings) -> FastAPI:
    active_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        configure_logging(active_settings.log_path)
        logging.getLogger("ion").info("Ion local API started")
        yield
        logging.getLogger("ion").info("Ion local API stopped")

    return FastAPI(title="Ion local API", version="0.0.0", lifespan=lifespan)


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
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def run() -> None:
    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    run()
