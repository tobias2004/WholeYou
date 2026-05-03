from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from audit_logs import clear_logs, list_logs

router = APIRouter(prefix="/api/logs", tags=["logs"])


class LogsResponse(BaseModel):
    logs: list[dict[str, Any]]


class ClearLogsResponse(BaseModel):
    cleared: int


@router.get("", response_model=LogsResponse)
async def get_logs() -> LogsResponse:
    return LogsResponse(logs=list_logs())


@router.delete("", response_model=ClearLogsResponse)
async def delete_logs() -> ClearLogsResponse:
    return ClearLogsResponse(cleared=clear_logs())
