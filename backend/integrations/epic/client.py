import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse, urlencode

import httpx

from config import EPIC_FHIR_BASE_URL
from integrations.epic.fhir_models import parse_fhir_resource, parse_fhir_resources

logger = logging.getLogger("wholeyou.epic")


@dataclass(frozen=True)
class PatientRecordQuery:
    resource_type: str
    params: dict[str, str] = field(default_factory=dict)

    def url(self, patient_id: str) -> str:
        params = {"patient": patient_id, **self.params}
        return f"{EPIC_FHIR_BASE_URL}/{self.resource_type}?{urlencode(params)}"


async def fetch_bundle_pages(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    max_pages: int = 3,
) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    next_url: str | None = url

    for _ in range(max_pages):
        if not next_url:
            break
        response = await client.get(next_url, headers=headers)
        logger.info("FHIR GET %s -> %s", next_url.split("?")[0], response.status_code)
        response.raise_for_status()
        payload = response.json()

        if payload.get("resourceType") != "Bundle":
            return [payload]

        pages.append(payload)
        next_url = None
        for link in payload.get("link") or []:
            if link.get("relation") == "next":
                next_url = link.get("url")
                break

    return pages


def resources_from_fhir_response_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for page in pages:
        if page.get("resourceType") != "Bundle":
            resources.append(page)
            continue
        entries = page.get("entry") or []
        resources.extend(entry["resource"] for entry in entries if entry.get("resource"))
    return resources


def binary_read_url_from_attachment_url(attachment_url: str | None) -> str | None:
    if not attachment_url:
        return None

    parsed = urlparse(attachment_url)
    if parsed.scheme in {"http", "https"}:
        if "/Binary/" not in parsed.path:
            return None
        return attachment_url

    stripped_url = attachment_url.lstrip("/")
    if not stripped_url.startswith("Binary/"):
        return None
    return urljoin(f"{EPIC_FHIR_BASE_URL}/", stripped_url)


def binary_read_urls_from_document_reference(document: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for content in document.get("content") or []:
        attachment = content.get("attachment") or {}
        url = binary_read_url_from_attachment_url(attachment.get("url"))
        if url and url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def attach_binary_resource_to_document(
    document: dict[str, Any], binary: dict[str, Any]
) -> None:
    contained = document.setdefault("contained", [])
    binary_id = binary.get("id")
    if binary_id and any(
        resource.get("resourceType") == "Binary" and resource.get("id") == binary_id
        for resource in contained
    ):
        return
    contained.append(binary)


async def attach_binary_resources_to_documents(
    client: httpx.AsyncClient,
    documents: list[dict[str, Any]],
    headers: dict[str, str],
) -> int:
    fetched_binaries: dict[str, dict[str, Any]] = {}
    attached_count = 0

    for document in documents:
        if document.get("resourceType") != "DocumentReference":
            continue

        for url in binary_read_urls_from_document_reference(document):
            binary = fetched_binaries.get(url)
            if binary is None:
                response = await client.get(url, headers=headers)
                logger.info("FHIR GET Binary -> %s", response.status_code)
                response.raise_for_status()
                binary = response.json()
                fetched_binaries[url] = binary

            parse_fhir_resource(binary)
            attach_binary_resource_to_document(document, binary)
            attached_count += 1

    return attached_count


def build_patient_record_queries(patient_id: str) -> dict[str, PatientRecordQuery]:
    return {
        "allergies_patient_chart": PatientRecordQuery("AllergyIntolerance"),
        "allergies_outside_record": PatientRecordQuery("AllergyIntolerance"),
        "care_plans_encounter": PatientRecordQuery("CarePlan"),
        "care_plans_longitudinal": PatientRecordQuery("CarePlan"),
        "care_plans_outside_record": PatientRecordQuery("CarePlan"),
        "care_teams_longitudinal": PatientRecordQuery("CareTeam"),
        "care_teams_outside_record": PatientRecordQuery("CareTeam"),
        "conditions_encounter_diagnosis": PatientRecordQuery("Condition"),
        "conditions_health_concerns": PatientRecordQuery("Condition"),
        "conditions_problems": PatientRecordQuery("Condition"),
        "conditions_outside_record_encounter_diagnosis": PatientRecordQuery("Condition"),
        "conditions_outside_record_health_concerns": PatientRecordQuery("Condition"),
        "conditions_outside_record_problems": PatientRecordQuery("Condition"),
        "diagnostic_reports_results": PatientRecordQuery("DiagnosticReport"),
        "diagnostic_reports_outside_record_results": PatientRecordQuery("DiagnosticReport"),
        "documents_clinical_notes": PatientRecordQuery("DocumentReference"),
        "documents_labs": PatientRecordQuery("DocumentReference"),
        "documents_outside_record_clinical_notes": PatientRecordQuery("DocumentReference"),
        "encounters_patient_chart": PatientRecordQuery("Encounter"),
        "encounters_outside_record": PatientRecordQuery("Encounter"),
        "goals_patient": PatientRecordQuery("Goal"),
        "goals_outside_record": PatientRecordQuery("Goal"),
        "goals_care_plan_goal": PatientRecordQuery("Goal"),
        "immunizations_patient_chart": PatientRecordQuery("Immunization"),
        "observations_assessments": PatientRecordQuery("Observation"),
        "observations_labs": PatientRecordQuery(
            "Observation", {"category": "laboratory"}
        ),
        "observations_sdoh_assessments": PatientRecordQuery("Observation"),
        "observations_social_history": PatientRecordQuery(
            "Observation", {"category": "social-history"}
        ),
        "observations_vital_signs": PatientRecordQuery(
            "Observation", {"category": "vital-signs"}
        ),
        "observations_outside_record_activities_of_daily_living": PatientRecordQuery(
            "Observation"
        ),
        "observations_outside_record_occupation": PatientRecordQuery("Observation"),
        "observations_outside_record_pregnancy_status": PatientRecordQuery("Observation"),
        "observations_outside_record_results": PatientRecordQuery("Observation"),
        "observations_outside_record_screening_assessment": PatientRecordQuery(
            "Observation"
        ),
        "observations_outside_record_sdoh_assessment": PatientRecordQuery("Observation"),
        "observations_outside_record_sexual_orientation": PatientRecordQuery(
            "Observation"
        ),
        "observations_outside_record_smoking_status": PatientRecordQuery("Observation"),
        "observations_outside_record_vital_signs": PatientRecordQuery(
            "Observation", {"category": "vital-signs"}
        ),
        "observations_smartdata_elements": PatientRecordQuery("Observation"),
        "procedures_orders": PatientRecordQuery("Procedure"),
        "procedures_surgeries": PatientRecordQuery("Procedure"),
        "procedures_outside_record": PatientRecordQuery("Procedure"),
        "procedures_sdoh_intervention": PatientRecordQuery("Procedure"),
        "medication_requests_signed_order": PatientRecordQuery("MedicationRequest"),
        "medication_requests_outside_record": PatientRecordQuery("MedicationRequest"),
        "medication_dispenses_fill_status": PatientRecordQuery("MedicationDispense"),
        "medication_dispenses_outside_record": PatientRecordQuery("MedicationDispense"),
        "medications_outside_record": PatientRecordQuery("Medication"),
        "devices_implants": PatientRecordQuery("Device"),
        "devices_outside_record": PatientRecordQuery("Device"),
        "coverage_outside_record": PatientRecordQuery("Coverage"),
        "coverage_patient_insurance": PatientRecordQuery("Coverage"),
    }


async def fetch_patient_record(
    *, access_token: str, patient_id: str
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/fhir+json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        patient_response = await client.get(
            f"{EPIC_FHIR_BASE_URL}/Patient/{patient_id}", headers=headers
        )
        logger.info("FHIR GET Patient -> %s", patient_response.status_code)
        patient_response.raise_for_status()

        patient = patient_response.json()
        resources_by_type: dict[str, Any] = {
            "patient": patient,
            "patient_model": parse_fhir_resource(patient),
        }
        raw_responses: dict[str, Any] = {"patient": parse_fhir_resource(patient)}
        query_models: dict[str, Any] = {}
        for name, query in build_patient_record_queries(patient_id).items():
            try:
                url = query.url(patient_id)
                pages = await fetch_bundle_pages(client, url, headers, max_pages=3)
                resources = resources_from_fhir_response_pages(pages)
                if query.resource_type == "DocumentReference":
                    binary_count = await attach_binary_resources_to_documents(
                        client, resources, headers
                    )
                    logger.info("FHIR %s binary_count=%s", name, binary_count)
                logger.info("FHIR %s count=%s", name, len(resources))
                resources_by_type[name] = resources
                query_models[name] = parse_fhir_resources(resources)
                raw_responses[name] = [parse_fhir_resource(page) for page in pages]
            except httpx.HTTPStatusError as exc:
                logger.warning("FHIR %s failed with %s", name, exc.response.status_code)
                resources_by_type[name] = []
                raw_responses[name] = []
                query_models[name] = []

        _add_legacy_aliases(resources_by_type)
        resources_by_type["fhir_models"] = query_models
        resources_by_type["raw_responses"] = raw_responses
        return resources_by_type


def _add_legacy_aliases(resources_by_type: dict[str, Any]) -> None:
    resources_by_type["labs"] = resources_by_type.get("observations_labs", [])
    resources_by_type["vitals"] = resources_by_type.get("observations_vital_signs", [])
    resources_by_type["conditions"] = [
        *resources_by_type.get("conditions_encounter_diagnosis", []),
        *resources_by_type.get("conditions_health_concerns", []),
        *resources_by_type.get("conditions_problems", []),
        *resources_by_type.get("conditions_outside_record_encounter_diagnosis", []),
        *resources_by_type.get("conditions_outside_record_health_concerns", []),
        *resources_by_type.get("conditions_outside_record_problems", []),
    ]
    resources_by_type["medications"] = [
        *resources_by_type.get("medication_requests_signed_order", []),
        *resources_by_type.get("medication_requests_outside_record", []),
    ]
    resources_by_type["allergies"] = [
        *resources_by_type.get("allergies_patient_chart", []),
        *resources_by_type.get("allergies_outside_record", []),
    ]
    resources_by_type["encounters"] = [
        *resources_by_type.get("encounters_patient_chart", []),
        *resources_by_type.get("encounters_outside_record", []),
    ]
    resources_by_type["diagnostic_reports"] = [
        *resources_by_type.get("diagnostic_reports_results", []),
        *resources_by_type.get("diagnostic_reports_outside_record_results", []),
    ]
    resources_by_type["documents"] = [
        *resources_by_type.get("documents_clinical_notes", []),
        *resources_by_type.get("documents_labs", []),
        *resources_by_type.get("documents_outside_record_clinical_notes", []),
    ]
