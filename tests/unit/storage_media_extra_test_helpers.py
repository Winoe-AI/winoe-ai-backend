from __future__ import annotations
from urllib.error import HTTPError
import pytest
from fastapi import HTTPException
import app.integrations.storage_media.s3_provider as s3_module
from app.core.settings import settings
from app.integrations.storage_media import (
    FakeStorageMediaProvider,
    S3StorageMediaProvider,
    ensure_safe_storage_key,
    get_storage_media_provider,
)
from app.integrations.storage_media.base import StorageMediaError
from app.services.media.keys import (
    build_recording_storage_key,
    normalize_extension,
    parse_recording_public_id,
)
from app.services.media.validation import validate_upload_input

def _build_s3_provider(*, use_path_style: bool = True) -> S3StorageMediaProvider:
    return S3StorageMediaProvider(
        endpoint="https://storage.example.com:9000/base",
        region="us-east-1",
        bucket="media-bucket",
        access_key_id="AKIA_TEST",
        secret_access_key="secret_test_key",
        use_path_style=use_path_style,
    )

__all__ = [name for name in globals() if not name.startswith("__")]
