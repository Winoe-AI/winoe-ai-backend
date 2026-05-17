"""Application module for media routes media fake storage routes workflows."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.integrations.storage_media import StorageMediaProvider
from app.integrations.storage_media.integrations_storage_media_storage_media_base_client import (
    StorageMediaError,
)
from app.integrations.storage_media.integrations_storage_media_storage_media_fake_provider_client import (
    FakeStorageMediaProvider,
)
from app.shared.http.dependencies.shared_http_dependencies_storage_media_utils import (
    get_media_storage_provider,
)

router = APIRouter(prefix="/storage/fake", tags=["recordings"])


def _require_fake_provider(
    storage_provider: StorageMediaProvider,
) -> FakeStorageMediaProvider:
    if not isinstance(storage_provider, FakeStorageMediaProvider):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fake media storage routes are unavailable",
        )
    return storage_provider


def _unprocessable(detail: str, exc: Exception | None = None) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=detail,
    ) from exc


def _parse_byte_range(range_header: str, size_bytes: int) -> tuple[int, int] | None:
    value = range_header.strip()
    if not value or not value.startswith("bytes="):
        return None
    if "," in value:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="Multiple byte ranges are not supported",
        )

    byte_range = value.removeprefix("bytes=").strip()
    start_text, end_text = byte_range.split("-", 1)
    if not start_text and not end_text:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="Invalid byte range",
        )

    if start_text:
        start = int(start_text)
        end = size_bytes - 1 if not end_text else int(end_text)
    else:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Invalid byte range",
            )
        start = max(size_bytes - suffix_length, 0)
        end = size_bytes - 1

    if start < 0 or start >= size_bytes:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="Requested range starts beyond the media size",
        )
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="Invalid byte range",
        )
    return start, min(end, size_bytes - 1)


def _media_response_headers(filename: str, *, size_bytes: int) -> dict[str, str]:
    return {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{filename}"',
        "Content-Length": str(size_bytes),
    }


@router.put(
    "/upload",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "Object uploaded"},
        status.HTTP_403_FORBIDDEN: {"description": "Signed URL rejected"},
        status.HTTP_404_NOT_FOUND: {"description": "Fake storage disabled"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Upload rejected"},
    },
)
async def fake_storage_upload_route(
    request: Request,
    key: Annotated[str, Query(..., min_length=1)],
    contentType: Annotated[str, Query(..., min_length=1)],
    sizeBytes: Annotated[int, Query(..., gt=0)],
    expiresAt: Annotated[int, Query(..., gt=0)],
    sig: Annotated[str, Query(..., min_length=16)],
    storage_provider: Annotated[
        StorageMediaProvider, Depends(get_media_storage_provider)
    ],
    durationSeconds: Annotated[int | None, Query(gt=0)] = None,
) -> Response:
    """Accept a signed fake-storage upload for local live validation."""
    provider = _require_fake_provider(storage_provider)
    try:
        safe_key = provider.validate_signed_upload_request(
            key=key,
            content_type=contentType,
            size_bytes=sizeBytes,
            expires_at=expiresAt,
            signature=sig,
            duration_seconds=durationSeconds,
        )
    except StorageMediaError as exc:
        detail = str(exc)
        status_code = (
            status.HTTP_403_FORBIDDEN
            if "signature" in detail.lower() or "expired" in detail.lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc
    body = await request.body()
    if len(body) != int(sizeBytes):
        _unprocessable("Uploaded object size does not match expected size")
    try:
        provider.write_object_bytes(
            safe_key,
            content_type=contentType,
            data=body,
            duration_seconds=durationSeconds,
        )
    except StorageMediaError as exc:
        _unprocessable(str(exc), exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/download",
    responses={
        status.HTTP_200_OK: {"description": "Object downloaded"},
        status.HTTP_403_FORBIDDEN: {"description": "Signed URL rejected"},
        status.HTTP_404_NOT_FOUND: {"description": "Object not found"},
    },
)
async def fake_storage_download_route(
    request: Request,
    key: Annotated[str, Query(..., min_length=1)],
    expiresAt: Annotated[int, Query(..., gt=0)],
    sig: Annotated[str, Query(..., min_length=16)],
    storage_provider: Annotated[
        StorageMediaProvider, Depends(get_media_storage_provider)
    ],
):
    """Serve a signed fake-storage download for local browser and worker use."""
    provider = _require_fake_provider(storage_provider)
    try:
        safe_key = provider.validate_signed_download_request(
            key=key,
            expires_at=expiresAt,
            signature=sig,
        )
    except StorageMediaError as exc:
        detail = str(exc)
        status_code = (
            status.HTTP_403_FORBIDDEN
            if "signature" in detail.lower() or "expired" in detail.lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc
    metadata = provider.get_object_metadata(safe_key)
    if metadata is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded object not found",
        )
    try:
        object_path = provider.object_path(safe_key)
    except StorageMediaError as exc:
        _unprocessable(str(exc), exc)
    if not object_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded object not found",
        )
    filename = safe_key.rsplit("/", 1)[-1]
    media_bytes = object_path.read_bytes()
    range_header = request.headers.get("range")
    if range_header:
        byte_range = _parse_byte_range(range_header, len(media_bytes))
        if byte_range is not None:
            start, end = byte_range
            sliced = media_bytes[start : end + 1]
            headers = _media_response_headers(filename, size_bytes=len(sliced))
            headers["Content-Range"] = f"bytes {start}-{end}/{len(media_bytes)}"
            return Response(
                content=sliced,
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                media_type=metadata.content_type,
                headers=headers,
            )

    headers = _media_response_headers(filename, size_bytes=len(media_bytes))
    return Response(
        content=media_bytes,
        status_code=status.HTTP_200_OK,
        media_type=metadata.content_type,
        headers=headers,
    )


__all__ = [
    "fake_storage_download_route",
    "fake_storage_upload_route",
    "router",
]
