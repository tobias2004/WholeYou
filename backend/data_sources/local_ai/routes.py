from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from audit_logs import append_log, data_access_entry
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


class LocalAiDocument(BaseModel):
    id: str
    categoryId: str
    documentType: str | None
    details: str | None
    date: str | None
    contentType: str | None


class DocumentsResponse(BaseModel):
    documents: list[LocalAiDocument]


class RawDocumentRequest(BaseModel):
    categoryId: str
    documentId: str


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
DOCUMENT_KEYS = (
    "documents_clinical_notes",
    "documents_labs",
    "documents_outside_record_clinical_notes",
)


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

    response = AvailableContextResponse(
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
    append_log(
        system="localAi",
        action="api_context_availability",
        status="succeeded",
        summary="Listed available Local AI context metadata.",
        data_accessed=[
            data_access_entry(source="epic", access_type="metadata_list"),
            data_access_entry(source="openWearables", access_type="metadata_list"),
        ],
        details={
            "endpoint": "/api/local-ai/context/available",
            "epicCategoryCount": len(epic_categories),
            "wearableCategoryCount": len(WEARABLE_CATEGORIES),
        },
    )
    return response


@router.get("/documents", response_model=DocumentsResponse)
async def available_documents() -> DocumentsResponse:
    compact_epic = _compact_epic_raw()
    documents: list[LocalAiDocument] = []

    for key in DOCUMENT_KEYS:
        for document in _documents_for_key(compact_epic, key):
            document_id = document.get("id")
            if not isinstance(document_id, str) or not document_id:
                continue
            documents.append(
                LocalAiDocument(
                    id=document_id,
                    categoryId=f"epic.{key}",
                    documentType=_document_type(document),
                    details=_document_details(document),
                    date=_document_date(document),
                    contentType=_document_content_type(document),
                )
            )

    append_log(
        system="localAi",
        action="api_context_documents",
        status="succeeded",
        summary="Listed available document metadata.",
        data_accessed=[
            data_access_entry(
                source="epic",
                category_id=document.categoryId,
                category_label=_label_from_key(document.categoryId.removeprefix("epic.")),
                document_id=document.id,
                content_type=document.contentType,
                access_type="metadata_list",
            )
            for document in documents
        ],
        details={"endpoint": "/api/local-ai/context/documents", "documentCount": len(documents)},
    )
    return DocumentsResponse(documents=documents)


@router.post("/raw", response_model=RawContextResponse)
async def selected_raw_context(request: RawContextRequest) -> RawContextResponse:
    compact_epic = _compact_epic_raw()
    selected: dict[str, Any] = {}
    service: WearableDataService | None = None
    data_accessed: list[dict[str, Any]] = []

    for category_id in request.categoryIds:
        if category_id.startswith("epic."):
            if not compact_epic:
                raise HTTPException(status_code=404, detail="No Epic data connected.")
            epic_key = category_id.removeprefix("epic.")
            if epic_key not in compact_epic:
                _raise_unknown_category(category_id)
            selected.setdefault("epic", {})[epic_key] = compact_epic[epic_key]
            data_accessed.append(_epic_data_access_entry(category_id, epic_key, compact_epic[epic_key]))
            continue

        wearable_category = WEARABLE_CATEGORY_BY_ID.get(category_id)
        if wearable_category is None:
            _raise_unknown_category(category_id)
        if service is None:
            service = _service()
        value = await _fetch_wearable_category(service, category_id)
        selected.setdefault("openWearables", {})[wearable_category.raw_key] = value
        data_accessed.append(_wearable_data_access_entry(category_id, value))

    append_log(
        system="localAi",
        action="api_context_fetch",
        status="succeeded",
        summary="Fetched selected raw context categories for Local AI.",
        data_accessed=data_accessed,
        details={
            "endpoint": "/api/local-ai/context/raw",
            "selectedCategoryIds": request.categoryIds,
        },
    )
    return RawContextResponse(
        generatedAt=datetime.now(timezone.utc).isoformat(),
        selectedRawContext=selected,
    )


@router.post("/document/raw", response_model=RawContextResponse)
async def selected_raw_document(request: RawDocumentRequest) -> RawContextResponse:
    compact_epic = _compact_epic_raw()
    if not compact_epic:
        raise HTTPException(status_code=404, detail="No Epic data connected.")

    if not request.categoryId.startswith("epic."):
        _raise_unknown_category(request.categoryId)
    epic_key = request.categoryId.removeprefix("epic.")
    if epic_key not in DOCUMENT_KEYS:
        _raise_unknown_category(request.categoryId)

    for document in _documents_for_key(compact_epic, epic_key):
        if document.get("id") == request.documentId:
            append_log(
                system="localAi",
                action="api_context_document_fetch",
                status="succeeded",
                summary="Fetched one selected raw document for Local AI.",
                data_accessed=[
                    data_access_entry(
                        source="epic",
                        category_id=request.categoryId,
                        category_label=_label_from_key(epic_key),
                        document_id=request.documentId,
                        content_type=_document_content_type(document),
                        record_count=1,
                        access_type="raw_document",
                    )
                ],
                details={
                    "endpoint": "/api/local-ai/context/document/raw",
                    "categoryId": request.categoryId,
                    "documentId": request.documentId,
                },
            )
            return RawContextResponse(
                generatedAt=datetime.now(timezone.utc).isoformat(),
                selectedRawContext={"epic": {epic_key: [document]}},
            )

    raise HTTPException(status_code=404, detail="Selected document was not found.")


def _compact_epic_raw() -> dict[str, Any]:
    raw = SESSION_DATA.get("raw")
    if not raw:
        return {}
    return compact_epic_raw_for_browser(raw)


def _documents_for_key(compact_epic: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = compact_epic.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _epic_data_access_entry(category_id: str, key: str, value: Any) -> dict[str, Any]:
    return data_access_entry(
        source="epic",
        category_id=category_id,
        category_label=_label_from_key(key),
        record_count=_record_count(value),
        access_type="raw_category",
    )


def _wearable_data_access_entry(category_id: str, value: Any) -> dict[str, Any]:
    category = WEARABLE_CATEGORY_BY_ID[category_id]
    return data_access_entry(
        source="openWearables",
        category_id=category_id,
        category_label=category.label,
        record_count=_record_count(value),
        access_type="raw_category",
    )


def _document_type(document: dict[str, Any]) -> str | None:
    type_value = document.get("type")
    if isinstance(type_value, dict):
        text = type_value.get("text")
        if isinstance(text, str) and text:
            return text
        coding = type_value.get("coding")
        if isinstance(coding, list):
            for item in coding:
                if isinstance(item, dict):
                    display = item.get("display")
                    if isinstance(display, str) and display:
                        return display
    return None


def _document_details(document: dict[str, Any]) -> str | None:
    description = document.get("description")
    if isinstance(description, str) and description:
        return description
    for content in document.get("content") or []:
        if not isinstance(content, dict):
            continue
        attachment = content.get("attachment")
        if not isinstance(attachment, dict):
            continue
        title = attachment.get("title")
        if isinstance(title, str) and title:
            return title
    return None


def _document_date(document: dict[str, Any]) -> str | None:
    for key in ("date", "created", "indexed"):
        value = document.get(key)
        if isinstance(value, str) and value:
            return value
    for content in document.get("content") or []:
        if not isinstance(content, dict):
            continue
        attachment = content.get("attachment")
        if isinstance(attachment, dict):
            creation = attachment.get("creation")
            if isinstance(creation, str) and creation:
                return creation
    return None


def _document_content_type(document: dict[str, Any]) -> str | None:
    for content in document.get("content") or []:
        if not isinstance(content, dict):
            continue
        attachment = content.get("attachment")
        if isinstance(attachment, dict):
            content_type = attachment.get("contentType")
            if isinstance(content_type, str) and content_type:
                return content_type
    for contained in document.get("contained") or []:
        if isinstance(contained, dict):
            content_type = contained.get("contentType")
            if isinstance(content_type, str) and content_type:
                return content_type
    return None


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
