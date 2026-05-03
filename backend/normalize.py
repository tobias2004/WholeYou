from datetime import UTC, datetime
from typing import Any


def get_first_coding(codable_concept: dict[str, Any] | None) -> dict[str, Any] | None:
    if not codable_concept:
        return None
    codings = codable_concept.get("coding") or []
    return codings[0] if codings else None


def get_code_display(codable_concept: dict[str, Any] | None) -> str | None:
    if not codable_concept:
        return None
    if codable_concept.get("text"):
        return codable_concept["text"]
    coding = get_first_coding(codable_concept)
    if not coding:
        return None
    return coding.get("display") or coding.get("code")


def get_reference_id(reference: str | None) -> str | None:
    if not reference:
        return None
    return reference.rstrip("/").split("/")[-1]


def get_patient_name(patient: dict[str, Any]) -> str:
    names = patient.get("name") or []
    if not names:
        return "Unknown patient"
    name = names[0]
    if name.get("text"):
        return name["text"]
    parts = [*(name.get("given") or []), name.get("family")]
    return " ".join(part for part in parts if part) or "Unknown patient"


def normalize_patient(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": resource.get("id"),
        "name": get_patient_name(resource),
        "birthDate": resource.get("birthDate"),
        "gender": resource.get("gender"),
    }


def _date(resource: dict[str, Any]) -> str | None:
    return (
        resource.get("effectiveDateTime")
        or resource.get("issued")
        or resource.get("authoredOn")
        or resource.get("recordedDate")
        or resource.get("date")
    )


def _quantity_value(quantity: dict[str, Any] | None) -> tuple[Any, str | None]:
    if not quantity:
        return None, None
    return quantity.get("value"), quantity.get("unit") or quantity.get("code")


def _normalize_flag(resource: dict[str, Any]) -> str | None:
    interpretations = resource.get("interpretation") or []
    if not interpretations:
        return None
    display = get_code_display(interpretations[0])
    if not display:
        return None
    flag_map = {"H": "high", "L": "low", "A": "abnormal", "N": "normal"}
    return flag_map.get(display, display.lower())


def _component_value(resource: dict[str, Any]) -> tuple[Any, str | None]:
    components = resource.get("component") or []
    if not components:
        return None, None

    systolic = None
    diastolic = None
    unit = None
    values = []

    for component in components:
        value, component_unit = _quantity_value(component.get("valueQuantity"))
        unit = unit or component_unit
        code = get_first_coding(component.get("code")) or {}
        code_value = code.get("code")
        display = (code.get("display") or "").lower()

        if code_value == "8480-6" or "systolic" in display:
            systolic = value
        elif code_value == "8462-4" or "diastolic" in display:
            diastolic = value
        elif value is not None:
            values.append(str(value))

    if systolic is not None and diastolic is not None:
        return f"{systolic}/{diastolic}", unit
    if values:
        return ", ".join(values), unit
    return None, unit


def normalize_observation(resource: dict[str, Any]) -> dict[str, Any]:
    coding = get_first_coding(resource.get("code")) or {}
    value: Any = None
    unit = None

    if resource.get("valueQuantity"):
        value, unit = _quantity_value(resource["valueQuantity"])
    elif resource.get("valueCodeableConcept"):
        value = get_code_display(resource["valueCodeableConcept"])
    elif resource.get("valueString"):
        value = resource["valueString"]
    elif resource.get("component"):
        value, unit = _component_value(resource)

    return {
        "id": resource.get("id"),
        "name": get_code_display(resource.get("code")),
        "value": value,
        "unit": unit,
        "date": _date(resource),
        "status": resource.get("status"),
        "code": coding.get("code"),
        "codeSystem": coding.get("system"),
        "flag": _normalize_flag(resource),
    }


def _status_code(value: dict[str, Any] | None) -> str | None:
    coding = get_first_coding(value)
    return coding.get("code") if coding else None


def normalize_condition(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": resource.get("id"),
        "name": get_code_display(resource.get("code")),
        "clinicalStatus": _status_code(resource.get("clinicalStatus")),
        "verificationStatus": _status_code(resource.get("verificationStatus")),
        "onsetDate": resource.get("onsetDateTime") or resource.get("recordedDate"),
    }


def normalize_medication_request(resource: dict[str, Any]) -> dict[str, Any]:
    medication = (
        get_code_display(resource.get("medicationCodeableConcept"))
        or (resource.get("medicationReference") or {}).get("display")
    )
    dosage = resource.get("dosageInstruction") or []
    return {
        "id": resource.get("id"),
        "name": medication,
        "status": resource.get("status"),
        "intent": resource.get("intent"),
        "authoredOn": resource.get("authoredOn"),
        "dosageText": "; ".join(item.get("text", "") for item in dosage if item.get("text"))
        or None,
    }


def normalize_allergy(resource: dict[str, Any]) -> dict[str, Any]:
    reactions = resource.get("reaction") or []
    reaction = None
    if reactions:
        manifestations = reactions[0].get("manifestation") or []
        if manifestations:
            reaction = get_code_display(manifestations[0])
    return {
        "id": resource.get("id"),
        "name": get_code_display(resource.get("code")),
        "criticality": resource.get("criticality"),
        "reaction": reaction,
    }


def normalize_encounter(resource: dict[str, Any]) -> dict[str, Any]:
    types = resource.get("type") or []
    period = resource.get("period") or {}
    return {
        "id": resource.get("id"),
        "type": get_code_display(types[0]) if types else None,
        "status": resource.get("status"),
        "start": period.get("start"),
        "end": period.get("end"),
    }


def normalize_diagnostic_report(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": resource.get("id"),
        "name": get_code_display(resource.get("code")),
        "status": resource.get("status"),
        "date": resource.get("effectiveDateTime") or resource.get("issued"),
    }


def normalize_document_reference(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": resource.get("id"),
        "type": get_code_display(resource.get("type")),
        "date": resource.get("date"),
        "title": resource.get("description")
        or _first_content_title(resource)
        or get_code_display(resource.get("type")),
    }


def _first_content_title(resource: dict[str, Any]) -> str | None:
    content = resource.get("content") or []
    if not content:
        return None
    attachment = content[0].get("attachment") or {}
    return attachment.get("title")


def build_summary(
    *,
    patient: dict[str, Any] | None,
    labs: list[dict[str, Any]],
    vitals: list[dict[str, Any]],
    conditions: list[dict[str, Any]],
    medications: list[dict[str, Any]],
    allergies: list[dict[str, Any]],
    encounters: list[dict[str, Any]],
    diagnostic_reports: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    scopes: str | None,
) -> dict[str, Any]:
    return {
        "connected": True,
        "source": "epic_sandbox",
        "patient": normalize_patient(patient or {}),
        "labs": [normalize_observation(item) for item in labs],
        "vitals": [normalize_observation(item) for item in vitals],
        "conditions": [normalize_condition(item) for item in conditions],
        "medications": [normalize_medication_request(item) for item in medications],
        "allergies": [normalize_allergy(item) for item in allergies],
        "encounters": [normalize_encounter(item) for item in encounters],
        "diagnosticReports": [
            normalize_diagnostic_report(item) for item in diagnostic_reports
        ],
        "documents": [normalize_document_reference(item) for item in documents],
        "metadata": {
            "retrievedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "scopes": scopes,
            "note": "Sandbox data only. Patient-facing FHIR data may be filtered by Epic configuration.",
        },
    }
