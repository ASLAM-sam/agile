# AgileAgent — Project Status & Database Guide

As of 22 August 2026.

---

# PART 1 — WHAT IS COMPLETE

## Backend platform — DONE

| Area | Status |
|---|---|
| Layered architecture (api → services → repositories → models) | Complete, enforced by tests |
| Authentication (JWT, register, login, refresh) | Complete |
| Project management (create, list, update, delete) | Complete |
| Run lifecycle (queue, execute, cancel, status) | Complete |
| Artifact storage and download | Complete |
| Technology catalogue endpoint | Complete |
| Provider health/dashboard endpoints | Complete |
| Health checks | Complete |
| Production configuration guards | Complete |
| Structured logging | Complete |
| Domain exception handling | Complete |

## The eleven agents — DONE

All eleven implemented with skip rules, prompts and structured output schemas:
Manager, Business Analyst, Solution Architect, Database Engineer, Backend
Engineer, Frontend Engineer, QA Engineer, AI Review Engineer, Code Improvement
Engineer, Documentation Engineer, Artifact Manager.

## Workflow subsystem — DONE

| Component | Status |
|---|---|
| Shared Project Memory (typed state) | Complete |
| Topological planner (`depends_on` / `requires`) | Complete |
| Execution engine with skip decisions | Complete |
| Event bus + Server-Sent Events with replay | Complete |
| Input intent guard | Complete (added 22 Aug 2026) |

## LLM orchestration — DONE

| Component | Status |
|---|---|
| Provider Manager (single gateway) | Complete |
| Six providers: Gemini, Groq, NVIDIA NIM, Ollama, OpenAI, Anthropic | Complete |
| Intelligent routing by task kind | Complete |
| Retry with exponential backoff + jitter | Complete |
| Automatic failover | Complete |
| Provider health monitoring + cooldowns | Complete |
| Prompt cache (content-keyed, LRU + TTL) | Complete |
| Capacity-aware ordering | Complete |
| Failure classification (5 kinds) | Complete |
| NVIDIA NIM integration | Complete (added 21 Aug 2026) |

## Technology adapters — DONE (9 of 9 planned)

- Frontend: React 18, Next.js 15, Angular 18
- Backend: FastAPI, Express.js, Spring Boot 3.4
- Database: PostgreSQL 16, MySQL 8.4, SQLite 3

## Packaging — DONE

Virtual workspace, ZIP builder, Docker Compose generation, manifest generation,
AI Engineering Report. All deterministic — no model involvement.

## Frontend — DONE

10 routed pages, live run streaming over SSE, provider monitoring dashboard,
stack review screen, artifact browser, download. Strict TypeScript, Tailwind,
loading/error/empty states throughout.

## Testing — DONE

- 406 backend tests, all passing
- 43 frontend tests, all passing
- Hermetic: in-memory SQLite, stubbed model, no network access
- Integration suite covers full-stack path, frontend-only path, and both
  failure modes

## Documentation & deliverables — DONE

README, ARCHITECTURE.md, DEVELOPMENT.md, annotated `.env.example`,
12-slide seminar deck, master prompt, viva preparation reference.

---

# PART 2 — WHAT REMAINS

Every item is labelled with its **blast radius** — how much existing code it
touches. Nothing in Tier 1 or Tier 2 modifies working logic.

## TIER 1 — Zero code change (do these first)

### 1.1 Empirical evaluation — HIGHEST PRIORITY
**Blast radius: none. This is measurement, not development.**

You claim seven evaluation metrics and have measured none of them. Generate 5
projects, try to run each, record the result in a table:

```
Projects generated : 5
Ran unmodified     : ?
Needed 1 fix       : ?
Failed to build    : ?
Avg generation time: ?
Avg files produced : ?
```

This converts "we built a system" into "we built and measured a system". It is
the single largest gap in the project and costs one hour.

### 1.2 Fix the rejected Anthropic key
**Blast radius: one line in `backend/.env`.**

`ANTHROPIC_API_KEY` is currently rejected on every call, burning a failover hop
and a 300-second cooldown. Either replace it or add
`LLM_DISABLED_PROVIDERS=anthropic`.

### 1.3 Enable Ollama as a safety net
**Blast radius: one line in `backend/.env`.**

`OLLAMA_ENABLED=true` after `ollama serve`. Gives an unmetered local fallback so
a run can never exhaust every provider.

### 1.4 Tune batch size for stability
**Blast radius: one line in `backend/.env`.**

`GENERATION_BATCH_SIZE=2` produces smaller prompts, so more providers can serve
them and fewer runs fail on capacity. Slower, but far more reliable.

### 1.5 Repository hygiene — SECURITY
**Blast radius: git only, no source changes.**

- `backend/.env.example` has a **real Groq API key committed** (line 43). That
  file is tracked. Revoke the key and blank the line.
- Commit `fa12c53` added `.venv/Lib/site-packages/` to the repository. Add
  `.venv/` to `.gitignore` and run `git rm -r --cached backend/.venv`.

## TIER 2 — Additive only (new files + one registration line)

### 2.1 Plain HTML/CSS/JavaScript adapter
**Blast radius: one new file, one line in the adapter registry. No existing
adapter, agent, workflow or API changes.**

Currently only React, Next.js and Angular exist. Asking for "a simple HTML/CSS/JS
website" returns a React project. This is a likely demo request and a visible
mismatch when it happens.

### 2.2 Additional model providers
**Blast radius: config only for any OpenAI-compatible vendor.**

Proven by the NVIDIA NIM integration: a registry entry plus a settings block,
with zero changes above the LLM layer.

### 2.3 Additional agents
**Blast radius: one new file, one entry in `DEFAULT_SEQUENCE`.**

The planner re-derives execution order from the dependency graph, so nothing
else changes.

## TIER 3 — Small edits to existing files

### 3.1 Routing preference for NVIDIA
**Blast radius: one tuple in `app/llm/routing.py`.**

NVIDIA currently sits behind OpenAI and Anthropic for code and review work.
Since both are paid and neither has a working key, NVIDIA should follow Gemini
directly. Preferences only reorder candidates — no provider becomes unreachable.

### 3.2 PostgreSQL for the demo environment
**Blast radius: one line in `backend/.env`. No schema or model changes.**

See Part 3. Your documentation states PostgreSQL is the database of record while
you are running SQLite.

## TIER 4 — Future scope (declared out of scope in v1)

These are genuine development efforts and are correctly deferred:

- Automatic cloud deployment and live URL generation
- CI/CD pipeline generation for produced projects
- GitHub push automation
- Vector database / semantic memory (needed only when learning from past
  generated projects or indexing external documentation)
- Multi-tenant SaaS isolation
- Learned provider routing (currently rule-based)
- Automated build verification of generated projects inside the pipeline

---

# PART 3 — DATABASE ACCESS

## The diagnosis: pgAdmin cannot connect to your database right now

Two separate reasons, both of which must be fixed for pgAdmin to work.

**Reason 1 — you are not running PostgreSQL.**
`backend/.env` line 43 says:

```
DATABASE_URL=sqlite+aiosqlite:///./aegis.db
```

Your application stores everything in a single file, `backend/aegis.db`.
pgAdmin is a PostgreSQL client. It cannot open a SQLite file.

**Reason 2 — you have no PostgreSQL server installed.**
Nothing exists under `C:\Program Files\PostgreSQL`, and nothing is listening on
port 5432. **pgAdmin is only a GUI client — it is not a database.** Installing
pgAdmin alone does not give you PostgreSQL, the same way installing a web
browser does not give you a website.

## Your current data (read from `backend/aegis.db`)

```
agent_executions      33 rows
artifacts             14 rows
generation_runs        3 rows
projects               3 rows
run_events           103 rows
users                  2 rows
```

---

## PATH A — View your existing data (5 minutes, no code change)

Use this if you just want to see your tables and data. Nothing is modified.

**Step 1.** Download DB Browser for SQLite from https://sqlitebrowser.org
(the "Standard installer, 64-bit" build). Install it.

**Step 2.** Open DB Browser for SQLite.

**Step 3.** Click **Open Database** in the toolbar.

**Step 4.** Navigate to `C:\Users\DELL\Desktop\aegis\backend\` and select
`aegis.db`. Click Open.

**Step 5.** Click the **Database Structure** tab. You will see the six tables
listed above, each expandable to show its columns, types and indexes.

**Step 6.** Click the **Browse Data** tab. Choose a table from the dropdown at
the top left — start with `users`, then `projects`, then `generation_runs`.

**Step 7.** Click the **Execute SQL** tab to run queries. Try:

```sql
SELECT id, name, slug, created_at FROM projects;

SELECT r.id, r.status, p.name
FROM generation_runs r
JOIN projects p ON p.id = r.project_id;

SELECT agent_role, status, duration_ms
FROM agent_executions
ORDER BY started_at;
```

**Alternative without installing anything:** in VS Code, install the extension
"SQLite Viewer" (or "SQLite" by alexcvzz), then right-click `backend/aegis.db`
in the Explorer and choose **Open Database**.

---

## PATH B — Switch to PostgreSQL and use pgAdmin (20–30 minutes)

Use this if you want pgAdmin specifically, or if you want your running system to
match your documentation, which states PostgreSQL is the database of record.

> **Warning:** this is a *different, empty* database. Your existing 2 users,
> 3 projects and 3 runs stay in `aegis.db` and will **not** appear in
> PostgreSQL. You will register a new account. Do this well before any demo,
> not during one.

### Step 1 — Install the PostgreSQL server

1. Go to https://www.postgresql.org/download/windows/
2. Click **Download the installer** (EDB).
3. Choose **PostgreSQL 16** for Windows x86-64. Run the downloaded `.exe`.
4. Click Next through Installation Directory and Data Directory (accept defaults).
5. On the **Components** screen, keep **PostgreSQL Server** and **pgAdmin 4**
   ticked. Stack Builder can be unticked.
6. On the **Password** screen, set a password for the `postgres` superuser.
   **Write it down** — you cannot recover it. For this project use:
   `aegis_password`
7. **Port:** leave it as `5432`.
8. Locale: leave as default. Click Next, then Next, then Finish.
9. Untick "Launch Stack Builder" at the end.

### Step 2 — Confirm the server is running

Open PowerShell and run:

```powershell
Get-Service -Name postgresql*
```

You should see `Status: Running`. If it says `Stopped`, run:

```powershell
Start-Service postgresql-x64-16
```

### Step 3 — Open pgAdmin and connect to the server

1. Open **pgAdmin 4** from the Start menu. It opens in your browser.
2. The first time, it asks you to set a **master password** — this is a pgAdmin
   password, separate from the postgres one. Set anything you will remember.
3. In the left-hand **Browser** panel, expand **Servers**.
4. If a server named `PostgreSQL 16` is already there, click it and enter the
   password from Step 1 point 6. Skip to Step 4.
5. If **Servers** is empty, right-click it → **Register** → **Server…**, then:
   - **General** tab → **Name:** `Local`
   - **Connection** tab → **Host name/address:** `localhost`
   - **Port:** `5432`
   - **Maintenance database:** `postgres`
   - **Username:** `postgres`
   - **Password:** the one you set in Step 1 point 6
   - Tick **Save password**
   - Click **Save**

### Step 4 — Create the role and database AgileAgent expects

1. In pgAdmin, expand **Local** (or `PostgreSQL 16`).
2. Right-click **Databases** → **Query Tool**.
3. Paste this and press **F5** (or the ▶ Execute button):

```sql
CREATE ROLE aegis WITH LOGIN PASSWORD 'aegis_password';
CREATE DATABASE aegis OWNER aegis;
GRANT ALL PRIVILEGES ON DATABASE aegis TO aegis;
```

4. Right-click **Databases** in the left panel → **Refresh**. A database named
   `aegis` now appears.

### Step 5 — Point the application at PostgreSQL

Open `C:\Users\DELL\Desktop\aegis\backend\.env`. Find line 43:

```
DATABASE_URL=sqlite+aiosqlite:///./aegis.db
```

Change it to:

```
DATABASE_URL=postgresql+asyncpg://aegis:aegis_password@localhost:5432/aegis
```

Save the file. **Change nothing else.** The `asyncpg` driver is already
installed, and no model, schema or application code needs to change — the
database URL is the only coupling point.

### Step 6 — Start the backend so the tables are created

```powershell
cd C:\Users\DELL\Desktop\aegis\backend
.\.venv\Scripts\activate
uvicorn app.main:app --reload
```

The schema is created automatically at startup. Watch for startup logs with no
connection errors. Leave this running.

### Step 7 — View your tables in pgAdmin

1. Back in pgAdmin, expand:
   **Servers → Local → Databases → aegis → Schemas → public → Tables**
2. Right-click **Tables** → **Refresh** if nothing shows.
3. You will see: `users`, `projects`, `generation_runs`, `agent_executions`,
   `artifacts`, `run_events`, plus `alembic_version`.
4. Right-click any table → **View/Edit Data** → **All Rows**.

### Step 8 — Create data and watch it appear

1. Start the frontend in a second terminal:
   ```powershell
   cd C:\Users\DELL\Desktop\aegis\frontend
   npm run dev
   ```
2. Open http://localhost:5173 and register a new account.
3. In pgAdmin, right-click the `users` table → **View/Edit Data** → **All Rows**.
   Your new account is there, with a hashed password.
4. Submit a project idea, then refresh the `projects` and `generation_runs`
   tables to watch rows appear live.

### Useful queries for the demo

Right-click the `aegis` database → **Query Tool**, then:

```sql
-- every project with its owner
SELECT p.name, p.slug, u.email, p.created_at
FROM projects p
JOIN users u ON u.id = p.owner_id
ORDER BY p.created_at DESC;

-- which agents ran, and how long each took
SELECT a.agent_role, a.status, a.duration_ms, p.name AS project
FROM agent_executions a
JOIN generation_runs r ON r.id = a.run_id
JOIN projects p ON p.id = r.project_id
ORDER BY a.started_at;

-- skipped agents and the reason (this is the traceability claim, in SQL)
SELECT agent_role, status, skip_reason
FROM agent_executions
WHERE status = 'skipped';

-- artifacts produced per run
SELECT r.id AS run, COUNT(a.id) AS artifacts
FROM generation_runs r
LEFT JOIN artifacts a ON a.run_id = r.id
GROUP BY r.id;
```

The third query is worth showing an examiner — it demonstrates your decision
traceability claim directly from the database.

### If you need to go back to SQLite

Restore line 43 to:

```
DATABASE_URL=sqlite+aiosqlite:///./aegis.db
```

Restart the backend. Your original data is untouched in `backend/aegis.db`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| pgAdmin: "could not connect to server" | PostgreSQL service is stopped | `Start-Service postgresql-x64-16` |
| Backend: `ConnectionRefusedError` on startup | Server not running, or wrong port | Check Step 2; confirm port 5432 |
| Backend: `password authentication failed` | Role/password mismatch | Re-run Step 4; check the URL in Step 5 matches exactly |
| Backend: `database "aegis" does not exist` | Step 4 was skipped or failed | Re-run Step 4, then refresh in pgAdmin |
| pgAdmin shows no tables | Backend has not started yet | Complete Step 6, then Refresh in pgAdmin |
| Your old projects are missing | Expected — PostgreSQL is a new, empty database | Register again, or switch back to SQLite |
