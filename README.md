# WholeYou

WholeYou connects your health records, wearable data, and daily patterns into private, personalized wellness guidance.

## Current Functionality

- Epic/MyChart sandbox OAuth using SMART on FHIR standalone launch
- Fetches patient-facing FHIR data from the Epic sandbox
- Displays patient profile, labs, vitals, conditions, medications, allergies, encounters, reports, and clinical document metadata
- Keeps OAuth state, token metadata, raw FHIR responses, and normalized summary data in temporary backend memory only

## Not Implemented Yet

- Wearable integrations
- Local SLM
- RAG
- Cloud storage
- Production Epic access
- Refresh tokens

## Local URLs

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Epic callback: http://localhost:8000/auth/epic/callback

## Epic Sandbox Configuration

- Endpoint URI: http://localhost:3000
- Redirect URI: http://localhost:8000/auth/epic/callback
- Non-production client ID: `73dccc76-0b72-496b-886f-7c0627c2429f`
- FHIR base URL: https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4

Confirm the Epic app is marked ready for sandbox. Epic sandbox app changes can take up to 1 hour to propagate.

## Run Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 and click **Connect MyChart**.

## Development Checks

Backend normalization tests:

```bash
PYTHONPATH=backend python3 -m unittest backend/tests/test_normalize.py
```

Frontend production build:

```bash
cd frontend
npm run build
```

## OAuth Flow

1. User opens http://localhost:3000.
2. User clicks **Connect MyChart**.
3. Frontend sends the browser to http://localhost:8000/connect/epic.
4. Backend creates state and PKCE values, then redirects to Epic authorization.
5. Epic redirects to http://localhost:8000/auth/epic/callback.
6. Backend validates state, exchanges the code for an access token, fetches FHIR resources, normalizes them, and redirects to http://localhost:3000/dashboard.
7. Dashboard calls `GET /api/epic/summary` and renders the returned data.

## API Endpoints

- `GET /health`
- `GET /connect/epic`
- `GET /auth/epic/callback`
- `GET /api/epic/summary`
- `GET /api/epic/raw`
- `POST /api/epic/logout`

`GET /api/epic/raw` is for local debugging only. Do not expose it in production.
