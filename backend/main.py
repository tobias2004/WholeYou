import base64
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from config import (
    EPIC_AUTHORIZE_URL,
    EPIC_CLIENT_ID,
    EPIC_FHIR_BASE_URL,
    EPIC_REDIRECT_URI,
    EPIC_SCOPES,
    FRONTEND_BASE_URL,
)
from epic_client import exchange_code_for_token, fetch_patient_record
from normalize import build_summary

logger = logging.getLogger("wholeyou.oauth")

app = FastAPI(title="WholeYou")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_BASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_DATA: dict[str, Any] = {}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "WholeYou"}


@app.get("/connect/epic")
async def connect_epic() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _pkce_challenge(code_verifier)

    SESSION_DATA.clear()
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


@app.get("/auth/epic/callback")
async def epic_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    if error:
        logger.warning("Epic callback returned authorization error")
        return _frontend_error("epic_authorization_failed")
    if not code:
        logger.warning("Epic callback missing authorization code")
        return _frontend_error("missing_authorization_code")
    if not state or state != SESSION_DATA.get("state"):
        logger.warning("Epic callback state mismatch")
        return _frontend_error("state_mismatch")

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
            return _frontend_error("missing_patient_id")

        logger.info("Epic token exchange succeeded; fetching FHIR resources")
        raw = await fetch_patient_record(
            access_token=token["access_token"], patient_id=patient_id
        )
        summary = build_summary(
            patient=raw.get("patient"),
            labs=raw.get("labs", []),
            vitals=raw.get("vitals", []),
            conditions=raw.get("conditions", []),
            medications=raw.get("medications", []),
            allergies=raw.get("allergies", []),
            encounters=raw.get("encounters", []),
            diagnostic_reports=raw.get("diagnostic_reports", []),
            documents=raw.get("documents", []),
            scopes=token.get("scope"),
        )

        SESSION_DATA.update({"token": _token_metadata(token), "summary": summary, "raw": raw})
        logger.info("Epic FHIR summary stored successfully")
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Epic OAuth/FHIR HTTP error status=%s body=%s",
            exc.response.status_code,
            _safe_response_text(exc.response),
        )
        return _frontend_error("epic_token_exchange_or_fhir_fetch_failed")
    except Exception as exc:
        logger.exception("Epic connection failed: %s", exc.__class__.__name__)
        return _frontend_error("epic_connection_failed")

    return _frontend_redirect("/dashboard")


@app.get("/api/epic/summary")
async def epic_summary() -> dict[str, Any]:
    if not SESSION_DATA.get("summary"):
        return {
            "connected": False,
            "message": "No Epic/MyChart sandbox data connected yet.",
        }
    return SESSION_DATA["summary"]


@app.get("/api/epic/raw")
async def epic_raw() -> dict[str, Any]:
    if not SESSION_DATA.get("raw"):
        raise HTTPException(status_code=404, detail="No raw Epic data connected yet.")
    return SESSION_DATA["raw"]


@app.post("/api/epic/logout")
async def epic_logout() -> dict[str, bool]:
    SESSION_DATA.clear()
    return {"ok": True}


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _frontend_error(message: str) -> HTMLResponse:
    return _frontend_redirect(f"/error?{urlencode({'message': message})}")


def _frontend_redirect(path: str) -> HTMLResponse:
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
