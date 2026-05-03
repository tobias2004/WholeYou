# WholeYou

WholeYou connects your health records, wearable data, and daily patterns into private, personalized wellness guidance.

## Current Functionality

- Epic/MyChart sandbox OAuth using SMART on FHIR standalone launch
- Backend-mediated Epic FHIR retrieval and normalization
- In-process Open Wearables wearable backend boundary
- Displays normalized WholeYou clinical data from backend clinical endpoints
- Backend AI panel using Nemotron 3 Super through OpenRouter with server-side data tools
- Chat-first dark frontend for attaching context, selecting skills, and reviewing formatted AI output
- Local MedCPT dense retrieval over `Sagarika-Singh-99/medical-rag-corpus` and `MedRAG/textbooks`, pooled and reranked by NVIDIA
- Keeps OAuth state, token metadata, raw FHIR responses, and normalized clinical data in temporary backend memory only

## Not Implemented Yet

- Managed production vector database for RAG
- Cloud storage
- Production Epic access
- Refresh tokens
- Durable per-user RAG artifact management
- Self-hosted AI inference

## Local URLs

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Epic callback: http://localhost:8000/auth/epic/callback
- Wearables: served by the WholeYou backend at http://localhost:8000/api/wearables/*

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

## Open Wearables Configuration

Open Wearables is implemented as a basic in-process WholeYou backend feature in
`backend/integrations/open_wearables`. It does not require a separate Docker
deployment, Open Wearables API server, Postgres, Redis, Celery, API base URL, API
token, or developer JWT for the local MVP.

Configure the WholeYou backend with:

```bash
OPEN_WEARABLES_WEBHOOK_SECRET=
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_REDIRECT_URI=http://localhost:8000/api/wearables/oauth/strava/callback
```

The `/wearables` page has a Synthetic/Real toggle:

- Synthetic mode: connecting a provider creates local synthetic data for that
  provider only.
- Real mode: connecting Strava redirects to Strava OAuth, exchanges the callback
  code server-side, stores provider tokens temporarily in backend memory, and
  imports recent activities as workouts.
- Apple Health XML import: upload an Apple Health `export.xml` file on
  `/wearables`; WholeYou validates the XML, parses supported Apple records, and
  adds standardized timeseries, workout, and sleep records to the dashboard.

Other real wearable providers are listed for UI parity but are not wired to real
OAuth yet. Current storage is temporary in `backend/session_store.py`; this
boundary is intentionally simple so it can be replaced by the WholeYou database
when clinical and wearable persistence are added.

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

Frontend tests:

```bash
cd frontend
npm test
```

## Backend AI

The main chat view sends prompts, selected data IDs, selected documents, and
optional image attachments to the WholeYou backend. The backend calls Nemotron
3 Super through OpenRouter and exposes server-side tools for MyChart data,
wearables data, health-data rerank, translation, and medical-corpus RAG rerank.
Configure `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, and optional model override
variables in the backend environment before generating answers. See
`docs/backend-ai.md` for the current AI boundary.

Local RAG artifacts are intentionally excluded from git under `data/`. The
current local layout is:

```text
data/
  medical-rag-corpus/
    medical_rag.sqlite
    embedding_shards/*.pt
    source/final_corpus.pkl
    source/dense_embeddings.pt
  medrag-textbooks/
    textbooks.sqlite
    embedding_shards/*.pt
```

Both SQLite stores expose the same canonical `documents` table:

```text
embedding_index INTEGER PRIMARY KEY
id TEXT NOT NULL
text TEXT NOT NULL
title TEXT
source TEXT NOT NULL
category TEXT
dataset_id TEXT NOT NULL
```

Both corpora use MedCPT Article Encoder embeddings and are searched with the
MedCPT Query Encoder. Runtime RAG pools candidate rows from both datasets, then
lets NVIDIA rerank choose the final passages used by the model.

## Frontend Experience

The main AI view is chat-first: the user can ask a question directly, expand the
`+` context panel only when needed, attach clinical/wearable/document/image
context, select skills, and review formatted answers with a concise tool/data
disclosure. The current theme is a dark clinical workspace with high-contrast
controls, dark chips/panels, focus states, and hover feedback.

## OAuth Flow

1. User opens http://localhost:3000.
2. User clicks **Connect MyChart**.
3. Frontend sends the browser to http://localhost:8000/connect/epic.
4. Backend creates state and PKCE values, then redirects to Epic authorization.
5. Epic redirects to http://localhost:8000/auth/epic/callback.
6. Backend validates state, exchanges the code for an access token, fetches FHIR resources, normalizes them, and redirects to http://localhost:3000/dashboard.
7. Dashboard calls `GET /api/clinical/summary` and renders normalized clinical data.

The browser does not call Epic FHIR APIs directly and never receives Epic access tokens.
Epic OAuth, token exchange, FHIR requests, and normalization are owned by the backend.

## Backend Architecture

```text
WholeYou frontend
  -> WholeYou backend / API gateway
      -> integrations/epic: Epic OAuth, FHIR client, FHIR normalization
      -> integrations/open_wearables: local Open Wearables backend and normalization
      -> data_sources/clinical: frontend-facing clinical data service
      -> data_sources/wearables: frontend-facing Open Wearables service boundary
      -> data_sources/journal: future journal boundary
      -> data_sources/context: future local LLM context boundary
```

Key backend modules:

- `backend/integrations/epic/client.py`: low-level Epic FHIR API requests
- `backend/integrations/epic/oauth.py`: Epic OAuth callback and token exchange
- `backend/integrations/epic/normalize.py`: FHIR to WholeYou clinical objects
- `backend/integrations/epic/schemas.py`: normalized clinical response models
- `backend/integrations/epic/routes.py`: Epic connection and debug routes
- `backend/integrations/open_wearables/client.py`: local Open Wearables backend storage and behavior
- `backend/integrations/open_wearables/normalize.py`: Open Wearables to WholeYou wearable objects
- `backend/integrations/open_wearables/schemas.py`: normalized wearable response models
- `backend/integrations/open_wearables/routes.py`: wearable route export
- `backend/data_sources/clinical/service.py`: clinical data abstraction used by API routes
- `backend/data_sources/clinical/routes.py`: frontend-facing `/api/clinical/*` routes
- `backend/data_sources/wearables/service.py`: wearable data abstraction and demo user mapping
- `backend/data_sources/wearables/routes.py`: frontend-facing `/api/wearables/*` routes

Current storage is in-memory only via `backend/session_store.py`. Production should replace this with per-user authenticated sessions and secure token storage.

## Open Wearables Architecture

```text
User
  -> WholeYou frontend
      -> WholeYou backend
          -> integrations/open_wearables
              -> future WholeYou database
```

Retrieval flow:

```text
User opens /wearables
  -> frontend calls /api/wearables/*
      -> backend reads/writes local Open Wearables records
          -> backend normalizes records
              -> frontend displays wearable data
```

WholeYou currently stores wearable MVP data in memory:

- WholeYou demo user ID
- Open Wearables user ID
- local provider connection status
- synthetic timeseries, workouts, sleep events, and data sources

Raw wearable records and provider-specific raw payloads stay out of frontend
JavaScript. Production hardening TODOs include authenticated user sessions,
database persistence, encryption at rest, token encryption for real provider
OAuth, webhook signature/replay verification, audit logging, retention policy,
and user disconnect/delete flows.

This milestone implements the basic wearable backend surface, local synthetic
provider data, and Strava OAuth/activity import. Other provider OAuth, HealthKit
native sync, Open Wearables AI features, journaling, and self-hosted AI
inference are intentionally out of scope.

## Future Boundaries

Current backend AI flow:

Browser asks backend for available clinical and wearable categories -> browser
sends prompt plus selected category/document IDs -> backend uses Nemotron 3
Super and server-side tools to fetch/rerank data, query local RAG artifacts, and
produce an answer.

Journal service, managed production vector storage, self-hosted NIM, and
advanced multi-user data isolation are not implemented in this milestone.

## API Endpoints

- `GET /health`
- `GET /connect/epic`
- `GET /auth/epic/callback`
- `GET /api/clinical/summary`
- `GET /api/clinical/conditions`
- `GET /api/clinical/medications`
- `GET /api/clinical/labs`
- `GET /api/clinical/vitals`
- `GET /api/clinical/encounters`
- `GET /api/epic/summary`
- `GET /api/epic/raw`
- `POST /api/epic/logout`
- `GET /api/wearables/summary`
- `GET /api/wearables/providers`
- `POST /api/wearables/connect/{provider}`
- `GET /api/wearables/oauth/{provider}/callback`
- `GET /api/wearables/connections`
- `DELETE /api/wearables/connections`
- `DELETE /api/wearables/connections/{provider}`
- `POST /api/wearables/sync`
- `POST /api/wearables/sync-history`
- `POST /api/wearables/synthetic-data`
- `GET /api/wearables/summary/activity`
- `GET /api/wearables/summary/sleep`
- `GET /api/wearables/summary/body`
- `GET /api/wearables/summary/data`
- `GET /api/wearables/timeseries`
- `GET /api/wearables/events/workouts`
- `GET /api/wearables/events/sleep`
- `GET /api/wearables/data-sources`
- `POST /api/wearables/import/apple-health/xml/upload-url`
- `POST /api/wearables/import/apple-health/xml/direct`
- `POST /api/wearables/webhook/open-wearables`
- `GET /api/local-ai/context/available`
- `GET /api/local-ai/context/documents`
- `POST /api/local-ai/context/raw`
- `POST /api/local-ai/context/document/raw`
- `POST /api/ai/chat`
- `POST /api/ai/chat/stream`

The `/api/epic/*` data endpoints are local debug/compatibility endpoints only. The frontend should use `/api/clinical/*`. Do not expose raw Epic FHIR data in production.
The frontend should use `/api/wearables/*` for wearable data and should never
call Open Wearables directly.
