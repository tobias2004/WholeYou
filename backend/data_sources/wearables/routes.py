import logging
from typing import Any

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from audit_logs import append_log, data_access_entry
from config import FRONTEND_BASE_URL, OPEN_WEARABLES_WEBHOOK_SECRET
from data_sources.wearables.service import DEMO_USER_ID, WearableDataService
from integrations.open_wearables.client import OpenWearablesClientError
from integrations.open_wearables.schemas import (
    HealthScore,
    HistoricalSyncRequest,
    ProviderConnectRequest,
    ProviderConnectResponse,
    SleepEvent,
    SyncRequest,
    SyntheticDataRequest,
    SyntheticDataResponse,
    WearableConnection,
    WearableProvider,
    WearableSummary,
    WearableTimeseriesPoint,
    WorkoutEvent,
)
from session_store import SESSION_DATA

logger = logging.getLogger("wholeyou.wearables")

router = APIRouter(prefix="/api/wearables", tags=["wearables"])


def _service() -> WearableDataService:
    # Local MVP uses a single demo user and in-memory Open Wearables user ID
    # mapping. TODO: replace with authenticated user-scoped session metadata,
    # encrypted token storage, audit logging, retention policy, and full
    # disconnect/delete flow before production use.
    return WearableDataService(SESSION_DATA)


def _filters(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


async def _compute_health_scores_after_update(service: WearableDataService) -> None:
    try:
        await service.compute_health_scores(DEMO_USER_ID)
    except OpenWearablesClientError:
        logger.exception("Open Wearables health score computation failed after data update")


@router.get("/summary", response_model=WearableSummary)
async def wearable_summary() -> dict[str, Any]:
    return await _service().get_wearable_summary(DEMO_USER_ID)


@router.get("/providers", response_model=list[WearableProvider])
async def wearable_providers() -> list[dict[str, Any]]:
    return await _service().get_providers()


@router.post("/connect/{provider}", response_model=ProviderConnectResponse)
async def connect_provider(
    provider: str,
    request: ProviderConnectRequest | None = None,
) -> dict[str, Any]:
    service = _service()
    mode = request.mode if request else "synthetic"
    append_log(
        system="openWearables",
        action="account_link",
        status="started",
        summary="Started wearable provider connection.",
        data_accessed=[data_access_entry(source="openWearables", access_type="account_link")],
        details={"provider": provider, "mode": mode},
    )
    try:
        result = await service.start_provider_connection(
            DEMO_USER_ID,
            provider,
            mode=mode,
        )
    except OpenWearablesClientError as exc:
        append_log(
            system="openWearables",
            action="account_link",
            status="failed",
            summary="Wearable provider connection failed.",
            data_accessed=[data_access_entry(source="openWearables", access_type="account_link")],
            details={"provider": provider, "mode": mode, "errorMessage": str(exc)},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if request and request.mode == "real" and not result.get("authorizationUrl"):
        append_log(
            system="openWearables",
            action="account_link",
            status="failed",
            summary="Wearable provider authorization URL was missing.",
            data_accessed=[data_access_entry(source="openWearables", access_type="account_link")],
            details={"provider": provider, "mode": mode},
        )
        raise HTTPException(
            status_code=502,
            detail="Open Wearables did not return a provider authorization URL.",
        )
    if not result.get("authorizationUrl"):
        await _compute_health_scores_after_update(service)
    append_log(
        system="openWearables",
        action="account_link",
        status="succeeded",
        summary="Wearable provider connection completed.",
        data_accessed=[data_access_entry(source="openWearables", access_type="account_link")],
        details={
            "provider": provider,
            "mode": mode,
            "authorizationRequired": bool(result.get("authorizationUrl")),
        },
    )
    return result


@router.get("/oauth/{provider}/callback")
async def wearable_oauth_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    service = _service()
    append_log(
        system="openWearables",
        action="oauth_callback",
        status="started",
        summary="Received wearable OAuth callback.",
        data_accessed=[data_access_entry(source="openWearables", access_type="account_link")],
        details={"provider": provider, "hasCode": bool(code), "hasState": bool(state), "hasError": bool(error)},
    )
    try:
        await service.handle_oauth_callback(provider, code=code, state=state, error=error)
        await _compute_health_scores_after_update(service)
    except OpenWearablesClientError as exc:
        append_log(
            system="openWearables",
            action="oauth_callback",
            status="failed",
            summary="Wearable OAuth callback failed.",
            data_accessed=[data_access_entry(source="openWearables", access_type="account_link")],
            details={"provider": provider, "hasCode": bool(code), "hasState": bool(state), "hasError": bool(error), "errorMessage": str(exc)},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    append_log(
        system="openWearables",
        action="oauth_callback",
        status="succeeded",
        summary="Wearable OAuth callback completed.",
        data_accessed=[data_access_entry(source="openWearables", access_type="account_link")],
        details={"provider": provider, "hasCode": bool(code), "hasState": bool(state), "hasError": bool(error)},
    )
    return RedirectResponse(url=f"{FRONTEND_BASE_URL}/")


@router.get("/connections", response_model=list[WearableConnection])
async def wearable_connections() -> list[dict[str, Any]]:
    return await _service().get_connections(DEMO_USER_ID)


@router.delete("/connections/{provider}")
async def delete_wearable_connection(provider: str) -> dict[str, Any]:
    try:
        return await _service().disconnect(DEMO_USER_ID, provider)
    except OpenWearablesClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/connections")
async def clear_wearable_connections() -> dict[str, Any]:
    try:
        result = await _service().clear_connections(DEMO_USER_ID)
        append_log(
            system="openWearables",
            action="clear_connections",
            status="succeeded",
            summary="Cleared wearable connections.",
            data_accessed=[data_access_entry(source="openWearables", access_type="account_link")],
        )
        return result
    except OpenWearablesClientError as exc:
        append_log(
            system="openWearables",
            action="clear_connections",
            status="failed",
            summary="Clearing wearable connections failed.",
            data_accessed=[data_access_entry(source="openWearables", access_type="account_link")],
            details={"errorMessage": str(exc)},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/sync")
async def sync_wearables(request: SyncRequest) -> dict[str, Any]:
    service = _service()
    try:
        result = await service.sync(
            DEMO_USER_ID,
            provider=request.provider,
            async_=request.async_,
        )
        await _compute_health_scores_after_update(service)
        return result
    except OpenWearablesClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/sync-history")
async def sync_wearable_history(request: HistoricalSyncRequest) -> dict[str, Any]:
    service = _service()
    try:
        result = await service.sync_history(
            DEMO_USER_ID,
            start_date=request.startDate,
            end_date=request.endDate,
            provider=request.provider,
        )
        await _compute_health_scores_after_update(service)
        return result
    except OpenWearablesClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/synthetic-data", response_model=SyntheticDataResponse)
async def generate_synthetic_wearable_data(
    request: SyntheticDataRequest,
) -> dict[str, Any]:
    service = _service()
    try:
        result = await service.generate_synthetic_data(
            seed=request.seed,
            preset=request.preset,
            num_users=request.numUsers,
        )
        await _compute_health_scores_after_update(service)
        return result
    except OpenWearablesClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/summary/activity")
async def activity_summary() -> dict[str, Any]:
    return await _service().get_summary(DEMO_USER_ID, "activity")


@router.get("/summary/sleep")
async def sleep_summary() -> dict[str, Any]:
    return await _service().get_summary(DEMO_USER_ID, "sleep")


@router.get("/summary/body")
async def body_summary() -> dict[str, Any]:
    return await _service().get_summary(DEMO_USER_ID, "body")


@router.get("/summary/data")
async def data_summary() -> dict[str, Any]:
    return await _service().get_summary(DEMO_USER_ID, "data")


@router.get("/timeseries", response_model=list[WearableTimeseriesPoint])
async def wearable_timeseries(
    type: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    resolution: str | None = None,
    page: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return await _service().get_timeseries(
        DEMO_USER_ID,
        _filters(
            {
                "type": type,
                "start_time": start_time,
                "end_time": end_time,
                "resolution": resolution,
                "page": page,
                "limit": limit,
            }
        ),
    )


@router.get("/events/workouts", response_model=list[WorkoutEvent])
async def wearable_workouts(
    start_time: str | None = None,
    end_time: str | None = None,
    page: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return await _service().get_workouts(
        DEMO_USER_ID,
        _filters(
            {
                "start_time": start_time,
                "end_time": end_time,
                "page": page,
                "limit": limit,
            }
        ),
    )


@router.get("/events/sleep", response_model=list[SleepEvent])
async def wearable_sleep_events(
    start_time: str | None = None,
    end_time: str | None = None,
    page: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return await _service().get_sleep(
        DEMO_USER_ID,
        _filters(
            {
                "start_time": start_time,
                "end_time": end_time,
                "page": page,
                "limit": limit,
            }
        ),
    )


@router.post("/health-scores/compute")
async def compute_wearable_health_scores() -> dict[str, Any]:
    try:
        result = await _service().compute_health_scores(DEMO_USER_ID)
        append_log(
            system="openWearables",
            action="health_score_compute",
            status="succeeded",
            summary="Computed wearable health scores.",
            data_accessed=[
                data_access_entry(
                    source="openWearables",
                    category_id="wearables.health_scores",
                    category_label="Health Scores",
                    access_type="derived_compute",
                )
            ],
        )
        return result
    except OpenWearablesClientError as exc:
        append_log(
            system="openWearables",
            action="health_score_compute",
            status="failed",
            summary="Computing wearable health scores failed.",
            data_accessed=[
                data_access_entry(
                    source="openWearables",
                    category_id="wearables.health_scores",
                    category_label="Health Scores",
                    access_type="derived_compute",
                )
            ],
            details={"errorMessage": str(exc)},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/health-scores", response_model=list[HealthScore])
async def wearable_health_scores(
    category: str | None = None,
    provider: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return await _service().get_health_scores(
        DEMO_USER_ID,
        _filters(
            {
                "category": category,
                "provider": provider,
                "limit": limit,
            }
        ),
    )


@router.get("/data-sources")
async def wearable_data_sources() -> dict[str, Any]:
    return await _service().get_data_sources(DEMO_USER_ID)


@router.post("/import/apple-health/xml/upload-url")
async def apple_health_xml_upload_url(payload: dict[str, Any]) -> dict[str, Any]:
    # TODO: confirm current Open Wearables import response shape before building
    # a production upload UX.
    return await _service().create_apple_health_upload_url(DEMO_USER_ID, payload)


@router.post("/import/apple-health/xml/direct")
async def apple_health_xml_direct(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = file.filename or ""
    if not filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="Apple Health import requires an .xml file")
    content = await file.read()
    service = _service()
    append_log(
        system="openWearables",
        action="wearable_import",
        status="started",
        summary="Started Apple Health XML import.",
        data_accessed=[data_access_entry(source="openWearables", access_type="file_import")],
        details={"filename": filename, "contentType": file.content_type},
    )
    try:
        result = await service.import_apple_health_xml_direct(
            DEMO_USER_ID,
            filename=filename,
            content=content,
        )
        await _compute_health_scores_after_update(service)
        append_log(
            system="openWearables",
            action="wearable_import",
            status="succeeded",
            summary="Completed Apple Health XML import.",
            data_accessed=[data_access_entry(source="openWearables", access_type="file_import")],
            details={
                "filename": filename,
                "contentType": file.content_type,
                "timeseriesImported": result.get("timeseriesImported"),
                "workoutsImported": result.get("workoutsImported"),
                "sleepImported": result.get("sleepImported"),
            },
        )
        return result
    except OpenWearablesClientError as exc:
        append_log(
            system="openWearables",
            action="wearable_import",
            status="failed",
            summary="Apple Health XML import failed.",
            data_accessed=[data_access_entry(source="openWearables", access_type="file_import")],
            details={"filename": filename, "contentType": file.content_type, "errorMessage": str(exc)},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/webhook/open-wearables")
async def open_wearables_webhook(
    request: Request,
    x_open_wearables_webhook_secret: str | None = Header(default=None),
) -> dict[str, str]:
    if (
        OPEN_WEARABLES_WEBHOOK_SECRET
        and x_open_wearables_webhook_secret != OPEN_WEARABLES_WEBHOOK_SECRET
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    payload = await request.json()
    event_type = payload.get("type") or payload.get("event") if isinstance(payload, dict) else None
    provider = payload.get("provider") if isinstance(payload, dict) else None
    logger.info("Open Wearables webhook event=%s provider=%s", event_type, provider)
    # TODO: production webhooks need signature verification, replay protection,
    # audit logging, and a retention-aware sync queue. Do not log raw payloads.
    return {"status": "accepted"}
