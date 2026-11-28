from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from repobrain.database.models import IngestionState
from repobrain.ingestion.github import (
    REPOSITORY_PATTERN,
    IngestionError,
    canonical_repository,
    validate_ref,
)
from repobrain.ingestion.service import Failure, IngestionService, SnapshotStatus

router = APIRouter(prefix="/api/v1")


class IngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: Annotated[str, Field(pattern=REPOSITORY_PATTERN, max_length=140)]
    ref: Annotated[str, Field(min_length=1, max_length=200)] | None = None

    @field_validator("repository")
    @classmethod
    def normalize_repository(cls, value: str) -> str:
        return canonical_repository(value)

    @field_validator("ref")
    @classmethod
    def check_ref(cls, value: str | None) -> str | None:
        return validate_ref(value) if value is not None else None


class RequestFailure(Failure):
    request_id: str


class ErrorEnvelope(BaseModel):
    error: RequestFailure


def ingestion_service(request: Request) -> IngestionService:
    service = getattr(request.app.state, "ingestion", None)
    if not isinstance(service, IngestionService):
        raise IngestionError(
            503, "database_unavailable", "Ingestion database is unavailable"
        )
    return service


@router.post(
    "/repositories/ingestions",
    status_code=202,
    responses={
        200: {"model": SnapshotStatus, "description": "Snapshot already completed"},
        **{
            code: {"model": ErrorEnvelope}
            for code in (404, 413, 422, 429, 500, 502, 503, 504)
        },
    },
)
async def submit_ingestion(
    payload: IngestionRequest, request: Request, response: Response
) -> SnapshotStatus:
    request_id: str = request.state.request_id
    status = await ingestion_service(request).submit(
        payload.repository,
        payload.ref,
        request_id,
        getattr(request.state, "workspace", None),
    )
    response.headers["Location"] = f"/api/v1/ingestions/{status.snapshot_id}"
    if status.state == IngestionState.COMPLETED:
        response.status_code = 200
    return status


@router.get(
    "/ingestions/{snapshot_id}",
    responses={code: {"model": ErrorEnvelope} for code in (404, 422, 500, 503)},
)
async def get_ingestion(snapshot_id: UUID, request: Request) -> SnapshotStatus:
    return await ingestion_service(request).status(snapshot_id)
