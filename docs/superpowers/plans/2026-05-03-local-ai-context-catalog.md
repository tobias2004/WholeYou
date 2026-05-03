# Local AI Context Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Local AI's raw JSON browser loading with a backend context catalog and transient selected raw context fetches.

**Architecture:** Add a backend Local AI context route that exposes lightweight availability metadata and selected raw payload fetches. Update the frontend Local AI panel to store only metadata and selected category IDs, fetching selected raw data only inside the generation call and clearing references in `finally`.

**Tech Stack:** FastAPI, Python `unittest`, React, TypeScript, Vite/Vitest.

---

## File Structure

- Create `backend/data_sources/local_ai/__init__.py`: package marker.
- Create `backend/data_sources/local_ai/routes.py`: FastAPI routes, category catalog, selected raw context resolver.
- Modify `backend/main.py`: include the Local AI context router.
- Create `backend/tests/test_local_ai_context_routes.py`: backend route tests for metadata-only availability and selected raw fetches.
- Modify `frontend/src/api.ts`: add Local AI context API types and fetch helpers.
- Modify `frontend/src/components/local-llm/LocalLlmPanel.tsx`: replace recursive JSON picker with flat metadata checklist and transient raw context fetch.
- Modify `frontend/src/lib/local-llm/types.ts`: narrow `selectedRawContext` object shape if needed for selected raw response.
- Modify or remove `frontend/src/lib/local-llm/jsonSelection.test.ts`: keep only if `jsonSelection.ts` remains used elsewhere.
- Optionally delete `frontend/src/components/local-llm/JsonContextChecklist.tsx` and `frontend/src/lib/local-llm/jsonSelection.ts` after confirming no references remain.

---

### Task 1: Backend Local AI Context Route Tests

**Files:**
- Create: `backend/tests/test_local_ai_context_routes.py`

- [ ] **Step 1: Write failing tests for availability and selected raw fetches**

Create `backend/tests/test_local_ai_context_routes.py`:

```python
import unittest

from fastapi.testclient import TestClient

import data_sources.local_ai.routes as local_ai_routes
from integrations.epic.fhir_models import parse_fhir_resource
from main import app
from session_store import SESSION_DATA


class FakeWearableDataService:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    async def get_connections(self, user_id):
        self.calls.append(("get_connections", user_id))
        return [{"provider": "oura", "scopes": [], "source": "open_wearables"}]

    async def get_summary(self, user_id, summary_type):
        self.calls.append(("get_summary", summary_type))
        return {"source": "open_wearables", "summaryType": summary_type}

    async def get_data_sources(self, user_id):
        self.calls.append(("get_data_sources", user_id))
        return {"source": "open_wearables", "dataSources": [{"provider": "oura"}]}

    async def get_timeseries(self, user_id, filters=None):
        self.calls.append(("get_timeseries", filters))
        return [{"type": filters["type"], "value": 64, "source": {"provider": "oura"}}]

    async def get_workouts(self, user_id, filters=None):
        self.calls.append(("get_workouts", filters))
        return [{"id": "workout-1", "source": {"provider": "oura"}}]

    async def get_sleep(self, user_id, filters=None):
        self.calls.append(("get_sleep", filters))
        return [{"id": "sleep-1", "source": {"provider": "oura"}}]

    async def get_health_scores(self, user_id, filters=None):
        self.calls.append(("get_health_scores", filters))
        return [{"id": "score-1", "category": "sleep", "components": {}}]


class LocalAiContextRoutesTests(unittest.TestCase):
    def setUp(self):
        SESSION_DATA.clear()
        self.fake_service = FakeWearableDataService()
        self.original_service = local_ai_routes._wearable_service
        local_ai_routes._wearable_service = lambda: self.fake_service
        self.client = TestClient(app)

    def tearDown(self):
        local_ai_routes._wearable_service = self.original_service
        SESSION_DATA.clear()

    def test_available_returns_metadata_without_raw_payloads(self):
        SESSION_DATA["raw"] = {
            "patient": parse_fhir_resource(
                {
                    "resourceType": "Patient",
                    "id": "patient-123",
                    "name": [{"text": "Test Patient"}],
                }
            ),
            "observations_labs": [
                {
                    "resourceType": "Observation",
                    "id": "lab-1",
                    "valueString": "large raw value should not appear",
                }
            ],
        }

        response = self.client.get("/api/local-ai/context/available")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("sources", payload)
        body = response.text
        self.assertIn("epic.patient", body)
        self.assertIn("epic.observations_labs", body)
        self.assertNotIn("Test Patient", body)
        self.assertNotIn("large raw value should not appear", body)

    def test_raw_returns_only_selected_epic_categories(self):
        SESSION_DATA["raw"] = {
            "patient": {"resourceType": "Patient", "id": "patient-123"},
            "observations_labs": [{"resourceType": "Observation", "id": "lab-1"}],
        }

        response = self.client.post(
            "/api/local-ai/context/raw",
            json={"categoryIds": ["epic.patient"]},
        )

        self.assertEqual(response.status_code, 200)
        selected = response.json()["selectedRawContext"]
        self.assertEqual(selected["epic"]["patient"]["id"], "patient-123")
        self.assertNotIn("observations_labs", selected["epic"])

    def test_raw_fetches_only_requested_wearable_category(self):
        response = self.client.post(
            "/api/local-ai/context/raw",
            json={"categoryIds": ["wearables.timeseries.heart_rate"]},
        )

        self.assertEqual(response.status_code, 200)
        selected = response.json()["selectedRawContext"]
        self.assertEqual(selected["openWearables"]["heartRate"][0]["type"], "heart_rate")
        self.assertEqual(
            self.fake_service.calls,
            [("get_timeseries", {"type": "heart_rate", "limit": 12})],
        )

    def test_raw_rejects_unknown_categories(self):
        response = self.client.post(
            "/api/local-ai/context/raw",
            json={"categoryIds": ["epic.not_a_real_category"]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown context category", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd /Users/tobi/WholeYou/backend
python -m unittest tests.test_local_ai_context_routes -v
```

Expected: import or route failures because `data_sources.local_ai.routes` and `/api/local-ai/context/*` do not exist.

---

### Task 2: Backend Local AI Context Routes

**Files:**
- Create: `backend/data_sources/local_ai/__init__.py`
- Create: `backend/data_sources/local_ai/routes.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_local_ai_context_routes.py`

- [ ] **Step 1: Add Local AI context package marker**

Create `backend/data_sources/local_ai/__init__.py`:

```python
"""Local AI context aggregation routes."""
```

- [ ] **Step 2: Implement the Local AI context route**

Create `backend/data_sources/local_ai/routes.py`:

```python
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from data_sources.wearables.service import DEMO_USER_ID, WearableDataService
from integrations.epic.routes import compact_epic_raw_for_browser
from session_store import SESSION_DATA

router = APIRouter(prefix="/api/local-ai/context", tags=["local-ai-context"])


class ContextCategory(BaseModel):
    id: str
    source: str
    key: str
    label: str
    available: bool = True
    recordCount: int | None = None


class ContextSource(BaseModel):
    id: str
    label: str
    connected: bool
    categories: list[ContextCategory]


class ContextAvailabilityResponse(BaseModel):
    sources: list[ContextSource]


class RawContextRequest(BaseModel):
    categoryIds: list[str] = Field(default_factory=list, min_length=0)


class RawContextResponse(BaseModel):
    selectedRawContext: dict[str, Any]
    generatedAt: str


WEARABLE_CATEGORIES: dict[str, tuple[str, str, str]] = {
    "wearables.connections": ("connections", "Connections", "connections"),
    "wearables.summary.activity": ("activitySummary", "Activity Summary", "summary.activity"),
    "wearables.summary.sleep": ("sleepSummary", "Sleep Summary", "summary.sleep"),
    "wearables.summary.body": ("bodySummary", "Body Summary", "summary.body"),
    "wearables.summary.data": ("dataSummary", "Data Summary", "summary.data"),
    "wearables.data_sources": ("dataSources", "Data Sources", "data_sources"),
    "wearables.timeseries.heart_rate": ("heartRate", "Heart Rate Timeseries", "timeseries.heart_rate"),
    "wearables.timeseries.steps": ("steps", "Steps Timeseries", "timeseries.steps"),
    "wearables.events.workouts": ("workouts", "Workouts", "events.workouts"),
    "wearables.events.sleep": ("sleepEvents", "Sleep Events", "events.sleep"),
    "wearables.health_scores": ("healthScores", "Health Scores", "health_scores"),
}


def _wearable_service() -> WearableDataService:
    return WearableDataService(SESSION_DATA)


@router.get("/available", response_model=ContextAvailabilityResponse)
async def available_context() -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    epic_raw = _epic_compacted_raw()
    sources.append(
        {
            "id": "epic",
            "label": "Epic MyChart",
            "connected": epic_raw is not None,
            "categories": _epic_categories(epic_raw or {}),
        }
    )
    sources.append(
        {
            "id": "openWearables",
            "label": "Open Wearables",
            "connected": True,
            "categories": [
                {
                    "id": category_id,
                    "source": "openWearables",
                    "key": response_key,
                    "label": label,
                    "available": True,
                    "recordCount": None,
                }
                for category_id, (response_key, label, _resolver_key) in WEARABLE_CATEGORIES.items()
            ],
        }
    )
    return {"sources": sources}


@router.post("/raw", response_model=RawContextResponse)
async def selected_raw_context(request: RawContextRequest) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    epic_ids = [category_id for category_id in request.categoryIds if category_id.startswith("epic.")]
    wearable_ids = [
        category_id for category_id in request.categoryIds if category_id.startswith("wearables.")
    ]
    unknown_ids = [
        category_id
        for category_id in request.categoryIds
        if not category_id.startswith("epic.") and category_id not in WEARABLE_CATEGORIES
    ]
    unknown_ids.extend(
        category_id for category_id in wearable_ids if category_id not in WEARABLE_CATEGORIES
    )
    if unknown_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown context category: {', '.join(sorted(set(unknown_ids)))}",
        )

    if epic_ids:
        selected["epic"] = _selected_epic_raw(epic_ids)
    if wearable_ids:
        selected["openWearables"] = await _selected_wearable_raw(wearable_ids)

    return {
        "selectedRawContext": selected,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _epic_compacted_raw() -> dict[str, Any] | None:
    raw = SESSION_DATA.get("raw")
    if not isinstance(raw, dict):
        return None
    return compact_epic_raw_for_browser(raw)


def _epic_categories(compacted: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"epic.{key}",
            "source": "epic",
            "key": key,
            "label": _label_from_key(key),
            "available": True,
            "recordCount": _record_count(value),
        }
        for key, value in compacted.items()
    ]


def _selected_epic_raw(category_ids: list[str]) -> dict[str, Any]:
    compacted = _epic_compacted_raw()
    if compacted is None:
        raise HTTPException(status_code=404, detail="No Epic data connected.")
    selected: dict[str, Any] = {}
    for category_id in category_ids:
        key = category_id.removeprefix("epic.")
        if key not in compacted:
            raise HTTPException(status_code=400, detail=f"Unknown context category: {category_id}")
        selected[key] = compacted[key]
    return selected


async def _selected_wearable_raw(category_ids: list[str]) -> dict[str, Any]:
    service = _wearable_service()
    selected: dict[str, Any] = {}
    for category_id in category_ids:
        response_key, _label, resolver_key = WEARABLE_CATEGORIES[category_id]
        selected[response_key] = await _resolve_wearable_category(service, resolver_key)
    return selected


async def _resolve_wearable_category(service: WearableDataService, resolver_key: str) -> Any:
    if resolver_key == "connections":
        return await service.get_connections(DEMO_USER_ID)
    if resolver_key.startswith("summary."):
        return await service.get_summary(DEMO_USER_ID, resolver_key.split(".", 1)[1])
    if resolver_key == "data_sources":
        return await service.get_data_sources(DEMO_USER_ID)
    if resolver_key == "timeseries.heart_rate":
        return await service.get_timeseries(DEMO_USER_ID, {"type": "heart_rate", "limit": 12})
    if resolver_key == "timeseries.steps":
        return await service.get_timeseries(DEMO_USER_ID, {"type": "steps", "limit": 12})
    if resolver_key == "events.workouts":
        return await service.get_workouts(DEMO_USER_ID, {"limit": 5})
    if resolver_key == "events.sleep":
        return await service.get_sleep(DEMO_USER_ID, {"limit": 5})
    if resolver_key == "health_scores":
        return await service.get_health_scores(DEMO_USER_ID, {"limit": 12})
    raise HTTPException(status_code=400, detail=f"Unknown wearable resolver: {resolver_key}")


def _record_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if value is None:
        return 0
    return 1


def _label_from_key(key: str) -> str:
    return key.replace("_", " ").title()
```

- [ ] **Step 3: Register the router**

Modify `backend/main.py` to import and include the new router:

```python
from data_sources.local_ai.routes import router as local_ai_router
```

and include it with the other routers:

```python
app.include_router(local_ai_router)
```

- [ ] **Step 4: Run backend Local AI route tests**

Run:

```bash
cd /Users/tobi/WholeYou/backend
python -m unittest tests.test_local_ai_context_routes -v
```

Expected: all tests pass.

- [ ] **Step 5: Run related backend tests**

Run:

```bash
cd /Users/tobi/WholeYou/backend
python -m unittest tests.test_epic_routes tests.test_wearable_routes tests.test_local_ai_context_routes -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit backend route work**

Run:

```bash
cd /Users/tobi/WholeYou
git add backend/data_sources/local_ai backend/main.py backend/tests/test_local_ai_context_routes.py
git commit -m "feat: add local ai context catalog api"
```

---

### Task 3: Frontend API Types And Tests

**Files:**
- Modify: `frontend/src/api.ts`
- Test: use TypeScript build and existing Vitest suite.

- [ ] **Step 1: Add Local AI context types and helpers**

Modify `frontend/src/api.ts` near the existing Local AI relevant API helpers:

```ts
export type LocalAiContextCategory = {
  id: string;
  source: "epic" | "openWearables" | string;
  key: string;
  label: string;
  available: boolean;
  recordCount?: number | null;
};

export type LocalAiContextSource = {
  id: "epic" | "openWearables" | string;
  label: string;
  connected: boolean;
  categories: LocalAiContextCategory[];
};

export type LocalAiContextAvailability = {
  sources: LocalAiContextSource[];
};

export type LocalAiSelectedRawContext = {
  selectedRawContext: {
    epic?: unknown;
    openWearables?: unknown;
  };
  generatedAt: string;
};

export async function getLocalAiContextAvailability(): Promise<LocalAiContextAvailability> {
  return getJson<LocalAiContextAvailability>("/api/local-ai/context/available");
}

export async function getLocalAiSelectedRawContext(
  categoryIds: string[]
): Promise<LocalAiSelectedRawContext> {
  return postJson<LocalAiSelectedRawContext>("/api/local-ai/context/raw", { categoryIds });
}
```

- [ ] **Step 2: Run frontend type/test check**

Run:

```bash
cd /Users/tobi/WholeYou/frontend
npm test -- --run
```

Expected: existing tests pass or fail only because the Local AI panel has not yet been migrated.

---

### Task 4: Replace Local AI Raw JSON Tree With Category Metadata

**Files:**
- Modify: `frontend/src/components/local-llm/LocalLlmPanel.tsx`
- Modify: `frontend/src/api.ts`
- Optionally delete: `frontend/src/components/local-llm/JsonContextChecklist.tsx`
- Optionally delete: `frontend/src/lib/local-llm/jsonSelection.ts`
- Optionally delete: `frontend/src/lib/local-llm/jsonSelection.test.ts`

- [ ] **Step 1: Replace imports and state in `LocalLlmPanel`**

Remove these imports:

```ts
import { getEpicRaw, getWearablesPageData } from "../../api";
import {
  buildSelectedJson,
  createSelectionForJson,
} from "../../lib/local-llm/jsonSelection";
import { JsonContextChecklist } from "./JsonContextChecklist";
```

Add these imports:

```ts
import {
  getLocalAiContextAvailability,
  getLocalAiSelectedRawContext,
  LocalAiContextAvailability,
} from "../../api";
```

Replace raw-data state:

```ts
const [epicData, setEpicData] = useState<Record<string, unknown> | null>(null);
const [wearablesData, setWearablesData] = useState<Record<string, unknown> | null>(null);
const [selectedEpicPaths, setSelectedEpicPaths] = useState<Set<string>>(new Set());
const [selectedWearablePaths, setSelectedWearablePaths] = useState<Set<string>>(new Set());
```

with metadata-only state:

```ts
const [contextAvailability, setContextAvailability] =
  useState<LocalAiContextAvailability | null>(null);
const [selectedCategoryIds, setSelectedCategoryIds] = useState<Set<string>>(new Set());
```

- [ ] **Step 2: Replace context loading**

Replace `loadContextData()` with:

```ts
async function loadContextData() {
  setContextLoading(true);
  setContextStatus("Loading available Epic and Open Wearables categories");

  try {
    const availability = await getLocalAiContextAvailability();
    setContextAvailability(availability);
    setSelectedCategoryIds(new Set());
    setContextStatus("Loaded available context categories. Select what to attach.");
  } catch (err) {
    setContextStatus(err instanceof Error ? err.message : "Failed to load context categories.");
  } finally {
    setContextLoading(false);
  }
}
```

- [ ] **Step 3: Replace context packet resolution with transient raw fetch**

Replace `resolveContextPacket()` with:

```ts
async function resolveContextPacket(): Promise<WholeYouContextPacket | undefined> {
  if (selectedCategoryIds.size === 0) {
    setContextStatus("No Epic or Open Wearables categories selected. Generating without context.");
    return undefined;
  }

  const selected = await getLocalAiSelectedRawContext([...selectedCategoryIds]);
  setContextStatus("Selected raw context fetched for this local generation only.");
  return {
    selectedRawContext: selected.selectedRawContext,
    generatedAt: selected.generatedAt,
  };
}
```

- [ ] **Step 4: Clear transient raw context references in `handleGenerate`**

Replace `handleGenerate()` with this structure:

```ts
async function handleGenerate() {
  if (!canGenerate) return;

  let contextPacket: WholeYouContextPacket | undefined;

  try {
    setResponse("");
    contextPacket = await resolveContextPacket();
    const output = await generate({
      userPrompt: prompt,
      contextPacket,
      onToken: (token) => {
        setResponse((current) => `${current}${token}`);
      },
    });
    setResponse((current) => current || output.text);
  } catch {
    // The hook exposes the user-facing error state.
  } finally {
    contextPacket = undefined;
  }
}
```

- [ ] **Step 5: Replace JSON tree JSX with flat category checklist**

Replace the `<div className="jsonContextGrid">...</div>` block with:

```tsx
<div className="contextCategoryList">
  {contextAvailability ? (
    contextAvailability.sources.map((source) => (
      <section className="contextCategoryGroup" key={source.id}>
        <div className="contextCategoryGroupHeader">
          <h3>{source.label}</h3>
          <span className="jsonChecklistMeta">
            {source.connected ? `${source.categories.length} categories` : "Not connected"}
          </span>
        </div>
        {source.connected && source.categories.length > 0 ? (
          <div className="contextCategoryOptions">
            {source.categories.map((category) => (
              <label className="contextCategoryOption" key={category.id}>
                <input
                  type="checkbox"
                  checked={selectedCategoryIds.has(category.id)}
                  disabled={!category.available}
                  onChange={(event) => {
                    setSelectedCategoryIds((current) => {
                      const next = new Set(current);
                      if (event.target.checked) {
                        next.add(category.id);
                      } else {
                        next.delete(category.id);
                      }
                      return next;
                    });
                  }}
                />
                <span>{category.label}</span>
                {typeof category.recordCount === "number" && (
                  <span className="jsonChecklistMeta">{category.recordCount}</span>
                )}
              </label>
            ))}
          </div>
        ) : (
          <p className="empty">No categories available.</p>
        )}
      </section>
    ))
  ) : (
    <div className="jsonContextPanel">
      <h3>Available context</h3>
      <p className="empty">Load available categories to choose Local AI context.</p>
    </div>
  )}
</div>
```

- [ ] **Step 6: Update button/status copy**

Change the context button text from:

```tsx
{contextLoading ? "Loading context" : "Load Epic and Open Wearables JSON"}
```

to:

```tsx
{contextLoading ? "Loading categories" : "Show available data"}
```

Change explanatory text to avoid claiming raw JSON is already attached:

```tsx
<p className="note">
  Select categories to fetch from the backend only when you generate locally.
</p>
```

- [ ] **Step 7: Remove unused JSON tree files if no references remain**

Run:

```bash
cd /Users/tobi/WholeYou
rg "JsonContextChecklist|jsonSelection"
```

If only the component/test files reference themselves, delete:

```bash
rm frontend/src/components/local-llm/JsonContextChecklist.tsx
rm frontend/src/lib/local-llm/jsonSelection.ts
rm frontend/src/lib/local-llm/jsonSelection.test.ts
```

If tests are useful as historical coverage, leave them until a later cleanup. Do not leave broken imports.

- [ ] **Step 8: Run frontend tests**

Run:

```bash
cd /Users/tobi/WholeYou/frontend
npm test -- --run
```

Expected: all frontend tests pass.

- [ ] **Step 9: Commit frontend migration**

Run:

```bash
cd /Users/tobi/WholeYou
git add frontend/src/api.ts frontend/src/components/local-llm frontend/src/lib/local-llm
git commit -m "feat: fetch local ai context on demand"
```

---

### Task 5: End-To-End Verification

**Files:**
- No planned source changes unless verification finds a bug.

- [ ] **Step 1: Run backend route tests**

Run:

```bash
cd /Users/tobi/WholeYou/backend
python -m unittest tests.test_local_ai_context_routes tests.test_epic_routes tests.test_wearable_routes -v
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd /Users/tobi/WholeYou/frontend
npm test -- --run
```

Expected: all tests pass.

- [ ] **Step 3: Start backend**

Run:

```bash
cd /Users/tobi/WholeYou/backend
uvicorn main:app --reload --port 8000
```

Expected: server starts on `http://127.0.0.1:8000`.

- [ ] **Step 4: Start frontend**

Run:

```bash
cd /Users/tobi/WholeYou/frontend
npm run dev -- --host localhost --port 3000
```

Expected: Vite starts on `http://localhost:3000`.

- [ ] **Step 5: Verify Local AI page does not fetch full raw data on category load**

Open `http://localhost:3000/local-ai` in the in-app browser.

Actions:

1. Click **Show available data**.
2. Confirm the page shows category names.
3. Confirm the browser Network panel or backend logs show `GET /api/local-ai/context/available`.
4. Confirm there is no Local AI request to `/api/epic/raw`.
5. Confirm there is no Local AI burst of `/api/wearables/summary/*`, `/api/wearables/timeseries`, `/api/wearables/events/*`, or `/api/wearables/health-scores` until generation.

- [ ] **Step 6: Verify selected raw context is fetched only on generation**

Actions:

1. Select only `Patient`.
2. Click **Generate locally**.
3. Confirm backend logs show `POST /api/local-ai/context/raw`.
4. Confirm the request body includes only `["epic.patient"]`.
5. Confirm no recursive JSON tree is rendered.

- [ ] **Step 7: Final status check**

Run:

```bash
cd /Users/tobi/WholeYou
git status --short
```

Expected: only intentional files changed, no generated cache files staged.

---

## Self-Review

Spec coverage:

- Metadata-only availability endpoint: Task 1 and Task 2.
- Selected raw fetch endpoint: Task 1 and Task 2.
- Backend remains data owner: Task 2.
- Local AI stores only metadata: Task 4.
- Transient raw context cleared after generation: Task 4 Step 4.
- No recursive tree: Task 4 Step 5 and Step 7.
- Tests: Tasks 1, 2, 3, 4, and 5.

Placeholder scan:

- No incomplete markers, vague edge handling, or unspecified test steps remain.

Type consistency:

- API response uses `selectedRawContext`, matching `WholeYouContextPacket`.
- Frontend selected IDs are `Set<string>` and request payload uses `categoryIds: string[]`.
