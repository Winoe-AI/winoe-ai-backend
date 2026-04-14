"""Application module for http routes health routes workflows."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.shared.http import shared_http_readiness_service as readiness_service
from app.shared.http.schemas import ReadinessPayload

router = APIRouter()


@router.get(
    "/health",
    summary="Health Check",
    description="Lightweight liveness probe for process and routing health.",
    responses={
        500: {"description": "Process is unhealthy."},
    },
)
async def health_check():
    """Liveness probe endpoint."""
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Readiness Check",
    description="Readiness probe for database, worker, and integration configuration.",
    response_model=ReadinessPayload,
    responses={
        200: {"description": "System is ready."},
        503: {
            "description": "System is not ready.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ReadinessPayload"}
                }
            },
        },
    },
)
async def readiness_check():
    """Readiness probe endpoint."""
    payload = await readiness_service.build_readiness_payload()
    if payload.get("status") != "ready":
        return JSONResponse(status_code=503, content=payload)
    return payload
