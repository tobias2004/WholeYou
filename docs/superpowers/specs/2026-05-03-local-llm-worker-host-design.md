# Local LLM Worker Host Design

## Goal

Move the browser-local Gemma runtime out of the React page and into a dedicated Web Worker so the visible app no longer directly owns model, processor, tokenization, generation tensors, or WebGPU runtime objects.

## Current Problem

The Local AI page currently creates a singleton `LocalLlmClient` in the main browser thread. That client loads the Gemma model, tokenizes prompts, runs generation, streams tokens, and disposes tensors from the same renderer that also runs React UI state.

This is different from public browser implementations that commonly isolate the model in a worker, background script, or offscreen host. The current shape increases renderer memory pressure and makes cleanup dependent on the lifetime of the React page.

## Requirements

- The main React page must not directly load `Gemma4ForConditionalGeneration` or `AutoProcessor`.
- A dedicated Web Worker must own model loading, generation, tensor cleanup, model disposal, and runtime state.
- The existing Local AI UI should keep the same user-facing behavior: load, generate, stream tokens, unload, and clear errors.
- The worker must stream generated tokens back to the UI.
- The worker must explicitly dispose generation inputs/outputs after each generation.
- The worker must call `model.dispose()` on unload.
- The main-thread client should be able to terminate and recreate the worker after unload to strengthen cleanup boundaries.
- The existing fallback device behavior can remain for now, but worker-owned load failures must not leave a second live model reference.
- The implementation should preserve the current prompt-building behavior and selected context behavior.

## Architecture

Create a worker-hosted Local LLM runtime:

- `localLlm.worker.ts`: worker entrypoint. Owns a `LocalLlmClient` instance and handles messages.
- `localLlmWorkerClient.ts`: main-thread proxy with the same high-level methods as the current client: `load`, `generate`, `unload`, `resetError`, `getState`.
- `useLocalLlm.ts`: uses the worker proxy instead of a main-thread singleton `LocalLlmClient`.

Message protocol:

- Main to worker:
  - `load`
  - `generate`
  - `unload`
  - `resetError`
  - `getState`
- Worker to main:
  - `state`
  - `token`
  - `result`
  - `error`

The worker should create token streamer callbacks inside the worker and forward token strings to the main thread. The main thread should only append token text and handle final results.

## Cleanup

Generation cleanup:

- Dispose generated-token slice when distinct from output tensor.
- Dispose output tensor.
- Dispose every disposable tensor in tokenized inputs.

Unload cleanup:

- Await `model.dispose()`.
- Clear worker-side model references.
- Send idle state to main thread.
- Main-thread proxy may terminate the worker after unload and lazily create a new worker on next load.

## Error Handling

- Worker errors should be serialized into message strings.
- Main-thread proxy should reject the corresponding operation promise.
- State should move to `error` for failed load or generation.
- `resetError` should clear worker state error and notify the UI.

## Testing

Unit tests should cover:

- Worker proxy routes `token` messages to the current generation callback.
- Worker proxy rejects the correct pending request on `error`.
- Worker proxy updates state from `state` messages.
- Existing `LocalLlmClient` tensor cleanup tests remain green.

Build verification must confirm Vite can bundle the worker.

## Out Of Scope

- Changing model dtype or model ID.
- Replacing Transformers.js pipeline/model class.
- Measuring memory automatically in tests.
- Browser-extension offscreen documents.
- Prompt/token budget changes.
