import os

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str) -> str:
    return os.getenv(name, default)


EPIC_CLIENT_ID = _get("EPIC_CLIENT_ID", "73dccc76-0b72-496b-886f-7c0627c2429f")
FRONTEND_BASE_URL = _get("FRONTEND_BASE_URL", "http://localhost:3000")
BACKEND_BASE_URL = _get("BACKEND_BASE_URL", "http://localhost:8000")
EPIC_REDIRECT_URI = _get(
    "EPIC_REDIRECT_URI", "http://localhost:8000/auth/epic/callback"
)
EPIC_FHIR_BASE_URL = _get(
    "EPIC_FHIR_BASE_URL",
    "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
)
EPIC_AUTHORIZE_URL = _get(
    "EPIC_AUTHORIZE_URL",
    "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/authorize",
)
EPIC_TOKEN_URL = _get(
    "EPIC_TOKEN_URL",
    "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token",
)

EPIC_SCOPES = [
    "openid",
    "fhirUser",
    "launch/patient",
    "patient/Patient.read",
    "patient/Observation.read",
    "patient/Condition.read",
    "patient/MedicationRequest.read",
    "patient/Medication.read",
    "patient/AllergyIntolerance.read",
    "patient/Encounter.read",
    "patient/DiagnosticReport.read",
    "patient/DocumentReference.read",
    "patient/Binary.read",
]
