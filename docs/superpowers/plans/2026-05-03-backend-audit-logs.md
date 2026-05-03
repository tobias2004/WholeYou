# Backend Audit Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Logs tab backed by backend in-memory audit entries that record action/data-access metadata without storing raw health payloads.

**Architecture:** Add a small backend audit store and logs API, then instrument AI/local-context/wearable/Epic paths where data access happens. Add frontend API helpers, a `/logs` page, and navigation using the existing Vite/React single-file routing pattern.

**Tech Stack:** FastAPI, Pydantic, `SESSION_DATA` in-memory storage, Python `unittest`, React 19, TypeScript, Vitest.

---

## File Structure

- Create `backend/audit_logs.py`: in-memory append/list/clear helpers, sanitization, and data-access metadata helpers.
- Create `backend/logs/routes.py`: `GET /api/logs` and `DELETE /api/logs`.
- Modify `backend/main.py`: include logs router.
- Modify `backend/data_sources/ai/routes.py`: log chat lifecycle, tool calls, translation, rerank, and selected data access.
- Modify `backend/data_sources/local_ai/routes.py`: log availability and raw context/document fetches.
- Modify `backend/data_sources/wearables/routes.py`: log provider connect, clear, import, health score compute actions where routes exist.
- Modify `backend/integrations/epic/routes.py`: log account link/logout/callback/data actions where routes exist.
- Create `backend/tests/test_audit_logs.py`: audit store and API tests.
- Modify `backend/tests/test_ai_routes.py`: add AI log assertions.
- Modify `backend/tests/test_local_ai_context_routes.py`: add local context log assertions.
- Modify `frontend/src/api.ts`: add log types and helpers.
- Modify `frontend/src/api.test.ts`: add helper tests.
- Modify `frontend/src/App.tsx`: add `/logs` route and `LogsPage`.
- Modify `frontend/src/components/Header.tsx`: add Logs nav link.
- Modify `frontend/src/styles.css`: add logs page styles.

## Task 1: Backend Audit Store and API

- [ ] Write failing tests in `backend/tests/test_audit_logs.py` for append/list sanitization, max length, `GET /api/logs`, and `DELETE /api/logs`.
- [ ] Run `PYTHONPATH=backend python -m unittest backend.tests.test_audit_logs -v` and confirm it fails because audit module/routes do not exist.
- [ ] Create `backend/audit_logs.py` with `append_log`, `list_logs`, `clear_logs`, sanitized detail handling, and max log length.
- [ ] Create `backend/logs/routes.py` and include it from `backend/main.py`.
- [ ] Run `PYTHONPATH=backend python -m unittest backend.tests.test_audit_logs -v` and confirm it passes.

## Task 2: Backend Instrumentation

- [ ] Add failing tests to `backend/tests/test_ai_routes.py` and `backend/tests/test_local_ai_context_routes.py` asserting AI chat/tool calls and local context fetches append safe log entries without raw prompt or payload text.
- [ ] Run `PYTHONPATH=backend python -m unittest backend.tests.test_ai_routes backend.tests.test_local_ai_context_routes -v` and confirm the new assertions fail.
- [ ] Instrument `backend/data_sources/ai/routes.py` and `backend/data_sources/local_ai/routes.py` with audit log calls.
- [ ] Inspect `backend/data_sources/wearables/routes.py` and `backend/integrations/epic/routes.py`; add focused logging to account/data connection actions using existing route boundaries.
- [ ] Run `PYTHONPATH=backend python -m unittest backend.tests.test_ai_routes backend.tests.test_local_ai_context_routes -v` and confirm it passes.

## Task 3: Frontend Logs API and Page

- [ ] Add failing Vitest cases in `frontend/src/api.test.ts` for `getAuditLogs` and `clearAuditLogs`.
- [ ] Run `npm test -- --run frontend/src/api.test.ts` from `frontend` and confirm the new tests fail.
- [ ] Add audit log types and API helpers in `frontend/src/api.ts`.
- [ ] Add `/logs` route, `LogsPage`, and Header navigation.
- [ ] Add scoped CSS for the Logs page.
- [ ] Run `npm test -- --run frontend/src/api.test.ts` from `frontend` and confirm it passes.

## Task 4: Verification

- [ ] Run backend focused tests: `PYTHONPATH=backend python -m unittest backend.tests.test_audit_logs backend.tests.test_ai_routes backend.tests.test_local_ai_context_routes -v`.
- [ ] Run frontend tests: `cd frontend && npm test -- --run src/api.test.ts`.
- [ ] Run frontend build: `cd frontend && npm run build`.
- [ ] Review `git diff` for raw prompt/image/answer/token/payload logging mistakes.
