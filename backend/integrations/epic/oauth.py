import base64
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi.responses import HTMLResponse, RedirectResponse

from config import (
    EPIC_AUTHORIZE_URL,
    EPIC_CLIENT_ID,
    EPIC_FHIR_BASE_URL,
    EPIC_REDIRECT_URI,
    EPIC_SCOPES,
    EPIC_TOKEN_URL,
    FRONTEND_BASE_URL,
)
from integrations.epic.client import fetch_patient_record
from session_store import SESSION_DATA

logger = logging.getLogger("wholeyou.oauth")

EPIC_DATA_KEYS = ("clinical_summary", "summary", "raw")
EPIC_SESSION_KEYS = ("token", "state", "code_verifier", *EPIC_DATA_KEYS)


def build_authorize_redirect() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _pkce_challenge(code_verifier)

    _clear_keys(EPIC_SESSION_KEYS)
    SESSION_DATA.update({"state": state, "code_verifier": code_verifier})

    params = {
        "response_type": "code",
        "client_id": EPIC_CLIENT_ID,
        "redirect_uri": EPIC_REDIRECT_URI,
        "scope": " ".join(EPIC_SCOPES),
        "aud": EPIC_FHIR_BASE_URL,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return RedirectResponse(f"{EPIC_AUTHORIZE_URL}?{urlencode(params)}")


async def handle_callback(
    *, code: str | None, state: str | None, error: str | None
) -> HTMLResponse:
    if error:
        logger.warning("Epic callback returned authorization error")
        return frontend_error("epic_authorization_failed")
    if not code:
        logger.warning("Epic callback missing authorization code")
        return frontend_error("missing_authorization_code")
    if not state or state != SESSION_DATA.get("state"):
        logger.warning("Epic callback state mismatch")
        return frontend_error("state_mismatch")

    try:
        logger.info("Epic callback received authorization code; exchanging token")
        token = await exchange_code_for_token(
            code=code,
            client_id=EPIC_CLIENT_ID,
            code_verifier=SESSION_DATA.get("code_verifier"),
        )
        patient_id = token.get("patient")
        if not patient_id:
            logger.warning("Epic token response missing patient context")
            return frontend_error("missing_patient_id")

        logger.info("Epic token exchange succeeded; fetching FHIR resources")
        raw = await fetch_patient_record(
            access_token=token["access_token"], patient_id=patient_id
        )

        SESSION_DATA.update(
            {
                "token": _token_metadata(token),
                "clinical_summary": {
                    "connected": True,
                    "patient": None,
                    "conditions": [],
                    "medications": [],
                    "labs": [],
                    "vitals": [],
                    "encounters": [],
                    "generatedAt": None,
                    "message": "Epic FHIR data is available from /api/epic/raw as fhir.resources models serialized to JSON.",
                },
                "summary": raw.get("raw_responses", raw),
                "raw": raw.get("raw_responses", raw),
            }
        )
        logger.info("Epic clinical summary stored successfully")
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Epic OAuth/FHIR HTTP error status=%s body=%s",
            exc.response.status_code,
            _safe_response_text(exc.response),
        )
        return frontend_error("epic_token_exchange_or_fhir_fetch_failed")
    except Exception as exc:
        logger.exception("Epic connection failed: %s", exc.__class__.__name__)
        return frontend_error("epic_connection_failed")

    return frontend_redirect("/")


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


def clear_epic_session() -> dict[str, bool]:
    _clear_keys(EPIC_SESSION_KEYS)
    return {"ok": True}


def clear_epic_data() -> dict[str, bool]:
    _clear_keys(EPIC_DATA_KEYS)
    return {"ok": True}


def _clear_keys(keys: tuple[str, ...]) -> None:
    for key in keys:
        SESSION_DATA.pop(key, None)


def frontend_error(message: str) -> HTMLResponse:
    return frontend_redirect(f"/error?{urlencode({'message': message})}")


def frontend_redirect(path: str) -> HTMLResponse:
    target = f"{FRONTEND_BASE_URL}{path}"
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="refresh" content="0;url={target}" />
    <title>Returning to WholeYou</title>
  </head>
  <body>
    <p>Returning to WholeYou...</p>
    <p><a href="{target}">Continue to WholeYou</a></p>
    <script>
      window.top.location.replace("{target}");
    </script>
  </body>
</html>"""
    )


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _token_metadata(token: dict[str, Any]) -> dict[str, Any]:
    return {
        "patient": token.get("patient"),
        "scope": token.get("scope"),
        "expires_in": token.get("expires_in"),
        "token_type": token.get("token_type"),
    }


def _safe_response_text(response: httpx.Response) -> str:
    text = response.text.strip().replace("\n", " ")
    return text[:500]
