# Backend Audit Logs Design

## Goal

Add a Logs tab that shows what WholeYou accessed and which backend, LLM, MyChart/Epic, Open Wearables, and related actions occurred. Logs must be retained in backend memory only. They must not store raw health data, prompts, images, LLM responses, OAuth tokens, or full tool results.

## Requirements

- Keep logs in backend process memory, using the same local MVP storage boundary as the current session data.
- Expose a Logs page from the frontend primary navigation.
- Show communication and access events for:
  - user AI queries
  - backend API requests that access MyChart/Epic, Open Wearables, local AI context, or AI generation
  - LLM tool calls
  - account linking and wearable connection actions
  - wearable import and health score compute actions
  - translation, rerank, and medical RAG calls
- Record exactly what categories, documents, skills, and tool names were used or requested.
- Record metadata about data access, not the data payload itself.
- Include enough status information to tell whether an action started, succeeded, or failed.
- Provide a clear logs action for deleting the in-memory log history.

## Non-Goals

- Persistent audit storage across backend restarts.
- Production compliance-grade audit logging.
- Storing raw MyChart/Epic payloads, wearable records, document text, uploaded images, user prompts, generated answers, OAuth tokens, API keys, or full external-service responses.
- Multi-user log isolation beyond the current local MVP backend session model.

## Log Entry Model

Each log entry should be a structured object:

```json
{
  "id": "log_...",
  "timestamp": "2026-05-03T00:00:00+00:00",
  "system": "ai",
  "action": "llm_tool_call",
  "status": "succeeded",
  "summary": "Nemotron called mychart_data.",
  "dataAccessed": [
    {
      "source": "epic",
      "categoryId": "epic.observations_labs",
      "categoryLabel": "Observations Labs",
      "recordCount": 12
    }
  ],
  "details": {
    "toolName": "mychart_data",
    "mode": "get",
    "selectedSkillIds": ["mychart_data"]
  }
}
```

Allowed fields:

- `id`: backend-generated opaque ID.
- `timestamp`: UTC ISO timestamp.
- `system`: `frontend`, `backend`, `ai`, `llm`, `epic`, `openWearables`, `nvidia`, or `medicalRag`.
- `action`: a stable action name such as `user_query`, `api_context_fetch`, `llm_tool_call`, `account_link`, `wearable_import`, or `rerank`.
- `status`: `started`, `succeeded`, or `failed`.
- `summary`: human-readable short text without sensitive payloads.
- `dataAccessed`: source/category/document metadata only.
- `details`: sanitized primitive metadata such as endpoint path, tool name, selected skill IDs, selected category IDs, document IDs, content types, prompt length, image attached boolean, topN, provider ID, mode, and error message.

Forbidden fields:

- raw prompt text
- image data URLs
- clinical or wearable record payloads
- document body text
- generated LLM answer text
- OAuth tokens, authorization codes, API keys, refresh tokens, or full callback URLs
- full tool results

## Backend Design

Add a focused audit module, for example `backend/audit_logs.py`, that owns:

- `append_log(entry)`
- `list_logs()`
- `clear_logs()`
- helpers for category/document metadata and sanitizing details

Store entries in `SESSION_DATA["auditLogs"]` or an equivalent backend-memory container. Use a fixed maximum length, such as 500 entries, to prevent unbounded growth.

Add a route module, for example `backend/logs/routes.py`:

- `GET /api/logs` returns logs newest-first or oldest-first with a documented order.
- `DELETE /api/logs` clears the in-memory log list and returns a count.

Wire this router into `backend/main.py`.

Instrument existing backend paths where the action actually happens:

- AI chat request start/success/failure.
- AI tool execution, including tool name, sanitized arguments, selected categories, selected documents, selected skills, and data-access metadata.
- Translation and rerank calls, recording languages/topN/dataset names but not text or passages.
- Local AI context availability, raw category fetch, and document raw fetch.
- Epic account link/logout/callback paths, recording status and source only.
- Open Wearables provider connect, clear connections, Apple Health XML import, and health score compute actions.

For failed actions, store the sanitized error message when it is safe and useful. Do not store exception objects or response bodies.

## Frontend Design

Add a `/logs` route and a `LogsPage` component.

The Logs tab should include:

- navigation link in `Header`
- refresh button
- clear button
- compact list or table of log entries
- filters for system/action or a simple grouped display if filters are too much for the first pass
- expandable JSON-style sanitized details

The UI should make the privacy boundary obvious through field labels and content, not by showing raw data. Empty state should say no backend activity has been logged yet.

The frontend does not need to create log entries directly for normal backend-backed actions. Backend instrumentation is the source of truth.

## Data Access Metadata

When available, category metadata should include:

- `source`: `epic`, `openWearables`, `medicalRag`, `image`, or `localAi`
- `categoryId`
- `categoryLabel`
- `documentId`
- `contentType`
- `recordCount`

When an LLM tool accesses selected data, the log should say which category IDs were accessed and which tool initiated access. If a tool lists categories, the log should record that it listed metadata rather than fetched raw category values.

## Error Handling

- Logging failures should not break the user-facing action.
- Sanitization should be centralized so unsafe fields are consistently removed.
- Unknown or unsupported log detail values should be converted to safe strings or omitted.
- Clearing logs should not clear connected data or sessions.

## Testing

Backend tests:

- Appending and listing logs preserves sanitized metadata only.
- The log store enforces the maximum entry count.
- `GET /api/logs` returns entries without raw prompt, image, answer, token, or health payload fields.
- `DELETE /api/logs` clears only audit logs.
- AI chat and tool execution append expected audit entries.
- Local AI raw context fetch logs selected categories without storing returned raw payloads.
- Wearable connect/import actions append safe metadata.

Frontend tests:

- Header includes the Logs navigation link.
- Logs page loads and renders backend log entries.
- Clear logs calls the backend and updates the empty state.
- Sanitized details render without assuming raw payload fields exist.

## Acceptance Criteria

- A user can open the Logs tab and see backend-retained in-memory activity.
- AI requests show attached categories, selected documents, selected skills, whether an image was attached, and LLM tool calls.
- MyChart/Epic and Open Wearables actions show which source and data categories were accessed.
- Logs do not contain raw health records, prompt text, image data, generated answers, tokens, or full external responses.
- Restarting the backend clears logs because retention is backend memory only.
