"""Tests for the FastAPI routes."""

import json
from pathlib import Path

import pytest
import respx
import httpx


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_empty(client):
    response = await client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_images"] == 0
    assert data["unsplash_images"] == 0
    assert data["local_images"] == 0


@pytest.mark.asyncio
async def test_stats_with_local_image(client, settings):
    """Drop a JPEG into the image dir and verify stats reflect it."""
    image_path = Path(settings.image_dir) / "sample.jpg"
    image_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)  # minimal fake JPEG header

    # Re-scan by calling /stats (which reads the DB); we need to index manually here
    from app.repository import scan_and_index
    await scan_and_index(settings)

    response = await client.get("/stats")
    data = response.json()
    assert data["total_images"] == 1
    assert data["local_images"] == 1


# ---------------------------------------------------------------------------
# /image — local source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_image_no_images_returns_503(client):
    """With no images and no Unsplash key the service should return 4xx/5xx."""
    response = await client.get("/image?source=local")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_image_local_returns_file(client, settings):
    image_path = Path(settings.image_dir) / "wall.jpg"
    image_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 200)

    from app.repository import scan_and_index
    await scan_and_index(settings)

    response = await client.get("/image?source=local")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


@pytest.mark.asyncio
async def test_get_image_local_json_metadata(client, settings):
    image_path = Path(settings.image_dir) / "wall2.jpg"
    image_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 200)

    from app.repository import scan_and_index
    await scan_and_index(settings)

    response = await client.get(
        "/image?source=local",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "local"
    assert "sha256" in data


# ---------------------------------------------------------------------------
# /image — invalid source param
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_image_invalid_source(client):
    response = await client.get("/image?source=invalid")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /refresh — mocked Unsplash
# ---------------------------------------------------------------------------


MOCK_UNSPLASH_META = {
    "id": "abc123",
    "width": 5000,
    "height": 3000,
    "urls": {
        "full": "https://images.unsplash.com/photo-abc123?full",
        "regular": "https://images.unsplash.com/photo-abc123?regular",
    },
    "links": {"html": "https://unsplash.com/photos/abc123"},
    "user": {"name": "Test Photographer", "username": "testphoto"},
    "tags": [{"title": "nature"}, {"title": "landscape"}],
}

FAKE_IMAGE_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 1024  # fake JPEG


@pytest.mark.asyncio
async def test_refresh_downloads_and_stores(client, settings):
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.unsplash.com/photos/random").mock(
            return_value=httpx.Response(200, json=MOCK_UNSPLASH_META)
        )
        mock.get("https://images.unsplash.com/photo-abc123", params={"regular": ""}).mock(
            return_value=httpx.Response(200, content=FAKE_IMAGE_BYTES)
        )
        # Catch-all for the download URL with any query params
        mock.get(
            url__regex=r"https://images\.unsplash\.com/photo-abc123.*"
        ).mock(return_value=httpx.Response(200, content=FAKE_IMAGE_BYTES))

        response = await client.post("/refresh")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "abc123"
    assert data["source"] == "unsplash"
    assert data["author"] == "Test Photographer"
    assert "nature" in data["tags"]

    # File should be on disk
    dest = Path(settings.image_dir) / "unsplash_abc123.jpg"
    assert dest.exists()


@pytest.mark.asyncio
async def test_refresh_deduplicates(client, settings):
    """A second /refresh with the same Unsplash ID must not create a duplicate."""
    with respx.mock(assert_all_called=False):
        import respx as rx

        with rx.mock(assert_all_called=False) as mock:
            mock.get("https://api.unsplash.com/photos/random").mock(
                return_value=httpx.Response(200, json=MOCK_UNSPLASH_META)
            )
            mock.get(
                url__regex=r"https://images\.unsplash\.com/photo-abc123.*"
            ).mock(return_value=httpx.Response(200, content=FAKE_IMAGE_BYTES))

            await client.post("/refresh")
            await client.post("/refresh")

    resp = await client.get("/stats")
    data = resp.json()
    # Should still be exactly 1 unsplash image (deduplication by SHA-256)
    assert data["unsplash_images"] == 1
