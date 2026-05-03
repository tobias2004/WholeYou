import logging
from typing import Any

import httpx

from config import EPIC_FHIR_BASE_URL, EPIC_REDIRECT_URI, EPIC_TOKEN_URL

logger = logging.getLogger("wholeyou.epic")


async def exchange_code_for_token(
    *, code: str, client_id: str, code_verifier: str | None = None
) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": EPIC_REDIRECT_URI,
        "client_id": client_id,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            EPIC_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()


async def fetch_bundle_pages(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    max_pages: int = 3,
) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
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

        entries = payload.get("entry") or []
        resources.extend(entry["resource"] for entry in entries if entry.get("resource"))
        next_url = None
        for link in payload.get("link") or []:
            if link.get("relation") == "next":
                next_url = link.get("url")
                break

    return resources


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

        queries = {
            "labs": f"{EPIC_FHIR_BASE_URL}/Observation?patient={patient_id}&category=laboratory",
            "vitals": f"{EPIC_FHIR_BASE_URL}/Observation?patient={patient_id}&category=vital-signs",
            "conditions": f"{EPIC_FHIR_BASE_URL}/Condition?patient={patient_id}",
            "medications": f"{EPIC_FHIR_BASE_URL}/MedicationRequest?patient={patient_id}",
            "allergies": f"{EPIC_FHIR_BASE_URL}/AllergyIntolerance?patient={patient_id}",
            "encounters": f"{EPIC_FHIR_BASE_URL}/Encounter?patient={patient_id}",
            "diagnostic_reports": f"{EPIC_FHIR_BASE_URL}/DiagnosticReport?patient={patient_id}",
            "documents": f"{EPIC_FHIR_BASE_URL}/DocumentReference?patient={patient_id}",
        }

        raw: dict[str, Any] = {"patient": patient_response.json()}
        for name, url in queries.items():
            try:
                resources = await fetch_bundle_pages(client, url, headers, max_pages=3)
                logger.info("FHIR %s count=%s", name, len(resources))
                raw[name] = resources
            except httpx.HTTPStatusError as exc:
                logger.warning("FHIR %s failed with %s", name, exc.response.status_code)
                raw[name] = []

        return raw
