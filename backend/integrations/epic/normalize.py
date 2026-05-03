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


def normalize_condition(resource: dict[str, Any]) -> dict[str, Any]:
    coding = get_first_coding(resource.get("code")) or {}
    return {
        "id": resource.get("id"),
        "name": get_code_display(resource.get("code")),
        "code": coding.get("code"),
        "clinicalStatus": _status_code(resource.get("clinicalStatus")),
        "verificationStatus": _status_code(resource.get("verificationStatus")),
        "recordedDate": resource.get("recordedDate") or resource.get("onsetDateTime"),
        "source": "epic",
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
        "dosageText": "; ".join(item.get("text", "") for item in dosage if item.get("text"))
        or None,
        "authoredOn": resource.get("authoredOn"),
        "source": "epic",
    }


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
        "code": coding.get("code"),
        "value": value,
        "unit": unit,
        "referenceRange": _reference_range(resource),
        "interpretation": _normalize_interpretation(resource),
        "effectiveDateTime": _effective_date(resource),
        "source": "epic",
    }


def normalize_encounter(resource: dict[str, Any]) -> dict[str, Any]:
    types = resource.get("type") or []
    period = resource.get("period") or {}
    reasons = resource.get("reasonCode") or []
    participants = resource.get("participant") or []
    provider = None
    if participants:
        individual = participants[0].get("individual") or {}
        provider = individual.get("display")

    return {
        "id": resource.get("id"),
        "type": get_code_display(types[0]) if types else None,
        "periodStart": period.get("start"),
        "periodEnd": period.get("end"),
        "reason": get_code_display(reasons[0]) if reasons else None,
        "provider": provider,
        "source": "epic",
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
        "source": "epic",
    }


def normalize_diagnostic_report(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": resource.get("id"),
        "name": get_code_display(resource.get("code")),
        "status": resource.get("status"),
        "date": resource.get("effectiveDateTime") or resource.get("issued"),
        "source": "epic",
    }


def normalize_document_reference(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": resource.get("id"),
        "type": get_code_display(resource.get("type")),
        "date": resource.get("date"),
        "title": resource.get("description")
        or _first_content_title(resource)
        or get_code_display(resource.get("type")),
        "source": "epic",
    }


def build_clinical_summary(
    *,
    labs: list[dict[str, Any]],
    vitals: list[dict[str, Any]],
    conditions: list[dict[str, Any]],
    medications: list[dict[str, Any]],
    encounters: list[dict[str, Any]],
    patient: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "connected": True,
        "patient": normalize_patient(patient or {}) if patient is not None else None,
        "conditions": [normalize_condition(item) for item in conditions],
        "medications": [normalize_medication_request(item) for item in medications],
        "labs": [normalize_observation(item) for item in labs],
        "vitals": [normalize_observation(item) for item in vitals],
        "encounters": [normalize_encounter(item) for item in encounters],
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def build_epic_debug_summary(
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
    summary = build_clinical_summary(
        patient=patient,
        labs=labs,
        vitals=vitals,
        conditions=conditions,
        medications=medications,
        encounters=encounters,
    )
    summary.update(
        {
            "source": "epic_sandbox",
            "allergies": [normalize_allergy(item) for item in allergies],
            "diagnosticReports": [
                normalize_diagnostic_report(item) for item in diagnostic_reports
            ],
            "documents": [normalize_document_reference(item) for item in documents],
            "metadata": {
                "retrievedAt": summary["generatedAt"],
                "scopes": scopes,
                "note": "Sandbox data only. Patient-facing FHIR data may be filtered by Epic configuration.",
            },
        }
    )
    return summary


def _status_code(value: dict[str, Any] | None) -> str | None:
    coding = get_first_coding(value)
    return coding.get("code") if coding else None


def _effective_date(resource: dict[str, Any]) -> str | None:
    return resource.get("effectiveDateTime") or resource.get("issued")


def _quantity_value(quantity: dict[str, Any] | None) -> tuple[Any, str | None]:
    if not quantity:
        return None, None
    return quantity.get("value"), quantity.get("unit") or quantity.get("code")


def _normalize_interpretation(resource: dict[str, Any]) -> str | None:
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


def _reference_range(resource: dict[str, Any]) -> str | None:
    ranges = resource.get("referenceRange") or []
    if not ranges:
        return None
    first = ranges[0]
    if first.get("text"):
        return first["text"]
    low = (first.get("low") or {}).get("value")
    high = (first.get("high") or {}).get("value")
    unit = (first.get("high") or first.get("low") or {}).get("unit")
    if low is not None and high is not None:
        suffix = f" {unit}" if unit else ""
        return f"{low}-{high}{suffix}"
    return None


def _first_content_title(resource: dict[str, Any]) -> str | None:
    content = resource.get("content") or []
    if not content:
        return None
    attachment = content[0].get("attachment") or {}
    return attachment.get("title")
