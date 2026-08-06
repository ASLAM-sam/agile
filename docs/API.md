# API Reference

Base path: `/api/v1` · Interactive docs: `/docs` · OpenAPI schema: `/openapi.json`

All endpoints except `/health` and `/catalog` require a bearer token:

```
Authorization: Bearer <access_token>
```

## Error format

Every failure returns the same shape:

```json
{
  "error": "validation_error",
  "message": "The selected technology stack is not valid.",
  "details": { "problems": ["FastAPI does not support mongodb."] }
}
```

| Status | `error` | Meaning |
|---|---|---|
| 401 | `authentication_failed` | Missing, invalid or expired token |
| 403 | `forbidden` | Authenticated but not permitted |
| 404 | `not_found` | Absent, or owned by someone else |
| 409 | `conflict` | Duplicate resource |
| 422 | `validation_error` | Payload or state failed validation |
| 429 | `rate_limited` | Concurrent-run limit reached |
| 502 | `llm_error` | Model provider failed after retries |
| 503 | `configuration_error` | `ANTHROPIC_API_KEY` not configured |

---

## System

### `GET /health`

Liveness plus the dependencies the service actually needs.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "development",
  "database": "connected",
  "llm_configured": true,
  "active_runs": 1
}
```

### `GET /catalog`

Every registered technology and the agent roster. Drives the stack-selection UI,
so a newly registered adapter appears with no frontend change.

```json
{
  "frontend": [{ "key": "react", "display_name": "React", "version": "18.3", "...": "..." }],
  "backend":  [{ "key": "fastapi", "...": "..." }],
  "database": [{ "key": "postgresql", "...": "..." }],
  "agents":   [{ "role": "manager", "display_name": "Manager", "...": "..." }]
}
```

### `GET /catalog/agents`

The team roster alone.

---

## Authentication

### `POST /auth/register` → `201`

```json
{ "email": "you@company.com", "full_name": "Ada Lovelace", "password": "…" }
```

Passwords must be at least 10 characters and combine letters with numbers or
symbols. Returns the user and a token pair.

### `POST /auth/login` → `200`

```json
{ "email": "you@company.com", "password": "…" }
```

An unknown address and a wrong password return the identical error, and take
comparable time — the response does not reveal whether an address is registered.

### `POST /auth/refresh` → `200`

```json
{ "refresh_token": "…" }
```

Returns a new pair. An access token presented here is rejected: token type is
enforced.

### `GET /auth/me` · `PATCH /auth/me`

Read or update the current profile (`full_name`, `theme_preference`).

---

## Projects

### `POST /projects` → `201`

```json
{ "idea": "A hospital management system for appointments and records", "tags": ["health"] }
```

`idea` must be at least 10 characters. `name` is optional — the Manager agent
assigns a considered one during the run.

### `GET /projects` → `200`

Query: `search`, `limit` (1–100, default 25), `offset`.

```json
{ "items": [...], "total": 12, "limit": 25, "offset": 0 }
```

### `GET /projects/stats` → `200`

Dashboard counters for the caller.

### `GET /projects/{id}` · `PATCH /projects/{id}` · `DELETE /projects/{id}`

Deleting a project cascades to its runs, artifacts and events.

### `GET /projects/{id}/runs` → `200`

Every run for the project, newest first.

---

## Generation

### `POST /projects/{id}/analyze` → `200`

Runs requirement analysis and returns a ranked technology recommendation.
Cached on the project — reopening the review screen does not re-bill it.

```json
{
  "project_id": "…",
  "analysis": {
    "executive_summary": "…",
    "functional_requirements": [...],
    "capabilities": {
      "needs_authentication": true,
      "needs_database": true,
      "needs_api": true,
      "needs_backend": true,
      "needs_frontend": true
    },
    "complexity": "advanced",
    "rationale": "Staff roles differ and records must persist between sessions."
  },
  "recommended_stack": { "frontend": "react", "backend": "fastapi", "database": "postgresql" },
  "options": {
    "frontend": [
      { "key": "react", "display_name": "React", "score": 9.0,
        "reasons": ["Component model suits data-dense interactive dashboards"] }
    ]
  },
  "workflow_preview": [
    { "role": "database_engineer", "display_name": "Database Engineer",
      "sequence": 3, "status": "waiting", "skip_reason": "" }
  ]
}
```

`workflow_preview` is the plan the user sees before committing: agents this
project does not need arrive already marked `skipped`, with the reason.

Returns `503` when `ANTHROPIC_API_KEY` is not configured.

### `POST /projects/{id}/runs` → `202`

Queues a run and launches it in the background.

```json
{ "tech_stack": { "frontend": "nextjs", "backend": "fastapi", "database": "postgresql" } }
```

Omit `tech_stack` to accept the recommendation. Any omitted layer falls back to
the recommended value, and a layer the analysis marked unnecessary is dropped
regardless of what is sent.

- `422` if the project has not been analysed, or the stack is invalid
- `429` if `MAX_CONCURRENT_RUNS` is already in flight

### `GET /runs` → `200`

Recent runs across all the caller's projects. Query: `limit` (1–100).

### `GET /runs/{id}` → `200`

Full execution state: status, progress, per-agent detail, plan, report and
token usage.

### `GET /runs/{id}/events` → `200`

Persisted timeline. Query: `after` (sequence), `limit` (1–2000).

### `GET /runs/{id}/files` → `200`

File manifest for a finished run — path, description, producing agent, size,
line count.

### `POST /runs/{id}/cancel` → `200`

Requests cancellation. A run already in a terminal state responds saying so.

### `GET /runs/{id}/stream` — Server-Sent Events

Live event stream. Query: `after` (sequence to replay from, default 0).

History is replayed first, then live events are tailed, so a client that
connects late or reconnects after a drop sees the complete timeline with no gap.
Events already replayed are suppressed by sequence number.

```
event: agent.started
data: {"sequence":12,"type":"agent.started","agent":"backend_engineer","message":"Backend Engineer started","timestamp":"…"}

event: agent.progress
data: {"sequence":13,"type":"agent.progress","agent":"backend_engineer","payload":{"progress":45},"message":"Writing files 2/4"}

: heartbeat

event: stream.end
data: {"reason":"run.completed"}
```

| Event | Meaning |
|---|---|
| `run.started` · `run.phase` · `run.completed` · `run.failed` · `run.cancelled` | Run lifecycle |
| `agent.started` · `agent.progress` · `agent.log` | Agent activity |
| `agent.completed` · `agent.skipped` · `agent.failed` | Agent outcome |
| `artifact.created` | Deliverables recorded |
| `stream.end` | No further events; close the connection |

A comment frame (`: heartbeat`) is sent every 20 seconds of silence to survive
proxies that close quiet connections.

> The client consumes this with `fetch` + `ReadableStream` rather than
> `EventSource`, because `EventSource` cannot send an `Authorization` header.

---

## Artifacts

### `GET /runs/{id}/artifacts` → `200`

Query: `kind` — `requirements`, `architecture`, `database`, `api_spec`,
`frontend_code`, `backend_code`, `tests`, `documentation`, `devops`, `report`,
`package`.

### `GET /artifacts/{id}` → `200`

One artifact including its inline content.

### `GET /runs/{id}/download` → `200`

Streams the generated project as a ZIP (`application/zip`).

The stored path is re-validated against the artifact root before the file is
opened, so a tampered database row cannot be used to read arbitrary files.
Returns `404` if the run has not been packaged.
