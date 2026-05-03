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

OPEN_WEARABLES_WEBHOOK_SECRET = _get("OPEN_WEARABLES_WEBHOOK_SECRET", "")
STRAVA_CLIENT_ID = _get("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = _get("STRAVA_CLIENT_SECRET", "")
STRAVA_REDIRECT_URI = _get(
    "STRAVA_REDIRECT_URI",
    f"{BACKEND_BASE_URL}/api/wearables/oauth/strava/callback",
)
STRAVA_AUTHORIZE_URL = _get(
    "STRAVA_AUTHORIZE_URL",
    "https://www.strava.com/oauth/authorize",
)
STRAVA_TOKEN_URL = _get("STRAVA_TOKEN_URL", "https://www.strava.com/oauth/token")
STRAVA_API_BASE_URL = _get("STRAVA_API_BASE_URL", "https://www.strava.com/api/v3")

OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = _get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = _get(
    "OPENROUTER_MODEL",
    "nvidia/nemotron-3-super-120b-a12b:free",
)
NVIDIA_RERANKER_API_KEY = _get("NVIDIA_RERANKER_API_KEY", "")
NVIDIA_RERANK_URL = _get(
    "NVIDIA_RERANK_URL",
    "https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking",
)
NVIDIA_RERANK_MODEL = _get(
    "NVIDIA_RERANK_MODEL",
    "nvidia/llama-nemotron-rerank-1b-v2",
)
NVIDIA_TRANSLATION_API_KEY = _get("NVIDIA_TRANSLATION_API_KEY", "")
NVIDIA_TRANSLATION_BASE_URL = _get(
    "NVIDIA_TRANSLATION_BASE_URL",
    "https://integrate.api.nvidia.com/v1",
)
NVIDIA_TRANSLATION_MODEL = _get(
    "NVIDIA_TRANSLATION_MODEL",
    "nvidia/riva-translate-4b-instruct-v1.1",
)
MEDICAL_RAG_DATASET_ID = _get(
    "MEDICAL_RAG_DATASET_ID",
    "Sagarika-Singh-99/medical-rag-corpus",
)
MEDICAL_RAG_DATA_DIR = _get("MEDICAL_RAG_DATA_DIR", "data/medical-rag-corpus")
MEDRAG_TEXTBOOKS_DATA_DIR = _get("MEDRAG_TEXTBOOKS_DATA_DIR", "data/medrag-textbooks")

EPIC_SCOPES = [
    "openid",
    "fhirUser",
    "launch/patient",
    "patient/Patient.read",
    "patient/AllergyIntolerance.read",
    "patient/Binary.read",
    "patient/CarePlan.read",
    "patient/CareTeam.read",
    "patient/Condition.read",
    "patient/Coverage.read",
    "patient/Device.read",
    "patient/DiagnosticReport.read",
    "patient/DocumentReference.read",
    "patient/Encounter.read",
    "patient/Goal.read",
    "patient/Immunization.read",
    "patient/Medication.read",
    "patient/MedicationDispense.read",
    "patient/MedicationRequest.read",
    "patient/Observation.read",
    "patient/Procedure.read",
]
