# Availability-Only Data Pages Design

## Goal

Prevent the Dashboard and Wearables pages from loading full clinical or wearable payloads into browser memory. These pages should show what data is present, not the data itself.

## Current Problem

The Local AI page now uses metadata-first context selection, but two other pages still fetch source data into React state:

- `/dashboard` calls `getEpicRaw()` and renders the raw Epic FHIR JSON tree.
- `/wearables` calls `getWearablesPageData()` and stores summaries, timeseries, workouts, sleep events, and health scores in page state.

Opening those pages still duplicates backend-held health data in frontend memory.

## Requirements

- `/dashboard` must not call `/api/epic/raw` on page load.
- `/dashboard` must not store full Epic raw data in React state.
- `/dashboard` must display only Epic availability metadata: category labels, availability, and record counts when available.
- `/wearables` must not call `getWearablesPageData()` on page load.
- `/wearables` must not store wearable summaries, timeseries, workouts, sleep events, or health scores in React state.
- `/wearables` must display only Open Wearables availability metadata: category labels, availability, and counts when available.
- Wearable actions should remain available: provider connection, clear connections, Apple Health XML import, and health score computation.
- After wearable actions, the page should refresh availability metadata only.
- Raw JSON display and raw copying should be removed from the default UI.
- Existing raw endpoints may remain for backend/debug use, but normal app pages should not call them.
- The backend remains the owner of full data until a selected raw context request is made for Local AI generation.

## API Design

Reuse the existing Local AI context availability endpoint:

`GET /api/local-ai/context/available`

The frontend should derive page-specific views from this response:

- Dashboard uses the source with `id === "epic"`.
- Wearables uses the source with `id === "openWearables"`.

No new backend endpoint is required for this change.

## Frontend Design

Add a small metadata view helper for source categories if useful, but keep it lightweight. It should render flat category rows/cards with:

- Label
- Available/unavailable status
- Record count when present

Dashboard:

- Replace `epicRaw` state with `LocalAiContextAvailability | null` or an Epic source object.
- Replace `getEpicRaw()` call with `getLocalAiContextAvailability()`.
- Replace raw JSON tree with an Epic category availability list.
- Keep `ConnectMyChart`.

Wearables:

- Replace `WearablesPageData | null` state with `LocalAiContextAvailability | null`.
- Replace `loadWearablesPage()` / `getWearablesPageData()` with `getLocalAiContextAvailability()`.
- Render Open Wearables category availability instead of summaries/timeseries/events.
- Keep provider/action controls.
- After connect, clear, import, or compute actions, call the metadata refresh function.

## Error Handling

- If availability fetch fails, show the existing state panel error pattern.
- If Epic is disconnected, Dashboard should say no Epic/MyChart data is connected.
- If Open Wearables has no categories or is unavailable, Wearables should say no wearable data categories are available.
- Wearable action failures should continue to show through `actionStatus`.

## Testing

Frontend tests should verify:

- Dashboard no longer imports or calls `getEpicRaw()`.
- Wearables no longer imports or calls `getWearablesPageData()`.
- Page code uses `getLocalAiContextAvailability()`.
- No Local AI or data pages reference `JsonContextChecklist` or `jsonSelection`.

Build verification should confirm TypeScript still compiles.

## Out Of Scope

- Removing backend raw endpoints.
- Removing wearable action endpoints.
- Adding developer/debug raw viewers.
- Changing Local AI generation context behavior.
