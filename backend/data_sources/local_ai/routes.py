from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_sources.wearables.service import DEMO_USER_ID, WearableDataService
from integrations.epic.routes import compact_epic_raw_for_browser
from session_store import SESSION_DATA

router = APIRouter(prefix="/api/local-ai/context", tags=["local-ai-context"])


class ContextCategory(BaseModel):
    id: str
    source: str
    key: str
    label: str
    available: bool
    recordCount: int | None


class ContextSource(BaseModel):
    id: str
    label: str
    connected: bool
    categories: list[ContextCategory]


class AvailableContextResponse(BaseModel):
    sources: list[ContextSource]


class RawContextRequest(BaseModel):
    categoryIds: list[str]


class RawContextResponse(BaseModel):
    generatedAt: str
    selectedRawContext: dict[str, Any]


class WearableCategory(BaseModel):
    id: str
    label: str
    raw_key: str


WEARABLE_CATEGORIES: tuple[WearableCategory, ...] = (
    WearableCategory(id="wearables.connections", label="Connections", raw_key="connections"),
    WearableCategory(
        id="wearables.summary.activity",
        label="Activity Summary",
        raw_key="activitySummary",
    ),
    WearableCategory(
        id="wearables.summary.sleep",
        label="Sleep Summary",
        raw_key="sleepSummary",
    ),
    WearableCategory(
        id="wearables.summary.body",
        label="Body Summary",
        raw_key="bodySummary",
    ),
    WearableCategory(
        id="wearables.summary.data",
        label="Data Summary",
        raw_key="dataSummary",
    ),
    WearableCategory(id="wearables.data_sources", label="Data Sources", raw_key="dataSources"),
    WearableCategory(
        id="wearables.timeseries.heart_rate",
        label="Heart Rate",
        raw_key="heartRate",
    ),
    WearableCategory(id="wearables.timeseries.steps", label="Steps", raw_key="steps"),
    WearableCategory(id="wearables.events.workouts", label="Workouts", raw_key="workouts"),
    WearableCategory(id="wearables.events.sleep", label="Sleep Events", raw_key="sleep"),
    WearableCategory(id="wearables.health_scores", label="Health Scores", raw_key="healthScores"),
)

WEARABLE_CATEGORY_BY_ID = {category.id: category for category in WEARABLE_CATEGORIES}


def _service() -> WearableDataService:
    return WearableDataService(SESSION_DATA)


@router.get("/available", response_model=AvailableContextResponse)
async def available_context() -> AvailableContextResponse:
    compact_epic = _compact_epic_raw()
    epic_categories = [
        ContextCategory(
            id=f"epic.{key}",
            source="epic",
            key=key,
            label=_label_from_key(key),
            available=True,
            recordCount=_record_count(value),
        )
        for key, value in compact_epic.items()
    ]

    return AvailableContextResponse(
        sources=[
            ContextSource(
                id="epic",
                label="Epic",
                connected=bool(compact_epic),
                categories=epic_categories,
            ),
            ContextSource(
                id="openWearables",
                label="Open Wearables",
                connected=True,
                categories=[
                    ContextCategory(
                        id=category.id,
                        source="openWearables",
                        key=category.raw_key,
                        label=category.label,
                        available=True,
                        recordCount=None,
                    )
                    for category in WEARABLE_CATEGORIES
                ],
            ),
        ]
    )


@router.post("/raw", response_model=RawContextResponse)
async def selected_raw_context(request: RawContextRequest) -> RawContextResponse:
    compact_epic = _compact_epic_raw()
    selected: dict[str, Any] = {}
    service: WearableDataService | None = None

    for category_id in request.categoryIds:
        if category_id.startswith("epic."):
            if not compact_epic:
                raise HTTPException(status_code=404, detail="No Epic data connected.")
            epic_key = category_id.removeprefix("epic.")
            if epic_key not in compact_epic:
                _raise_unknown_category(category_id)
            selected.setdefault("epic", {})[epic_key] = compact_epic[epic_key]
            continue

        wearable_category = WEARABLE_CATEGORY_BY_ID.get(category_id)
        if wearable_category is None:
            _raise_unknown_category(category_id)
        if service is None:
            service = _service()
        selected.setdefault("openWearables", {})[
            wearable_category.raw_key
        ] = await _fetch_wearable_category(service, category_id)

    return RawContextResponse(
        generatedAt=datetime.now(timezone.utc).isoformat(),
        selectedRawContext=selected,
    )


def _compact_epic_raw() -> dict[str, Any]:
    raw = SESSION_DATA.get("raw")
    if not raw:
        return {}
    return compact_epic_raw_for_browser(raw)


async def _fetch_wearable_category(
    service: WearableDataService,
    category_id: str,
) -> Any:
    if category_id == "wearables.connections":
        return await service.get_connections(DEMO_USER_ID)
    if category_id == "wearables.summary.activity":
        return await service.get_summary(DEMO_USER_ID, "activity")
    if category_id == "wearables.summary.sleep":
        return await service.get_summary(DEMO_USER_ID, "sleep")
    if category_id == "wearables.summary.body":
        return await service.get_summary(DEMO_USER_ID, "body")
    if category_id == "wearables.summary.data":
        return await service.get_summary(DEMO_USER_ID, "data")
    if category_id == "wearables.data_sources":
        return await service.get_data_sources(DEMO_USER_ID)
    if category_id == "wearables.timeseries.heart_rate":
        return await service.get_timeseries(
            DEMO_USER_ID,
            {"type": "heart_rate", "limit": 12},
        )
    if category_id == "wearables.timeseries.steps":
        return await service.get_timeseries(DEMO_USER_ID, {"type": "steps", "limit": 12})
    if category_id == "wearables.events.workouts":
        return await service.get_workouts(DEMO_USER_ID, {"limit": 5})
    if category_id == "wearables.events.sleep":
        return await service.get_sleep(DEMO_USER_ID, {"limit": 5})
    if category_id == "wearables.health_scores":
        return await service.get_health_scores(DEMO_USER_ID, {"limit": 12})
    _raise_unknown_category(category_id)


def _raise_unknown_category(category_id: str) -> None:
    raise HTTPException(
        status_code=400,
        detail=f"Unknown context category: {category_id}",
    )


def _label_from_key(key: str) -> str:
    return key.replace("_", " ").title()


def _record_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    return 1
