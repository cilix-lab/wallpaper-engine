"""Local image repository — scan, index, and deduplicate images on disk."""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from .config import Settings
from .database import db
from .models import Image

logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def scan_and_index(settings: Settings) -> int:
    """
    Walk *IMAGE_DIR*, register every unrecognised image, and purge DB rows
    whose files no longer exist.  Returns the number of newly added entries.
    """
    image_dir = Path(settings.image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    added = 0
    async with db.session() as session:
        # ── Remove stale entries ──────────────────────────────────────────
        result = await session.execute(select(Image))
        all_records: list[Image] = result.scalars().all()
        for record in all_records:
            path = image_dir / record.filename
            if not path.exists():
                logger.info("Removing stale DB entry", extra={"image": record.filename})
                await session.delete(record)

        # ── Index new files ───────────────────────────────────────────────
        existing_filenames: set[str] = {r.filename for r in all_records if (image_dir / r.filename).exists()}
        existing_hashes: set[str] = {r.sha256 for r in all_records if (image_dir / r.filename).exists()}

        for path in sorted(image_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            if path.name in existing_filenames:
                continue

            sha256 = _hash_file(path)
            if sha256 in existing_hashes:
                logger.debug("Skipping duplicate file", extra={"image": path.name})
                continue

            image = Image(
                id=str(uuid.uuid4()),
                sha256=sha256,
                filename=path.name,
                source="local",
                downloaded_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
                file_size=path.stat().st_size,
            )
            session.add(image)
            existing_hashes.add(sha256)
            added += 1
            logger.info("Indexed local image", extra={"image": path.name})

    logger.info("Repository scan complete", extra={"added": added})
    return added


async def get_stats(settings: Settings) -> dict:
    """Return aggregate statistics about the local repository."""
    image_dir = Path(settings.image_dir)
    async with db.session() as session:
        total = (await session.execute(select(func.count()).select_from(Image))).scalar_one()
        unsplash_count = (
            await session.execute(
                select(func.count()).select_from(Image).where(Image.source == "unsplash")
            )
        ).scalar_one()
        local_count = (
            await session.execute(
                select(func.count()).select_from(Image).where(Image.source == "local")
            )
        ).scalar_one()

    disk_bytes = sum(
        f.stat().st_size
        for f in image_dir.iterdir()
        if f.is_file() and f.suffix.lower() in ALLOWED_SUFFIXES
    ) if image_dir.exists() else 0

    return {
        "total_images": total,
        "unsplash_images": unsplash_count,
        "local_images": local_count,
        "disk_usage_bytes": disk_bytes,
        "disk_usage_mb": round(disk_bytes / (1024 * 1024), 2),
    }


async def persist_image(image: Image) -> Image:
    """
    Save *image* to the database.  If an entry with the same SHA-256 already
    exists, return the existing record instead.
    """
    async with db.session() as session:
        existing = (
            await session.execute(select(Image).where(Image.sha256 == image.sha256))
        ).scalar_one_or_none()
        if existing is not None:
            logger.debug("Duplicate SHA-256 — returning existing record", extra={"sha256": image.sha256})
            return existing
        session.add(image)
    return image


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
