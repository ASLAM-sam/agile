# Development Guide

How to work on Aegis AI: setup, conventions, and how to extend it.

## Contents

- [Setup](#setup)
- [Running the stack](#running-the-stack)
- [Code conventions](#code-conventions)
- [Testing](#testing)
- [Adding a technology adapter](#adding-a-technology-adapter)
- [Adding a model provider](#adding-a-model-provider)
- [Adding an agent](#adding-an-agent)
- [Working on prompts](#working-on-prompts)
- [Database changes](#database-changes)
- [Troubleshooting](#troubleshooting)

---

## Setup

**Prerequisites:** Python 3.11+, Node 20+, and a key for at least one model
provider. Docker and PostgreSQL are optional for local development.

```bash
git clone <repository-url> aegis
cd aegis
cp backend/.env.example backend/.env
```

Set `SECRET_KEY` and a model provider key in `backend/.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`LLM_PROVIDER` names the provider tried first. Every other provider holding a
key stays behind it as an automatic fallback:

| Provider | Key | Where to get one |
|---|---|---|
| `anthropic` (default) | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `gemini` | `GOOGLE_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — free tier |
| `groq` | `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) — free tier |
| `nvidia` | `NVIDIA_API_KEY` | [build.nvidia.com](https://build.nvidia.com) — free credits |
| `openai` | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) |
| `ollama` | none — set `OLLAMA_ENABLED=true` | local `ollama serve` |

**Configure at least two.** A single provider has nothing to fail over to, and
free tiers run out mid-run.

Configuration lives under `backend/` because the backend is the only component
that reads it. `app/core/config.py` resolves the path relative to the package
rather than the working directory, so uvicorn, pytest and alembic all see the
same file wherever they are invoked from. Real environment variables take
precedence over it.

Two values are worth knowing about:

- **A blank `SECRET_KEY=`** is treated as absent and replaced with a random
  per-process key, so sessions drop on every reload. Set it once and that stops.
  Production refuses to start without an explicit key of at least 32 characters.
- **`DATABASE_URL`** defaults to PostgreSQL in the example. Without a server
  running, use the file-backed fallback:
  `DATABASE_URL=sqlite+aiosqlite:///./aegis.db`

**Backend:**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

**Frontend:**

```bash
cd frontend
npm install
```

---

## Running the stack

Two terminals:

```bash
# Terminal 1 — API on :8000  (configuration comes from backend/.env)
cd backend
uvicorn app.main:app --reload

# Terminal 2 — web client on :5173
cd frontend
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000`, so the browser
sees a single origin. CORS never enters the local development loop, and the SSE
stream is not buffered by an intermediary.

The database schema is created automatically at startup — no migration step is
needed to get going.

---

## Code conventions

### Backend

| Rule | Why |
|---|---|
| Routes → services → repositories → models | A service that imports `fastapi` cannot be tested or reused outside HTTP |
| SQLAlchemy 2.0 typed mappings (`Mapped[...]`) | Legacy `Column(...)` loses type information |
| `async def` for all I/O | The event loop must never block |
| Explicit `response_model` and `status_code` on every route | The OpenAPI schema is the contract |
| Pydantic v2 only (`model_config`, `field_validator`) | v1 syntax silently changes behaviour |
| Configuration only via `core/config.py` | `os.getenv` scattered through the codebase cannot be validated |
| Services raise domain exceptions | Registered handlers give every failure one shape |
| Full type annotations, concise docstrings | |

Line length 100. `ruff check app tests alembic` and `ruff format app tests`.
Generated migrations under `alembic/versions/` are exempt from the line-length
rule — see `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml`.

### Frontend

| Rule | Why |
|---|---|
| Function components with typed props | |
| `strict` TypeScript, no `any` | `noUncheckedIndexedAccess` is on |
| Tailwind utilities only | No inline styles, no CSS-in-JS |
| Import via the `@/` alias | Relative chains break on refactor |
| Every data view renders loading, error and empty states | A success-only view is incomplete |
| All network calls through `api/client.ts` | One place for auth, errors and refresh |
| Keyboard-operable interactive elements with visible focus | |

`npm run typecheck` before committing.

### The four states rule

Any component that loads data must handle all four:

```tsx
if (state.isLoading) return <LoadingState />;
if (state.error)     return <ErrorState error={state.error} onRetry={state.reload} />;
if (!state.data?.length) return <EmptyState title="…" description="…" />;
return <TheActualContent data={state.data} />;
```

`useAsync` provides all four; `components/ui/States.tsx` provides the
presentation. There is no reason to hand-roll them.

---

## Testing

```bash
cd backend  && pytest -q                 # 406 tests
cd backend  && pytest --cov=app          # with coverage
cd frontend && npm test                  # 43 tests
```

### How the backend suite stays fast and hermetic

- **Database** — in-memory SQLite per test, via `StaticPool` so every connection
  sees the same database.
- **Model provider** — `StubLLM` returns queued responses in order. No test
  touches the network.
- **Isolation** — each test gets a fresh engine, so order never matters.
- **Configuration** — `conftest` sets `AEGIS_ENV_FILE=""`, which disables the
  dotenv source outright. Without it the suite reads whatever `backend/.env`
  happens to contain, and a stray `ANTHROPIC_API_KEY` or `GENERATION_BATCH_SIZE`
  on one machine quietly changes what the tests exercise.

### What to test

Behaviour, not implementation. A test asserting that a function calls another
function is worthless; one asserting the right output for a given input is not.

The integration suite exercises the whole pipeline end to end — the full-stack
path, the frontend-only path, a non-critical failure and a critical failure.
Those tests are the ones that catch real regressions; two design bugs were found
by them during the initial build.

---

## Adding a technology adapter

One file, one registration line. Nothing else changes.

### 1. Write the adapter

```python
# app/adapters/frontend/vue.py
from app.adapters.base import FrontendAdapter, ScaffoldContext, ScaffoldFile


class VueAdapter(FrontendAdapter):
    key = "vue"
    display_name = "Vue"
    language = "TypeScript"
    version = "3.5"
    description = "Progressive framework with a gentle learning curve."
    tags = ("spa", "typescript", "vite")
    best_for = ("Teams new to component frameworks", "Rapid prototyping")

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        """Deterministic build tooling. Never generated by an agent."""
        return [
            ScaffoldFile(
                path="frontend/package.json",
                content=...,                      # pinned dependencies
                description="Node package manifest.",
            ),
            # tsconfig.json, vite.config.ts, index.html, Dockerfile, nginx.conf
        ]

    def dockerfile(self, ctx: ScaffoldContext) -> str:
        ...   # multi-stage, non-root, with a HEALTHCHECK

    def conventions(self, ctx: ScaffoldContext) -> str:
        """The contract handed to the Frontend Engineer.

        Must state the exact file layout, the framework rules generated code
        must follow, and a 'Do not generate' section listing the scaffold files.
        """
        ...
```

### 2. Register it

```python
# app/adapters/registry.py — inside build_default_registry()
from app.adapters.frontend.vue import VueAdapter

for adapter in (ReactAdapter(), NextJSAdapter(), AngularAdapter(), VueAdapter(), ...):
    registry.register(adapter)
```

That is the whole change. The adapter now appears in the catalogue, is scored by
the recommendation engine, and is selectable in the UI.

### 3. Optionally, teach the recommender about it

To have domain signals steer towards it, add entries to `_FRONTEND_SIGNALS` in
`app/services/recommendation_service.py`. Without this it still scores from the
baseline — it simply will not be preferred for any particular domain.

### 4. Confirm the shared tests cover it

`tests/unit/test_adapters.py` is parameterised over the registry. Add the key to
the parameter lists and it inherits every contract check: path safety, non-empty
content, pinned dependencies, non-root Dockerfiles, and a "Do not generate"
section.

---

## Adding a model provider

Two cases. Both leave every agent, workflow step and adapter untouched.

### It speaks the OpenAI chat-completions protocol

Most do. This is configuration, not code — add a factory entry to
`app/llm/providers/registry.py`:

```python
def _together(spec: ProviderSpec, config: Settings) -> ProviderAdapter:
    return OpenAICompatibleAdapter(
        spec,
        base_url=config.together_base_url,
        api_key=config.together_api_key,
        timeout_seconds=config.llm_timeout_seconds,
        supports_json_schema=False,   # falls back to json_object + validation
    )

PROVIDER_FACTORIES["together"] = _together
PROVIDER_LABELS["together"] = ("Together AI", ("free tier",))
```

Add `together_api_key`, `together_model` and `together_base_url` to `Settings`,
list the key in `provider_credentials` and `provider_models`, and it appears in
the routing order, on the dashboard, and in failover.

NVIDIA NIM is the worked example: `_nvidia` in the registry, a settings block,
three map entries. No new client, no change to the manager, nothing above the
LLM layer. See `tests/unit/test_nvidia_provider.py`.

### It has its own SDK

Subclass `ProviderAdapter` in `app/llm/providers/`. It owns exactly two things:

```python
class MyAdapter(ProviderAdapter):
    @property
    def is_configured(self) -> bool: ...

    async def complete_structured(self, prompt) -> Completion: ...
    async def complete_text(self, prompt) -> TextCompletion: ...

    def classify(self, error: BaseException) -> ErrorKind:
        """Retry, fail over, or stop."""
```

Retrying, selection, caching and health are **not** the adapter's job. They are
cross-provider policies; implementing them per adapter is how five providers
become five subtly different behaviours.

### Classification is the part that matters

`classify` decides whether a failure is retried, handed to the next provider, or
raised. Get it wrong and the system degrades quietly:

- A quota misread as `RETRYABLE` earns no cooldown, so every remaining agent
  pays another round trip to rediscover the same empty quota.
- A malformed request misread as `QUOTA` is retried against all five providers,
  spending five quotas to collect five identical rejections.

Walk `__cause__`, not just the outer exception — a client with its own retry
loop wraps the real error. `tests/unit/test_provider_manager.py` has the
regression cases.

### Confirm it participates

```bash
pytest tests/unit/test_provider_manager.py -q
```

The failover, routing and cooldown tests are provider-agnostic, so a new adapter
inherits them by being registered.

---

## Adding an agent

```python
# app/agents/security_engineer.py
from app.agents.base import Agent
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AgentRole


class SecurityEngineerAgent(Agent):
    role = AgentRole.SECURITY_ENGINEER          # add to the enum first
    display_name = "Security Engineer"
    description = "Audits generated code for security defects."

    depends_on = (AgentRole.BACKEND_ENGINEER,)  # ordering
    requires = ()                               # nothing it cannot work without

    def should_execute(self, ctx) -> SkipDecision:
        if not ctx.memory.needs_auth:
            return SkipDecision.skip("No authentication, so there is no session to audit.")
        return SkipDecision.run()

    def system_prompt(self, ctx) -> str:
        return "ROLE: Security Engineer\n\n…"

    async def execute(self, ctx) -> AgentResult:
        await ctx.progress(self.role, 20, "Auditing authentication paths")
        completion = await ctx.llm.complete_structured(
            self.build_prompt(ctx, instruction="…", schema=FINDINGS_SCHEMA)
        )
        ...
        return AgentResult(role=self.role, summary="…", usage=completion.usage)
```

Add it to `DEFAULT_SEQUENCE` in `app/agents/registry.py`. The planner re-derives
the execution order from the dependency graph — you do not position it manually.

### `depends_on` vs `requires`

This distinction matters and is enforced by a test.

- **`depends_on`** — *ordering*. "Run me after X so I can see its output."
- **`requires`** — *hard requirement*. "I cannot function without X."

Only a failed `requires` blocks an agent. Declaring an ordering dependency as a
requirement means one non-essential agent failing cascades into skipping
everything downstream — including packaging, which discards the user's project.
Default `requires` to empty and add to it only when the agent genuinely cannot
produce anything useful without that input.

---

## Working on prompts

Prompts live in each agent's `system_prompt()` and in each adapter's
`conventions()`. Both are ordinary Python strings, so they are diffable and
reviewable.

Guidelines that have held up:

- **Be concrete.** "Every foreign key declares an explicit `ON DELETE` action"
  beats "follow database best practices".
- **Give worked examples for judgement calls.** The Business Analyst's
  capability decisions are the highest-leverage output in the system, so its
  prompt carries six worked examples and two decision tests.
- **State what *not* to do only where the failure is real.** Every prohibition
  costs attention; a speculative one costs attention for nothing.
- **Keep the cacheable prefix stable.** `cacheable_prefix()` must not vary
  between calls within a run, or prompt caching stops working silently. Check
  `usage.cache_read_tokens` if you suspect it has.

After changing a prompt, run the integration suite. It will not judge prose, but
it will catch a schema that no longer matches what the agent writes into memory.

---

## Database changes

The development path calls `Base.metadata.create_all` at startup, so a new
column appears on the next restart of a fresh database.

For an existing database, or for staging and production, use Alembic. The
repository ships with an initial-schema migration as the baseline:

```bash
cd backend
alembic revision --autogenerate -m "add security findings table"
alembic upgrade head          # apply
alembic downgrade -1          # revert one revision
alembic current               # what is applied now
alembic history               # full revision graph
```

Inside a container:

```bash
docker compose exec api alembic upgrade head
```

Notes:

- `alembic/env.py` reads `DATABASE_URL` from application settings rather than
  `alembic.ini`, so migrations always target the same database the application
  does and no credential is committed.
- New models must be imported in `app/models/__init__.py`, or autogenerate will
  not see them and will propose *dropping* the table.
- `render_as_batch` is enabled automatically on SQLite, which cannot `ALTER`
  most columns in place. The same migration therefore runs on both PostgreSQL
  and the SQLite development fallback.
- `env.py` supplies a `render_item` hook for the portable `JSONType` column.
  Without it, autogenerate emits `postgresql.JSONB(astext_type=Text())` and
  omits the `Text` import, producing a migration that raises `NameError` when
  it runs.
- **Always read a generated migration before applying it.** Autogenerate
  detects added and removed objects well, but it cannot distinguish a rename
  from a drop-plus-add — and it will happily generate the destructive version.

---

## Troubleshooting

**`… is not configured` (503)** — expected when the selected provider's key is
absent. The message names the variable to set. The platform runs and the
interface is browsable; only generation is disabled.

**Gemini quota errors (503)** — the free tier limits requests per minute and per
day, and a generation run makes many calls. Lower `GENERATION_BATCH_SIZE` and
`MAX_CONCURRENT_RUNS`, or wait for the window to reset.

**`is no longer available to new users` (503)** — Google retires model ids for
new API keys while still returning them from `models.list()`. Set
`GEMINI_MODEL` to a current flash model.

**`ImportError: partially initialized module`** — a package `__init__` is
re-exporting across a layer boundary. See the layering table in
[ARCHITECTURE.md](ARCHITECTURE.md); import from the module directly instead.

**Port already in use** — `uvicorn app.main:app --reload --port 8001`, and
update `vite.config.ts`'s proxy target to match.

**The live console shows nothing** — check that no proxy is buffering the
stream. The bundled nginx config sets `proxy_buffering off` for `/api/`
specifically for this reason.

**Prompt caching seems ineffective** — inspect `usage.cache_read_tokens` on a
completion. Zero across repeated calls means something varies inside the
cacheable prefix.

**Frontend type errors after pulling** — `rm -rf node_modules && npm install`.
`noUncheckedIndexedAccess` makes indexed access return `T | undefined`, so
`array[0]` needs a guard.
