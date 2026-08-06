# Aegis AI

**Multi-Agent AI Software Engineering Platform for Autonomous Software Development**

> From idea to production-ready starter project — powered by an autonomous AI engineering team.

Describe a software idea in plain language. Eleven specialised AI engineers
analyse the requirements, decide which capabilities the project actually needs,
design the architecture and database schema, write the frontend and backend,
review and improve their own output, document everything, and hand back a
downloadable project.

It behaves like a software company, not a chatbot: the Business Analyst's
findings determine which engineers are assigned, so a portfolio site gets no
database engineer and a banking system gets the whole team.

---

## Contents

- [What it produces](#what-it-produces)
- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [The engineering team](#the-engineering-team)
- [Supported technologies](#supported-technologies)
- [Architecture](#architecture)
- [Project layout](#project-layout)
- [Development](#development)
- [Testing](#testing)
- [Configuration](#configuration)
- [Extending the platform](#extending-the-platform)
- [Limitations](#limitations)

---

## What it produces

Every generated project includes, where the requirements call for it:

| Category | Deliverables |
|---|---|
| **Requirements** | Executive summary, project overview, SRS, functional and non-functional requirements, user stories, use cases, scope |
| **Design** | Software architecture, module breakdown, layer rules, folder structure, architectural decision records |
| **Database** | Schema design, executable SQL DDL, seed data, forward-only migrations, relationship and index design |
| **API** | Complete REST specification: paths, methods, request and response shapes, status codes, auth requirements |
| **Code** | Frontend source, backend source, environment configuration — with build tooling emitted deterministically |
| **Quality** | Unit tests, structural validation, code review findings, an applied improvement pass |
| **Documentation** | README, installation guide, API reference, developer guide, configuration reference |
| **DevOps** | Dockerfiles per service, `docker-compose.yml`, `.gitignore`, `.editorconfig` |
| **Reporting** | AI Engineering Report, project manifest, downloadable ZIP |

Artifacts a project genuinely does not need are marked *not required* with the
reason, rather than being generated for the sake of a checklist.

---

## Quick start

### With Docker

```bash
git clone <repository-url> aegis
cd aegis

cp backend/.env.example backend/.env
# In backend/.env set SECRET_KEY and one provider key:
#   LLM_PROVIDER=anthropic  ->  ANTHROPIC_API_KEY
#   LLM_PROVIDER=gemini     ->  GOOGLE_API_KEY   (free tier)
#   python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose --env-file ./backend/.env up --build
```

Configuration lives in `backend/.env`, because the backend is the only
component that reads it. Compose does not look there on its own, hence
`--env-file`.

| Service | URL |
|---|---|
| Web client | http://localhost:5173 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

### Without Docker

The platform boots against SQLite, so no database server is required for local
development.

**Backend** (terminal 1):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env
# In backend/.env set SECRET_KEY, a provider key, and for a database
# that needs no server:
#   LLM_PROVIDER=gemini
#   GOOGLE_API_KEY=...          # free tier: https://aistudio.google.com/apikey
#   DATABASE_URL=sqlite+aiosqlite:///./aegis.db

uvicorn app.main:app --reload
```

`backend/.env` is resolved by absolute path, so uvicorn, pytest and alembic all
read the same file no matter which directory you run them from.

**Frontend** (terminal 2):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, create an account, and submit an idea.

> Without the selected provider's key the platform still runs and the interface
> is fully browsable — generation is disabled and says which variable to set.

---

## How it works

```
Idea
 ↓
Requirement analysis          Business Analyst decides what the project needs
 ↓
Technology recommendation     Ranked options, each with its reasoning
 ↓
Stack review (optional)       You may override any layer
 ↓
Workflow engine               Plans execution, resolves dependencies
 ↓
Dynamic agent execution       Only the agents this project needs
 ↓
Code review                   Finds real, file-specific issues
 ↓
Code improvement              Applies the findings
 ↓
Artifact packaging            Assembles and versions the deliverables
 ↓
AI Engineering Report
 ↓
Download ZIP
```

### The dynamic part

The Business Analyst answers five questions about the idea:

- Does anything need to persist between sessions? → **database**
- Do different people see different data? → **authentication**
- Must a client exchange data with a server? → **API** and **backend**
- Is there a user interface? → **frontend**

Those answers drive the workflow. Two examples from the test suite:

| Project | Agents engaged | Skipped |
|---|---|---|
| Hospital management system | 11 of 11 | — |
| Portfolio website | 9 of 11 | Database Engineer, Backend Engineer |

Skipped agents are shown in the interface **with the reason**, so the decision
is legible rather than mysterious.

### Deterministic scaffolding vs. AI generation

A deliberate split runs through the whole platform:

- **Adapters emit build tooling** — `package.json`, `tsconfig.json`,
  `vite.config.ts`, `pyproject.toml`, Dockerfiles, nginx configs. These are
  hand-verified and version-pinned. Agents never generate build configuration,
  because a subtly wrong build file breaks a project in ways a reader cannot
  diagnose.
- **Agents generate application logic** — pages, components, routes, services,
  repositories, schema, tests — guided by the adapter's conventions prompt,
  which states exactly which files already exist and must not be recreated.

### Two-phase code generation

Code agents work in two passes rather than asking for a whole application in
one completion:

1. **Plan** — emit a file manifest (paths, purpose, dependencies, order).
2. **Generate** — produce file contents in ordered batches, each batch seeing
   the manifest and the paths already written.

A single completion for an entire application reliably truncates and produces
files importing modules the model never wrote.

---

## The engineering team

| # | Agent | Responsibility | Runs when |
|---|---|---|---|
| 1 | **Manager** | Names the project, sets the delivery approach and success criteria | Always |
| 2 | **Business Analyst** | SRS, requirements, user stories, use cases, **capability decisions** | Always |
| 3 | **Solution Architect** | Architecture, modules, layers, folder structure, API contract | Always |
| 4 | **Database Engineer** | Schema, relationships, indexes, migrations | Data persists |
| 5 | **Backend Engineer** | APIs, services, data access, validation, auth | Server logic needed |
| 6 | **Frontend Engineer** | Pages, routing, components, responsive layout, API integration | UI needed |
| 7 | **QA Engineer** | Structural validation and unit tests | Code was generated |
| 8 | **AI Review Engineer** | Architectural, security and correctness review | Enough source to review |
| 9 | **Code Improvement Engineer** | Applies review findings | Review found issues |
| 10 | **Documentation Engineer** | README, installation, API docs, developer guide | Always |
| 11 | **Artifact Manager** | Compose file, ignore rules, manifest, package | Always |

Two agents are deterministic by design: the **Workflow Engine** sequences
execution in ordinary code (a guarantee beats a probability), and the
**Artifact Manager** derives Compose files and manifests mechanically from
state already in memory.

---

## Supported technologies

| Layer | Options |
|---|---|
| **Frontend** | React 18 · Next.js 15 · Angular 18 |
| **Backend** | FastAPI · Express.js · Spring Boot 3.4 |
| **Database** | PostgreSQL 16 · MySQL 8.4 · SQLite 3 |

Each adapter contributes its own scaffold, conventions, container definition
and dialect rules. The recommendation engine scores all of them against the
analysed requirements and explains every ranking — you are choosing between
arguments, not accepting a verdict.

---

## Architecture

### Backend — layered, with strict dependency direction

```
api/          HTTP only: routing, serialisation, status codes
  ↓
services/     Business logic. Never imports FastAPI.
  ↓
repositories/ All SQL. Accepts an AsyncSession.
  ↓
models/       SQLAlchemy 2.0 typed ORM
```

Alongside those, four subsystems carry the platform's actual capability:

| Subsystem | Role |
|---|---|
| `agents/` | The eleven engineers. Each declares its skip rule and prompt. |
| `workflow/` | Shared project memory, topological planner, execution engine, event bus |
| `adapters/` | Plugin technology system: scaffolds, conventions, containers |
| `packaging/` | Virtual workspace, ZIP builder, Compose generation, reporting |

### Shared project memory

One typed state object threads through every agent. It is why the agents behave
like colleagues rather than independent prompts: the Backend Engineer sees the
schema the Database Engineer designed, the QA Engineer sees the code the others
wrote, and the Documentation Engineer sees all of it.

Version 1 uses no vector store. The state is small, structured and fully
enumerable, so exact recall beats similarity search.

### Ordering vs. requirement

Agent dependencies are declared in two kinds, deliberately kept apart:

- `depends_on` — **ordering**. Run me after X so I can see its output.
- `requires` — **hard requirement**. I cannot function without X.

Only a failed `requires` blocks an agent. Conflating the two means one
non-essential agent failing (say, the QA Engineer) cascades into skipping
documentation and packaging, discarding an otherwise complete project. A test
enforces that `requires` is always a subset of `depends_on`.

### Live streaming

Run events are broadcast over Server-Sent Events and persisted simultaneously.
A client that connects late, reloads, or reconnects after a drop replays history
from its last sequence number and continues with no gap.

The client consumes the stream through `fetch` + `ReadableStream` rather than
`EventSource`, because `EventSource` cannot set request headers — the only way
to authenticate it would be a token in the query string, which leaks into
browser history, proxy logs and the `Referer` header.

---

## Project layout

```
aegis/
├── backend/
│   ├── app/
│   │   ├── adapters/          Plugin technology system (9 adapters)
│   │   │   ├── frontend/      react, nextjs, angular
│   │   │   ├── backend/       fastapi, express, spring-boot
│   │   │   └── database/      postgresql, mysql, sqlite
│   │   ├── agents/            The 11 AI engineers
│   │   ├── api/v1/routes/     HTTP layer
│   │   ├── core/              Config, security, logging, exceptions, enums
│   │   ├── db/                Engine, session, bootstrap
│   │   ├── llm/               Anthropic client, schemas, protocol
│   │   ├── models/            SQLAlchemy ORM
│   │   ├── packaging/         Workspace, ZIP, Compose, reporting
│   │   ├── repositories/      Data access
│   │   ├── schemas/           Pydantic request/response models
│   │   ├── services/          Business logic
│   │   ├── workflow/          Memory, planner, engine, events
│   │   └── main.py
│   ├── alembic/               Migrations
│   ├── tests/                 219 tests
│   ├── .env.example           Annotated configuration → copy to backend/.env
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/               Single HTTP boundary
│   │   ├── components/        UI primitives, layout, feature components
│   │   ├── hooks/             Auth, theme, async data, run stream
│   │   ├── pages/             10 routed pages
│   │   ├── types/             Domain types mirroring the API
│   │   └── lib/               Pure helpers
│   └── package.json
├── docs/
└── docker-compose.yml
```

---

## Development

```bash
# Backend
cd backend
uvicorn app.main:app --reload      # http://localhost:8000
ruff check app                     # lint
ruff format app                    # format

# Frontend
cd frontend
npm run dev                        # http://localhost:5173
npm run typecheck
npm run build
```

The Vite dev server proxies `/api` to `http://localhost:8000`, so the browser
sees a single origin and CORS never enters the local development loop.

---

## Testing

```bash
cd backend && pytest -q                    # 219 tests
cd backend && pytest --cov=app             # with coverage
cd frontend && npm test                    # 43 tests
```

The backend suite runs against an in-memory SQLite database and a deterministic
language-model double, so it is fast and hermetic — no test touches the network.
The integration suite exercises the entire pipeline end to end, including the
full-stack path, the frontend-only path, and both failure modes.

---

## Configuration

Every setting is read from the environment through `app/core/config.py` and
validated once at import. Values come from `backend/.env`, and real environment
variables override that file — which is how the Compose stack injects
configuration without shipping the file into the image. See
[`backend/.env.example`](backend/.env.example) for the annotated list; the
essentials:

| Variable | Purpose | Default |
|---|---|---|
| `LLM_PROVIDER` | Which model provider the agents use: `anthropic` or `gemini`. | `anthropic` |
| `ANTHROPIC_API_KEY` | Required when the provider is `anthropic`. | — |
| `GOOGLE_API_KEY` | Required when the provider is `gemini`. Free-tier keys from [AI Studio](https://aistudio.google.com/apikey). | — |
| `SECRET_KEY` | JWT signing key. Generate a fresh one. | random per process |
| `DATABASE_URL` | PostgreSQL in production; SQLite works for local development. | SQLite file |
| `LLM_MODEL` | Model identifier when the provider is `anthropic`. | `claude-opus-5` |
| `GEMINI_MODEL` | Model identifier when the provider is `gemini`. | `gemini-3.6-flash` |

Only the selected provider's key is needed. Generation is disabled without it;
the rest of the platform still runs so the interface stays browsable.

### Choosing a provider

Both implement the same `LLMProvider` interface, so no agent, adapter or
workflow code differs between them.

| | Anthropic | Gemini |
|---|---|---|
| Cost | Paid credit required | Free tier available |
| Schema enforcement | `output_config.format` | `response_json_schema` |
| Thinking | `effort` levels honoured | Model sizes its own budget; `LLM_EFFORT` ignored |
| Prompt caching | Yes, on the stable system prefix | Not used |

The free Gemini tier enforces per-minute and per-day request limits. A long
generation run makes many calls, so if it stops with a quota message, lower
`GENERATION_BATCH_SIZE` and `MAX_CONCURRENT_RUNS` and start it again.
| `LLM_EFFORT` | Reasoning depth: `low` … `max`. | `high` |
| `MAX_CONCURRENT_RUNS` | Runs permitted in flight at once. | `4` |
| `ENVIRONMENT` | `development` \| `staging` \| `production` | `development` |

Production configuration is enforced, not merely documented: setting
`ENVIRONMENT=production` with `DEBUG=true` or a SQLite URL fails at startup
rather than at 3am.

---

## Extending the platform

Adding a technology takes one file and one line — no workflow, agent or API
change:

```python
# app/adapters/frontend/vue.py
from app.adapters.base import FrontendAdapter, ScaffoldContext, ScaffoldFile

class VueAdapter(FrontendAdapter):
    key = "vue"
    display_name = "Vue"
    language = "TypeScript"
    version = "3.5"
    description = "Progressive framework with a gentle learning curve."

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        ...   # package.json, vite.config.ts, tsconfig.json, Dockerfile

    def conventions(self, ctx: ScaffoldContext) -> str:
        ...   # the contract handed to the Frontend Engineer

    def dockerfile(self, ctx: ScaffoldContext) -> str:
        ...
```

Register it in `app/adapters/registry.py` and it immediately appears in the
catalogue, the recommendation engine and the stack-selection screen.

Adding an agent is the same shape: subclass `Agent` or `CodeAgent`, declare
`depends_on` / `requires` and a `should_execute` rule, and add it to
`DEFAULT_SEQUENCE` in `app/agents/registry.py`. The planner re-derives the
execution order from the dependency graph.

---

## Limitations

Deliberately out of scope in version 1, with the architecture built to
accommodate them later:

- Automatic cloud deployment and live URL generation
- CI/CD pipeline generation
- GitHub push automation
- Vector database / semantic memory
- Multi-tenant SaaS isolation

### What a generated project is

A **production-oriented starter project**: a complete, coherent foundation with
working code, a real schema, documentation and tests. It is a strong starting
point, not a finished product.

Before deploying anything it produces, review the code against your own
standards, replace every placeholder credential, run and extend the test suite,
and perform a security review appropriate to your risk profile. The generated
`AI_ENGINEERING_REPORT.md` says the same thing, in the package.

---

**Aegis AI v1.0** — built with FastAPI, React, PostgreSQL and Claude.
