from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ion_api.logging import configure_logging
from ion_api.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        configure_logging(active_settings.log_path)
        logging.getLogger("ion").info("Ion local API started")
        yield
        logging.getLogger("ion").info("Ion local API stopped")

    app = FastAPI(title="Ion local API", version="0.0.0", lifespan=lifespan)
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


app = create_app()


def run() -> None:
    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    run()
