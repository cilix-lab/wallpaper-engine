"""Image selection strategies."""

import logging
from pathlib import Path

from sqlalchemy import func, select

from .config import Settings
from .database import db
from .models import Image
from .repository import get_image_by_id, persist_image
from .unsplash import download_wallpaper

logger = logging.getLogger(__name__)


class ImageNotFoundError(Exception):
    pass


async def select_image(
    settings: Settings,
    source: str | None = None,
    refresh: bool = False,
    image_id: str | None = None,
) -> tuple[Image, Path]:
    """
    Return ``(Image, absolute_path)`` according to the requested strategy.

    *source* values: ``"local"`` | ``"unsplash"`` | ``"hybrid"``

    If *refresh* is True, always fetch a fresh image from Unsplash.
    If *image_id* is given, look up that specific image and ignore other params.
    """
    if image_id is not None:
        image = await get_image_by_id(image_id)
        if image is None:
            raise ImageNotFoundError(f"No image with id '{image_id}'")
        return image, Path(settings.image_dir) / image.filename

    effective_source = (source or settings.default_source).lower()

    if refresh:
        return await _unsplash_fresh(settings)

    if effective_source == "local":
        return await _local_random(settings)

    if effective_source == "unsplash":
        # Prefer cached; fall through to fresh fetch if cache is empty
        result = await _unsplash_cached(settings)
        if result is not None:
            return result
        logger.info("Unsplash cache empty — fetching fresh image")
        return await _unsplash_fresh(settings)

    # hybrid (default): random across all stored images
    result = await _hybrid_random(settings)
    if result is not None:
        return result
    # No images at all — fetch from Unsplash
    logger.info("No local images — fetching from Unsplash")
    return await _unsplash_fresh(settings)


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------


async def _local_random(settings: Settings) -> tuple[Image, Path]:
    async with db.session() as session:
        image = (
            await session.execute(
                select(Image)
                .where(Image.source == "local")
                .order_by(func.random())
                .limit(1)
            )
        ).scalar_one_or_none()
    if image is None:
        raise ImageNotFoundError("No local images available")
    return image, Path(settings.image_dir) / image.filename


async def _unsplash_cached(settings: Settings) -> tuple[Image, Path] | None:
    async with db.session() as session:
        image = (
            await session.execute(
                select(Image)
                .where(Image.source == "unsplash")
                .order_by(Image.downloaded_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if image is None:
        return None
    return image, Path(settings.image_dir) / image.filename


async def _unsplash_fresh(settings: Settings) -> tuple[Image, Path]:
    image = await download_wallpaper(settings)
    image = await persist_image(image)
    return image, Path(settings.image_dir) / image.filename


async def _hybrid_random(settings: Settings) -> tuple[Image, Path] | None:
    async with db.session() as session:
        image = (
            await session.execute(
                select(Image).order_by(func.random()).limit(1)
            )
        ).scalar_one_or_none()
    if image is None:
        return None
    return image, Path(settings.image_dir) / image.filename
