from typing import Any

from fastapi import APIRouter

from data_sources.clinical.service import ClinicalDataService
from integrations.epic.schemas import ClinicalSummary
from session_store import SESSION_DATA

router = APIRouter(prefix="/api/clinical", tags=["clinical"])


def _service() -> ClinicalDataService:
    # Local MVP uses one in-memory session. Production should resolve the user
    # from an authenticated session and load that user's clinical source data.
    return ClinicalDataService(SESSION_DATA)


@router.get("/summary", response_model=ClinicalSummary)
async def clinical_summary() -> dict[str, Any]:
    return _service().get_clinical_summary("local")


@router.get("/conditions")
async def clinical_conditions() -> list[dict[str, Any]]:
    return _service().get_conditions("local")


@router.get("/medications")
async def clinical_medications() -> list[dict[str, Any]]:
    return _service().get_medications("local")


@router.get("/labs")
async def clinical_labs() -> list[dict[str, Any]]:
    return _service().get_labs("local")


@router.get("/vitals")
async def clinical_vitals() -> list[dict[str, Any]]:
    return _service().get_vitals("local")


@router.get("/encounters")
async def clinical_encounters() -> list[dict[str, Any]]:
    return _service().get_encounters("local")
