# Local AI Context Catalog Design

## Goal

Reduce browser memory use on the Local AI page by preventing the browser from loading, rendering, or storing full Epic/MyChart and Open Wearables datasets. The browser should only see lightweight availability metadata until the user generates with selected context.

## Current Problem

The Local AI page currently calls `/api/epic/raw` and `getWearablesPageData()` before generation. That brings a large Epic payload and multiple Open Wearables payloads into React state, renders them as a recursive JSON tree, defaults all leaves to selected, and then reconstructs selected raw JSON before injecting it into the prompt.

This duplicates large backend-held data in the browser and adds memory pressure next to the WebGPU model runtime.

## Requirements

- After Epic OAuth, the backend stores the fetched Epic data. The browser must not receive full Epic raw data unless it explicitly requests selected categories for generation.
- After Open Wearables OAuth or synthetic data generation, the backend stores the wearable data. The browser must not receive full wearable data unless it explicitly requests selected categories for generation.
- The Local AI context selector must call a backend availability endpoint that returns only category metadata.
- The Local AI page must display a flat category checklist, not a recursive raw JSON tree.
- On generation, the frontend must request only the selected raw categories from the backend.
- Selected raw payloads must be transient in the browser. They should not be stored in React state, browser storage, or long-lived module variables.
- After selected raw payloads are handed to the LLM generation path, the frontend must clear references in a `finally` path so the garbage collector can reclaim them.
- The backend can return raw payloads for now. Compact LLM-ready summaries are out of scope for this change.
- Existing dashboard and wearable pages can keep their current endpoints unless they are directly part of the Local AI flow.

## API Design

Add a backend API boundary for Local AI context:

`GET /api/local-ai/context/available`

Returns lightweight metadata:

```json
{
  "sources": [
    {
      "id": "epic",
      "label": "Epic MyChart",
      "connected": true,
      "categories": [
        {
          "id": "epic.patient",
          "source": "epic",
          "key": "patient",
          "label": "Patient",
          "available": true,
          "recordCount": 1
        }
      ]
    }
  ]
}
```

`POST /api/local-ai/context/raw`

Request:

```json
{
  "categoryIds": ["epic.patient", "wearables.timeseries.heart_rate"]
}
```

Response:

```json
{
  "selectedRawContext": {
    "epic": {
      "patient": {}
    },
    "openWearables": {
      "heartRate": []
    }
  },
  "generatedAt": "2026-05-03T00:00:00.000Z"
}
```

Unknown, unavailable, or disconnected categories should return a client error with a clear message. Partial success should not silently omit categories, because the user selected them explicitly for the prompt.

## Category Model

Epic category IDs should map to top-level keys in the compacted Epic raw payload. Examples:

- `epic.patient`
- `epic.conditions_problems`
- `epic.observations_labs`
- `epic.observations_vital_signs`
- `epic.medication_requests_signed_order`
- `epic.documents_labs`

Open Wearables category IDs should map to existing backend service calls rather than preloading `getWearablesPageData()` in the browser. Examples:

- `wearables.connections`
- `wearables.summary.activity`
- `wearables.summary.sleep`
- `wearables.summary.body`
- `wearables.summary.data`
- `wearables.data_sources`
- `wearables.timeseries.heart_rate`
- `wearables.timeseries.steps`
- `wearables.events.workouts`
- `wearables.events.sleep`
- `wearables.health_scores`

Availability metadata should include counts when cheap to compute. For Epic, counts can be derived from backend-held top-level raw values. For Wearables, counts can be derived from the service responses or omitted/null if the count would require an expensive fetch.

## Frontend Design

Replace the JSON tree context selector in `LocalLlmPanel` with a lightweight category selector:

- `loadContextAvailability()` calls `getLocalAiContextAvailability()`.
- Component state stores only availability metadata and selected category IDs.
- The UI defaults to no categories selected, except a small default such as `epic.patient` can be considered later after memory behavior is stable.
- On generate:
  - Build a local `let contextPacket` variable.
  - If categories are selected, call `getLocalAiSelectedRawContext(categoryIds)`.
  - Pass the returned context packet into `generate()`.
  - In a `finally` block, set `contextPacket = undefined`.
- Do not store selected raw payloads in React state.
- Do not persist selected raw payloads to `localStorage`, `sessionStorage`, IndexedDB, URL params, or caches.

The existing `JsonContextChecklist` and `jsonSelection` utilities should no longer be used by Local AI. They can be deleted if unused elsewhere, or left temporarily if tests still cover them during incremental migration.

## Backend Design

Add a focused backend module or route file for Local AI context aggregation. It should depend on existing Epic session data and wearable services, but should own the Local AI category IDs and response shape.

Epic raw category resolution:

- Read `SESSION_DATA["raw"]`.
- Serialize/compact using the same logic currently used by `/api/epic/raw`.
- Return only requested top-level keys.

Open Wearables category resolution:

- Use `WearableDataService` with the existing demo user.
- Fetch only requested categories.
- Preserve existing limits for potentially large arrays unless the category contract specifies otherwise. Initial defaults can match current Local AI behavior: 12 heart-rate points, 12 step points, 5 workouts, 5 sleep events, and 12 health scores.

The backend remains the owner of full source data. The Local AI browser code receives only selected raw slices.

## Error Handling

- If no Epic data is connected, Epic categories should be absent or marked unavailable.
- If Open Wearables is not configured or has no data, wearable categories should be absent or marked unavailable.
- If selected categories are unavailable at generation time, `POST /api/local-ai/context/raw` should return `400` or `404` with a useful `detail`.
- Frontend generation should continue without context only when the user selected no categories. It should not silently drop selected-but-failed categories.

## Testing

Backend tests:

- Availability endpoint returns only metadata, not raw payloads.
- Epic category list reflects stored Epic top-level keys.
- Selected Epic category fetch returns only requested keys.
- Wearable selected category fetch calls only the requested service methods.
- Unknown category IDs return a client error.

Frontend tests:

- Local AI availability fetch stores metadata, not raw context.
- Generate fetches selected raw context only at generation time.
- Raw context is not written to component state.
- Generate clears transient context references in a `finally` path.
- Existing prompt generation still receives the selected raw context packet.

## Out Of Scope

- Worker/offscreen model hosting.
- Prompt token budgeting.
- Compact clinical/wearable summarization.
- Production encrypted backend storage.
- Multi-user auth scoping beyond the current local MVP session model.
