"""Shared pytest fixtures."""

import asyncio
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.database import db
from app.main import create_app


# ---------------------------------------------------------------------------
# Override settings for every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear the lru_cache on get_settings between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path: Path, monkeypatch) -> Settings:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    db_path = str(tmp_path / "metadata.db")

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "test-key-abc123")
    monkeypatch.setenv("IMAGE_DIR", str(image_dir))
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("DEFAULT_SOURCE", "hybrid")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    get_settings.cache_clear()
    return get_settings()


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(settings) -> AsyncGenerator[AsyncClient, None]:
    # Reset database singleton so each test gets a fresh DB
    await db.close()

    app = create_app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Trigger lifespan (startup)
        async with app.router.lifespan_context(app):
            yield ac

    await db.close()
