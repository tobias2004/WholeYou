# Availability-Only Data Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Dashboard and Wearables pages from fetching full health payloads and show only backend availability metadata.

**Architecture:** Reuse `/api/local-ai/context/available` for metadata. Replace Dashboard and Wearables page state with `LocalAiContextAvailability`, render flat category availability lists, and refresh metadata after wearable actions.

**Tech Stack:** React, TypeScript, Vite/Vitest, existing FastAPI metadata endpoint.

---

### Task 1: Remove Page-Level Raw Data Fetches

**Files:**
- Modify: `/Users/tobi/WholeYou/frontend/src/App.tsx`
- Modify: `/Users/tobi/WholeYou/frontend/src/api.ts` only if imports/types need cleanup.

- [ ] Replace `getEpicRaw` and `getWearablesPageData` imports in `App.tsx` with `getLocalAiContextAvailability` and `LocalAiContextAvailability`.
- [ ] Replace Dashboard `epicRaw` state with availability metadata.
- [ ] Replace Wearables `WearablesPageData` state with availability metadata.
- [ ] Remove `loadWearablesPage()` and call the metadata endpoint directly.

### Task 2: Render Availability Lists Only

**Files:**
- Modify: `/Users/tobi/WholeYou/frontend/src/App.tsx`

- [ ] Add helpers to find sources by `id === "epic"` and `id === "openWearables"`.
- [ ] Add a reusable category availability list component.
- [ ] Dashboard shows only Epic category labels/status/counts and no `JsonTree`.
- [ ] Wearables shows only Open Wearables category labels/status/counts while preserving connect/import/compute/clear controls.
- [ ] After wearable actions, refresh metadata only.

### Task 3: Verify No Raw Data Page Loads

**Files:**
- Modify tests only if an existing test needs updating.

- [ ] Run `rg -n "getEpicRaw|getWearablesPageData|JsonTree|copyJson" frontend/src/App.tsx`.
- [ ] Expected: no matches for `getEpicRaw`, `getWearablesPageData`, `JsonTree`, or `copyJson` in `App.tsx`.
- [ ] Run `npm test -- --run`.
- [ ] Run `npm run build`.
- [ ] Use the running app to confirm `/dashboard` and `/wearables` return HTTP 200.

## Self-Review

Spec coverage:

- Dashboard no longer loads raw Epic data: Task 1 and Task 3.
- Wearables no longer loads all wearable data: Task 1 and Task 3.
- Pages display only availability metadata: Task 2.
- Wearable actions remain and refresh metadata: Task 2.
- Backend raw endpoints are left intact: no backend changes planned.

No incomplete markers or unresolved placeholders remain.
