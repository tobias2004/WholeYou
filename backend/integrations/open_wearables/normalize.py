from datetime import datetime, timezone
from typing import Any


OPEN_WEARABLES_SOURCE = "open_wearables"

_SENSITIVE_KEYS = {
    "access_token",
    "refresh_token",
    "token",
    "authorization_code",
    "client_secret",
    "api_key",
}


def _value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _source(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    return {
        "provider": _value(payload, "provider") or source.get("provider"),
        "device": _value(payload, "device", "device_name") or source.get("device"),
        "deviceType": _value(payload, "device_type", "deviceType") or source.get("deviceType"),
    }


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data", "results", "providers", "connections"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def normalize_provider(payload: dict[str, Any], source: str = OPEN_WEARABLES_SOURCE) -> dict[str, Any]:
    del source
    provider_id = str(_value(payload, "id", "provider", "name") or "")
    return {
        "id": provider_id,
        "name": str(_value(payload, "name", "display_name", "displayName") or provider_id),
        "type": _value(payload, "type", "category"),
        "supportsOAuth": bool(_value(payload, "supports_oauth", "supportsOAuth", "oauth") or False),
        "supportsImport": bool(_value(payload, "supports_import", "supportsImport", "import") or False),
        "requiresMobile": bool(_value(payload, "requires_mobile", "requiresMobile") or False),
        "logoUrl": _value(payload, "logo_url", "logoUrl", "logo"),
        "enabled": bool(_value(payload, "enabled") if _value(payload, "enabled") is not None else True),
    }


def normalize_providers(payload: Any, source: str = OPEN_WEARABLES_SOURCE) -> list[dict[str, Any]]:
    return [normalize_provider(item, source=source) for item in _items(payload)]


def normalize_connection(payload: dict[str, Any], source: str = OPEN_WEARABLES_SOURCE) -> dict[str, Any]:
    clean = {key: value for key, value in payload.items() if key not in _SENSITIVE_KEYS}
    return {
        "provider": str(_value(clean, "provider") or ""),
        "status": _value(clean, "status"),
        "providerUserId": _value(clean, "provider_user_id", "providerUserId"),
        "scopes": _value(clean, "scopes") or [],
        "connectedAt": _value(clean, "connected_at", "connectedAt", "created_at", "createdAt"),
        "lastSyncedAt": _value(clean, "last_synced_at", "lastSyncedAt"),
        "source": source,
    }


def normalize_connections(payload: Any, source: str = OPEN_WEARABLES_SOURCE) -> list[dict[str, Any]]:
    return [normalize_connection(item, source=source) for item in _items(payload)]


def normalize_timeseries_point(
    payload: dict[str, Any], source: str = OPEN_WEARABLES_SOURCE
) -> dict[str, Any]:
    del source
    return {
        "timestamp": _value(payload, "timestamp", "time", "start_time", "startTime"),
        "type": _value(payload, "type", "metric_type", "metricType"),
        "value": _value(payload, "value", "quantity"),
        "unit": _value(payload, "unit"),
        "zoneOffset": _value(payload, "zone_offset", "zoneOffset", "timezone_offset"),
        "source": _source(payload),
    }


def normalize_timeseries(payload: Any, source: str = OPEN_WEARABLES_SOURCE) -> list[dict[str, Any]]:
    return [normalize_timeseries_point(item, source=source) for item in _items(payload)]


def normalize_workout_event(
    payload: dict[str, Any], source: str = OPEN_WEARABLES_SOURCE
) -> dict[str, Any]:
    del source
    return {
        "id": _value(payload, "id"),
        "type": _value(payload, "type", "activity_type", "activityType"),
        "startTime": _value(payload, "start_time", "startTime", "start"),
        "endTime": _value(payload, "end_time", "endTime", "end"),
        "durationMinutes": _value(payload, "duration_minutes", "durationMinutes"),
        "calories": _value(payload, "calories", "calories_burned", "caloriesBurned"),
        "distance": _value(payload, "distance", "distance_meters", "distanceMeters"),
        "averageHeartRate": _value(
            payload, "average_heart_rate", "averageHeartRate", "avg_hr", "avgHr"
        ),
        "source": _source(payload),
    }


def normalize_workouts(payload: Any, source: str = OPEN_WEARABLES_SOURCE) -> list[dict[str, Any]]:
    return [normalize_workout_event(item, source=source) for item in _items(payload)]


def normalize_sleep_event(
    payload: dict[str, Any], source: str = OPEN_WEARABLES_SOURCE
) -> dict[str, Any]:
    del source
    return {
        "id": _value(payload, "id"),
        "startTime": _value(payload, "start_time", "startTime", "start"),
        "endTime": _value(payload, "end_time", "endTime", "end"),
        "durationMinutes": _value(payload, "duration_minutes", "durationMinutes"),
        "efficiencyPercent": _value(payload, "efficiency_percent", "efficiencyPercent"),
        "stages": _value(payload, "stages") or [],
        "interruptions": _value(payload, "interruptions", "awake_count", "awakeCount"),
        "source": _source(payload),
    }


def normalize_sleep_events(payload: Any, source: str = OPEN_WEARABLES_SOURCE) -> list[dict[str, Any]]:
    return [normalize_sleep_event(item, source=source) for item in _items(payload)]


def normalize_health_score(
    payload: dict[str, Any], source: str = OPEN_WEARABLES_SOURCE
) -> dict[str, Any]:
    del source
    return {
        "id": _value(payload, "id"),
        "dataSourceId": _value(payload, "data_source_id", "dataSourceId"),
        "provider": _value(payload, "provider"),
        "category": _value(payload, "category"),
        "value": _value(payload, "value"),
        "qualifier": _value(payload, "qualifier"),
        "recordedAt": _value(payload, "recorded_at", "recordedAt"),
        "zoneOffset": _value(payload, "zone_offset", "zoneOffset"),
        "components": _value(payload, "components") or {},
    }


def normalize_health_scores(payload: Any, source: str = OPEN_WEARABLES_SOURCE) -> list[dict[str, Any]]:
    return [normalize_health_score(item, source=source) for item in _items(payload)]


def normalize_summary_payload(payload: Any, source: str = OPEN_WEARABLES_SOURCE) -> dict[str, Any]:
    if isinstance(payload, dict):
        summary = {key: value for key, value in payload.items() if key not in _SENSITIVE_KEYS}
    else:
        summary = {"items": _items(payload)}
    summary["source"] = source
    return summary


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
