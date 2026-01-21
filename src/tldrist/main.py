"""FastAPI application entry point for TLDRist."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from tldrist import __version__
from tldrist.api.routes import router
from tldrist.config import get_settings
from tldrist.utils.logging import get_logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = get_logger(__name__)
    logger.info("TL;DRist starting", version=__version__)
    yield
    logger.info("TL;DRist shutting down")


app = FastAPI(
    title="TLDRist",
    description="Weekly digest of Todoist Read list articles summarized with Gemini",
    version=__version__,
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with basic info."""
    return {
        "name": "TLDRist",
        "version": __version__,
        "docs": "/docs",
    }
