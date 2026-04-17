"""Tests for the local repository scanner."""

import hashlib
from pathlib import Path

import pytest

from app.repository import _hash_file, scan_and_index


@pytest.mark.asyncio
async def test_scan_indexes_new_images(settings):
    image_dir = Path(settings.image_dir)
    (image_dir / "a.jpg").write_bytes(b"\xff\xd8\xff" + b"\xAA" * 256)
    (image_dir / "b.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\xBB" * 256)

    added = await scan_and_index(settings)
    assert added == 2


@pytest.mark.asyncio
async def test_scan_skips_duplicates(settings):
    image_dir = Path(settings.image_dir)
    content = b"\xff\xd8\xff" + b"\xCC" * 512
    (image_dir / "dup1.jpg").write_bytes(content)
    (image_dir / "dup2.jpg").write_bytes(content)  # identical content

    added = await scan_and_index(settings)
    assert added == 1  # only one should be indexed


@pytest.mark.asyncio
async def test_scan_ignores_disallowed_extensions(settings):
    image_dir = Path(settings.image_dir)
    (image_dir / "script.sh").write_bytes(b"#!/bin/bash\n")
    (image_dir / "document.pdf").write_bytes(b"%PDF-1.4")

    added = await scan_and_index(settings)
    assert added == 0


@pytest.mark.asyncio
async def test_scan_removes_stale_entries(settings):
    image_dir = Path(settings.image_dir)
    p = image_dir / "temp.jpg"
    p.write_bytes(b"\xff\xd8\xff" + b"\xDD" * 128)

    added = await scan_and_index(settings)
    assert added == 1

    p.unlink()

    added2 = await scan_and_index(settings)
    assert added2 == 0

    # Verify DB no longer contains the stale entry
    from app.database import db
    from app.models import Image
    from sqlalchemy import select

    async with db.session() as session:
        count = len((await session.execute(select(Image))).scalars().all())
    assert count == 0


def test_hash_file(tmp_path):
    p = tmp_path / "test.bin"
    data = b"hello world"
    p.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert _hash_file(p) == expected
