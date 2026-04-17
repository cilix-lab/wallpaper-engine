"""Unsplash API client — fetch metadata and download wallpaper images."""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import Settings
from .models import Image

logger = logging.getLogger(__name__)

UNSPLASH_API = "https://api.unsplash.com/photos/random"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


# ---------------------------------------------------------------------------
# Retry decorator shared by network calls
# ---------------------------------------------------------------------------

_retry = retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


@_retry
async def fetch_metadata(settings: Settings, query: str = "") -> dict:
    """Return raw Unsplash JSON for a random landscape wallpaper."""
    if not settings.unsplash_access_key:
        raise ValueError("UNSPLASH_ACCESS_KEY is not configured")

    params: dict = {
        "orientation": "landscape",
        "content_filter": "high",
    }
    effective_query = query or settings.unsplash_query
    if effective_query:
        params["query"] = effective_query

    headers = {"Authorization": f"Client-ID {settings.unsplash_access_key}"}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(UNSPLASH_API, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

    logger.info("Fetched Unsplash metadata", extra={"unsplash_id": data.get("id")})
    return data


async def download_wallpaper(settings: Settings, query: str = "") -> Image:
    """
    Fetch a random wallpaper from Unsplash, save it to *IMAGE_DIR*, and return
    an unsaved :class:`Image` ORM instance (caller must persist to DB).
    """
    meta = await fetch_metadata(settings, query=query)
    image_id: str = meta["id"]
    image_dir = Path(settings.image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    # Pick the best available URL within the size cap
    max_bytes = settings.max_image_size_mb * 1024 * 1024
    urls: dict = meta.get("urls", {})
    download_url = _pick_url(urls, max_bytes)

    # Derive a safe filename
    filename = f"unsplash_{image_id}.jpg"
    dest = image_dir / filename

    logger.info("Downloading Unsplash image", extra={"url": download_url, "dest": str(dest)})
    sha256 = await _download_file(download_url, dest, max_bytes)

    tags_raw = meta.get("tags") or []
    tags = json.dumps([t.get("title", "") for t in tags_raw if isinstance(t, dict)])

    user = meta.get("user") or {}
    author = user.get("name") or user.get("username")

    width: int | None = meta.get("width")
    height: int | None = meta.get("height")

    return Image(
        id=image_id,
        sha256=sha256,
        filename=filename,
        source="unsplash",
        author=author,
        unsplash_url=meta.get("links", {}).get("html"),
        tags=tags,
        downloaded_at=datetime.now(tz=timezone.utc),
        file_size=dest.stat().st_size,
        width=width,
        height=height,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pick_url(urls: dict, max_bytes: int) -> str:
    """Return the best quality URL that is likely within the byte budget."""
    # Unsplash sizes: raw > full > regular > small > thumb
    for key in ("full", "regular", "small", "thumb", "raw"):
        if key in urls:
            return urls[key]
    raise ValueError("No usable URL found in Unsplash response")


@_retry
async def _download_file(url: str, dest: Path, max_bytes: int) -> str:
    """Stream *url* to *dest* and return its SHA-256 hex digest."""
    hasher = hashlib.sha256()
    total = 0

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in response.aiter_bytes(chunk_size=65_536):
                    total += len(chunk)
                    if total > max_bytes:
                        fh.close()
                        dest.unlink(missing_ok=True)
                        raise ValueError(
                            f"Image exceeds max size of {max_bytes} bytes"
                        )
                    hasher.update(chunk)
                    fh.write(chunk)

    return hasher.hexdigest()
