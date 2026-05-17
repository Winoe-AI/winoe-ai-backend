from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from app.integrations.storage_media import (
    FakeStorageMediaProvider,
    get_storage_media_provider,
)


@pytest.mark.asyncio
async def test_fake_storage_download_supports_byte_ranges(async_client):
    get_storage_media_provider.cache_clear()
    provider = get_storage_media_provider()
    assert isinstance(provider, FakeStorageMediaProvider)

    key = "qa/tests/range-video.webm"
    provider.write_object_bytes(
        key,
        content_type="video/webm",
        data=b"abcdefghij",
    )
    try:
        signed_url = provider.create_signed_download_url(key, expires_seconds=3600)
        parsed = urlsplit(signed_url)

        ranged_response = await async_client.get(
            f"{parsed.path}?{parsed.query}",
            headers={"Range": "bytes=2-5"},
        )
        assert ranged_response.status_code == 206, ranged_response.text
        assert ranged_response.headers["accept-ranges"] == "bytes"
        assert ranged_response.headers["content-range"] == "bytes 2-5/10"
        assert ranged_response.content == b"cdef"

        full_response = await async_client.get(f"{parsed.path}?{parsed.query}")
        assert full_response.status_code == 200, full_response.text
        assert full_response.headers["accept-ranges"] == "bytes"
        assert full_response.content == b"abcdefghij"
    finally:
        provider.delete_object(key)
        get_storage_media_provider.cache_clear()
