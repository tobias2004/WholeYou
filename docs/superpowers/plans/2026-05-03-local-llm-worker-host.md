# Local LLM Worker Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Host the browser-local Gemma runtime in a dedicated Web Worker instead of the React renderer.

**Architecture:** Add a worker entrypoint that owns `LocalLlmClient`, and a main-thread proxy that exposes load/generate/unload/reset state methods. `useLocalLlm` swaps from the in-page singleton to the worker proxy while preserving the panel API.

**Tech Stack:** React, TypeScript, Vite Web Workers, Transformers.js.

---

### Task 1: Worker Message Protocol

**Files:**
- Create `frontend/src/lib/local-llm/localLlmWorkerProtocol.ts`

- [ ] Define request/response message types for `load`, `generate`, `unload`, `resetError`, `state`, `token`, `result`, and `error`.
- [ ] Include request IDs so load/generate/unload promises resolve or reject correctly.

### Task 2: Worker Host

**Files:**
- Create `frontend/src/lib/local-llm/localLlm.worker.ts`

- [ ] Instantiate `LocalLlmClient` inside the worker.
- [ ] Handle `load`, `generate`, `unload`, `resetError`, and `getState` messages.
- [ ] For generation, forward streamed tokens with `token` messages.
- [ ] After unload, close worker-side state by calling `client.unload()`.

### Task 3: Main-Thread Worker Proxy

**Files:**
- Create `frontend/src/lib/local-llm/localLlmWorkerClient.ts`
- Create `frontend/src/lib/local-llm/localLlmWorkerClient.test.ts`

- [ ] Write tests for state updates, token callbacks, operation result resolution, and error rejection.
- [ ] Implement a proxy class with `load`, `generate`, `unload`, `resetError`, `getState`, and `subscribe`.
- [ ] Lazily create the worker on first use.
- [ ] Terminate the worker after successful unload so the next load starts fresh.

### Task 4: Hook Integration

**Files:**
- Modify `frontend/src/hooks/useLocalLlm.ts`

- [ ] Replace the direct `LocalLlmClient` singleton with `LocalLlmWorkerClient`.
- [ ] Subscribe to worker state changes and update React state.
- [ ] Preserve `loadModel`, `generate`, `unloadModel`, and `resetError` behavior.

### Task 5: Verification

**Commands:**
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

- [ ] Confirm `LocalLlmClient` tests still pass.
- [ ] Confirm worker proxy tests pass.
- [ ] Confirm Vite builds the worker.
- [ ] Confirm `/local-ai` still returns 200 from the dev server.

## Self-Review

Spec coverage:

- Worker owns model runtime: Tasks 2 and 4.
- Streaming preserved: Tasks 2 and 3.
- Cleanup preserved: existing `LocalLlmClient` cleanup plus Task 2 unload and Task 3 termination.
- Main-thread UI API preserved: Task 4.

No unresolved placeholders remain.
