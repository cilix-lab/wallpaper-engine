"""Tests for the Unsplash API client."""

from pathlib import Path

import httpx
import pytest
import respx

from app.unsplash import _pick_url, download_wallpaper, fetch_metadata

MOCK_META = {
    "id": "xyz789",
    "width": 4000,
    "height": 2500,
    "urls": {
        "full": "https://images.unsplash.com/photo-xyz789?full",
        "regular": "https://images.unsplash.com/photo-xyz789?regular",
    },
    "links": {"html": "https://unsplash.com/photos/xyz789"},
    "user": {"name": "Jane Doe", "username": "janedoe"},
    "tags": [{"title": "mountains"}, {"title": "snow"}],
}

FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 512


# ---------------------------------------------------------------------------
# fetch_metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_metadata_success(settings):
    with respx.mock() as mock:
        mock.get("https://api.unsplash.com/photos/random").mock(
            return_value=httpx.Response(200, json=MOCK_META)
        )
        data = await fetch_metadata(settings)

    assert data["id"] == "xyz789"


@pytest.mark.asyncio
async def test_fetch_metadata_no_key_raises(settings, monkeypatch):
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    empty_settings = get_settings()

    with pytest.raises(ValueError, match="UNSPLASH_ACCESS_KEY"):
        await fetch_metadata(empty_settings)


@pytest.mark.asyncio
async def test_fetch_metadata_http_error_retries(settings):
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(500)
        return httpx.Response(200, json=MOCK_META)

    with respx.mock() as mock:
        mock.get("https://api.unsplash.com/photos/random").mock(side_effect=side_effect)
        data = await fetch_metadata(settings)

    assert data["id"] == "xyz789"
    assert call_count == 3


# ---------------------------------------------------------------------------
# download_wallpaper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_wallpaper_creates_file(settings):
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.unsplash.com/photos/random").mock(
            return_value=httpx.Response(200, json=MOCK_META)
        )
        mock.get(url__regex=r"https://images\.unsplash\.com/photo-xyz789.*").mock(
            return_value=httpx.Response(200, content=FAKE_JPEG)
        )

        image = await download_wallpaper(settings)

    dest = Path(settings.image_dir) / "unsplash_xyz789.jpg"
    assert dest.exists()
    assert image.id == "xyz789"
    assert image.source == "unsplash"
    assert image.author == "Jane Doe"
    assert image.sha256 is not None


@pytest.mark.asyncio
async def test_download_wallpaper_exceeds_size_limit(settings, monkeypatch):
    monkeypatch.setenv("MAX_IMAGE_SIZE_MB", "0")
    from app.config import get_settings
    get_settings.cache_clear()
    small_limit_settings = get_settings()

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.unsplash.com/photos/random").mock(
            return_value=httpx.Response(200, json=MOCK_META)
        )
        mock.get(url__regex=r"https://images\.unsplash\.com/photo-xyz789.*").mock(
            return_value=httpx.Response(200, content=FAKE_JPEG)
        )

        with pytest.raises(ValueError, match="exceeds max size"):
            await download_wallpaper(small_limit_settings)


# ---------------------------------------------------------------------------
# _pick_url
# ---------------------------------------------------------------------------


def test_pick_url_prefers_full():
    urls = {"thumb": "t", "small": "s", "regular": "r", "full": "f", "raw": "raw"}
    assert _pick_url(urls, 10_000_000) == "f"


def test_pick_url_falls_back_to_regular():
    urls = {"regular": "r", "small": "s"}
    assert _pick_url(urls, 10_000_000) == "r"


def test_pick_url_raises_when_empty():
    with pytest.raises(ValueError):
        _pick_url({}, 10_000_000)
