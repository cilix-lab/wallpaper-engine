"""FastAPI route definitions."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from .config import Settings, get_settings
from .repository import get_stats, persist_image, scan_and_index
from .selector import ImageNotFoundError, select_image
from .unsplash import download_wallpaper

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# GET /image
# ---------------------------------------------------------------------------


@router.get("/image")
async def get_image(
    request: Request,
    source: str = Query(default=None, description="local | unsplash | hybrid"),
    refresh: bool = Query(default=False, description="Force a fresh Unsplash fetch"),
    settings: Settings = Depends(get_settings),
):
    """
    Return a wallpaper image.

    * Send ``Accept: application/json`` to receive metadata instead of the file.
    * Use ``?source=local|unsplash|hybrid`` to control the selection pool.
    * Use ``?refresh=true`` to force a fresh Unsplash download.
    """
    _validate_source(source)
    try:
        image, path = await select_image(settings, source=source, refresh=refresh)
    except ImageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return _image_to_json(image)

    return FileResponse(
        path=str(path),
        media_type=_media_type(path),
    )


# ---------------------------------------------------------------------------
# POST /refresh
# ---------------------------------------------------------------------------


@router.post("/refresh")
async def refresh_image(
    settings: Settings = Depends(get_settings),
):
    """Fetch a new image from Unsplash, store it, and return its metadata."""
    try:
        image = await download_wallpaper(settings)
        image = await persist_image(image)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _image_to_json(image)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


@router.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------


@router.get("/stats")
async def stats(settings: Settings = Depends(get_settings)):
    return await get_stats(settings)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_source(source: str | None) -> None:
    valid = {None, "local", "unsplash", "hybrid"}
    if source not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source '{source}'. Must be one of: local, unsplash, hybrid.",
        )


def _media_type(path: Path) -> str:
    return "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"


def _image_to_json(image) -> JSONResponse:
    tags = []
    if image.tags:
        try:
            tags = json.loads(image.tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    return JSONResponse(
        content={
            "id": image.id,
            "filename": image.filename,
            "source": image.source,
            "author": image.author,
            "unsplash_url": image.unsplash_url,
            "tags": tags,
            "downloaded_at": image.downloaded_at.isoformat() if image.downloaded_at else None,
            "file_size": image.file_size,
            "width": image.width,
            "height": image.height,
            "sha256": image.sha256,
        }
    )
