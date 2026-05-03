from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from audit_logs import append_log, data_access_entry
from integrations.epic.oauth import (
    build_authorize_redirect,
    clear_epic_data,
    clear_epic_session,
    handle_callback,
)
from session_store import SESSION_DATA

router = APIRouter(tags=["epic"])


@router.get("/connect/epic")
async def connect_epic() -> RedirectResponse:
    append_log(
        system="epic",
        action="account_link",
        status="started",
        summary="Started Epic/MyChart account link.",
        data_accessed=[data_access_entry(source="epic", access_type="account_link")],
    )
    return build_authorize_redirect()


@router.get("/auth/epic/callback")
async def epic_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    append_log(
        system="epic",
        action="oauth_callback",
        status="started",
        summary="Received Epic/MyChart OAuth callback.",
        data_accessed=[data_access_entry(source="epic", access_type="account_link")],
        details={"hasCode": bool(code), "hasState": bool(state), "hasError": bool(error)},
    )
    try:
        response = await handle_callback(code=code, state=state, error=error)
    except Exception as exc:
        append_log(
            system="epic",
            action="oauth_callback",
            status="failed",
            summary="Epic/MyChart OAuth callback failed.",
            data_accessed=[data_access_entry(source="epic", access_type="account_link")],
            details={
                "hasCode": bool(code),
                "hasState": bool(state),
                "hasError": bool(error),
                "errorMessage": str(exc),
            },
        )
        raise
    append_log(
        system="epic",
        action="oauth_callback",
        status="succeeded",
        summary="Epic/MyChart OAuth callback completed.",
        data_accessed=[data_access_entry(source="epic", access_type="account_link")],
        details={"hasCode": bool(code), "hasState": bool(state), "hasError": bool(error)},
    )
    return response


@router.get("/api/epic/summary", include_in_schema=False)
async def epic_summary() -> dict[str, Any]:
    if not SESSION_DATA.get("summary"):
        return {
            "connected": False,
            "message": "No Epic/MyChart sandbox data connected yet.",
        }
    return SESSION_DATA["summary"]


@router.get("/api/epic/raw", include_in_schema=False)
async def epic_raw() -> dict[str, Any]:
    if not SESSION_DATA.get("raw"):
        raise HTTPException(status_code=404, detail="No raw Epic data connected yet.")
    compact = compact_epic_raw_for_browser(SESSION_DATA["raw"])
    append_log(
        system="epic",
        action="api_context_fetch",
        status="succeeded",
        summary="Fetched compact Epic/MyChart raw categories.",
        data_accessed=[
            data_access_entry(
                source="epic",
                category_id=f"epic.{key}",
                category_label=_label_from_key(key),
                record_count=_record_count(value),
                access_type="raw_category",
            )
            for key, value in compact.items()
        ],
        details={"endpoint": "/api/epic/raw", "categoryCount": len(compact)},
    )
    return compact


@router.post("/api/epic/logout", include_in_schema=False)
async def epic_logout() -> dict[str, bool]:
    result = clear_epic_session()
    append_log(
        system="epic",
        action="account_logout",
        status="succeeded",
        summary="Cleared Epic/MyChart session.",
        data_accessed=[data_access_entry(source="epic", access_type="account_link")],
    )
    return result


@router.delete("/api/epic/data", include_in_schema=False)
async def epic_clear_data() -> dict[str, bool]:
    result = clear_epic_data()
    append_log(
        system="epic",
        action="clear_data",
        status="succeeded",
        summary="Cleared Epic/MyChart data.",
        data_accessed=[data_access_entry(source="epic", access_type="account_link")],
    )
    return result


def serialize_fhir_for_browser(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {
            key: serialize_fhir_for_browser(child)
            for key, child in value.items()
            if child is not None
        }
    if isinstance(value, list):
        return [serialize_fhir_for_browser(child) for child in value]
    return value


def compact_epic_raw_for_browser(raw: dict[str, Any]) -> dict[str, Any]:
    serialized = serialize_fhir_for_browser(raw)
    compacted: dict[str, Any] = {}

    for key, value in serialized.items():
        if key == "patient":
            compacted[key] = value
            continue

        if isinstance(value, list):
            if len(value) == 0:
                continue
            resources = _resources_from_single_bundle_array(value)
            if len(resources) == 0:
                continue
            compacted[key] = resources
            continue

        compacted[key] = value

    return compacted


def _label_from_key(key: str) -> str:
    return key.replace("_", " ").title()


def _record_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if value is None:
        return 0
    return 1


def _resources_from_single_bundle_array(value: list[Any]) -> list[Any]:
    if len(value) != 1:
        return value

    bundle = value[0]
    if not isinstance(bundle, dict):
        return value

    entries = bundle.get("entry")
    if not isinstance(entries, list):
        return value

    resources: list[Any] = []
    for entry in entries:
        if isinstance(entry, dict) and "resource" in entry:
            resource = entry["resource"]
            if isinstance(resource, dict) and resource.get("resourceType") == "OperationOutcome":
                continue
            resources.append(resource)
    return resources
