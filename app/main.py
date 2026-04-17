"""Application factory and entry point."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .database import db
from .logging_config import configure_logging
from .repository import scan_and_index
from .routes import router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting wallpaper-engine service")
        await db.init(settings.db_path)
        added = await scan_and_index(settings)
        logger.info("Repository indexed", extra={"new_images": added})
        yield
        logger.info("Shutting down wallpaper-engine service")
        await db.close()

    app = FastAPI(
        title="Wallpaper Engine",
        description="Linux Wallpaper Service — Unsplash + Local Repository",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


# Allow running with `python -m app.main`
if __name__ == "__main__":
    settings = get_settings()
    configure_logging(settings.log_level)
    app = create_app(settings)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.port,
        log_config=None,  # We handle logging ourselves
    )
