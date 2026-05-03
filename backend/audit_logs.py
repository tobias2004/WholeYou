from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from session_store import SESSION_DATA

MAX_AUDIT_LOGS = 500

_SENSITIVE_DETAIL_KEYS = {
    "answer",
    "apiKey",
    "authorization",
    "authorizationCode",
    "authorizationUrl",
    "code",
    "content",
    "data",
    "documentText",
    "fullCallbackUrl",
    "image",
    "imageDataUrl",
    "payload",
    "prompt",
    "raw",
    "rawPayload",
    "refreshToken",
    "response",
    "result",
    "token",
    "toolResult",
}

_ALLOWED_DATA_ACCESS_KEYS = {
    "source",
    "categoryId",
    "categoryLabel",
    "documentId",
    "contentType",
    "recordCount",
    "accessType",
}


def append_log(
    *,
    system: str,
    action: str,
    status: str,
    summary: str,
    data_accessed: list[dict[str, Any]] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = {
        "id": f"log_{uuid4().hex}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": _safe_string(system),
        "action": _safe_string(action),
        "status": _safe_string(status),
        "summary": _safe_string(summary),
        "dataAccessed": _sanitize_data_accessed(data_accessed or []),
        "details": _sanitize_details(details or {}),
    }
    logs = _store()
    logs.append(entry)
    if len(logs) > MAX_AUDIT_LOGS:
        del logs[: len(logs) - MAX_AUDIT_LOGS]
    return entry


def list_logs() -> list[dict[str, Any]]:
    return [dict(entry) for entry in _store()]


def clear_logs() -> int:
    logs = _store()
    cleared = len(logs)
    logs.clear()
    return cleared


def data_access_entry(
    *,
    source: str,
    category_id: str | None = None,
    category_label: str | None = None,
    document_id: str | None = None,
    content_type: str | None = None,
    record_count: int | None = None,
    access_type: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"source": source}
    if category_id:
        entry["categoryId"] = category_id
    if category_label:
        entry["categoryLabel"] = category_label
    if document_id:
        entry["documentId"] = document_id
    if content_type:
        entry["contentType"] = content_type
    if record_count is not None:
        entry["recordCount"] = record_count
    if access_type:
        entry["accessType"] = access_type
    return entry


def _store() -> list[dict[str, Any]]:
    logs = SESSION_DATA.setdefault("auditLogs", [])
    if not isinstance(logs, list):
        logs = []
        SESSION_DATA["auditLogs"] = logs
    return logs


def _sanitize_data_accessed(data_accessed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for item in data_accessed:
        if not isinstance(item, dict):
            continue
        safe_item = {
            key: _sanitize_detail_value(value)
            for key, value in item.items()
            if key in _ALLOWED_DATA_ACCESS_KEYS
        }
        if safe_item:
            sanitized.append(safe_item)
    return sanitized


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _sanitize_detail_value(value)
        for key, value in details.items()
        if isinstance(key, str) and not _is_sensitive_key(key)
    }


def _sanitize_detail_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _safe_string(value)
    if isinstance(value, list):
        return [_sanitize_detail_value(item) for item in value[:50]]
    if isinstance(value, tuple):
        return [_sanitize_detail_value(item) for item in list(value)[:50]]
    if isinstance(value, dict):
        return _sanitize_details(value)
    return _safe_string(value)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.replace("_", "").replace("-", "").lower()
    return any(
        normalized == sensitive.lower()
        or normalized.endswith(sensitive.lower())
        for sensitive in _SENSITIVE_DETAIL_KEYS
    )


def _safe_string(value: Any) -> str:
    text = str(value)
    if len(text) > 240:
        return f"{text[:237]}..."
    return text
