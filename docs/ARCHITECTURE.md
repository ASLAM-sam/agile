# Architecture

How Aegis AI is put together, and why each significant decision was made.

## Contents

- [Design principles](#design-principles)
- [System overview](#system-overview)
- [The agent layer](#the-agent-layer)
- [The workflow engine](#the-workflow-engine)
- [Shared project memory](#shared-project-memory)
- [The adapter system](#the-adapter-system)
- [The LLM layer](#the-llm-layer)
- [Packaging](#packaging)
- [Real-time streaming](#real-time-streaming)
- [Data model](#data-model)
- [Decision record](#decision-record)

---

## Design principles

1. **Determinism where a guarantee is available.** Sequencing, path safety,
   build configuration and Compose files are ordinary code. A language model is
   used where judgement is required, not where a guarantee already exists.
2. **One responsibility per file.** Every module has a single reason to change.
3. **Strict dependency direction.** Routes → services → repositories → models.
   A service never imports `fastapi`; a route never writes SQL.
4. **Extension without modification.** Adding a technology or an agent means
   adding a file and registering it. No existing file changes shape.
5. **Explain every decision to the user.** Skips carry reasons, recommendations
   carry rationale, effort estimates carry their basis.
6. **Degrade, do not collapse.** One non-essential agent failing must not
   discard an otherwise complete project.

---

## System overview

```
┌──────────────────────────────────────────────────────────────────┐
│  React SPA                                                        │
│  pages · hooks · single API boundary · SSE consumer               │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTPS / SSE
┌────────────────────────────▼─────────────────────────────────────┐
│  FastAPI                                                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  api/v1/routes   HTTP only                                  │  │
│  ├────────────────────────────────────────────────────────────┤  │
│  │  services        Business logic, no framework imports       │  │
│  ├────────────────────────────────────────────────────────────┤  │
│  │  repositories    All SQL                                    │  │
│  ├────────────────────────────────────────────────────────────┤  │
│  │  models          SQLAlchemy 2.0 typed ORM                   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────┐ │
│  │  agents   │  │ workflow  │  │ adapters  │  │  packaging    │ │
│  │  11 roles │  │ engine +  │  │ 9 plugins │  │ workspace,    │ │
│  │           │  │ memory    │  │           │  │ zip, report   │ │
│  └───────────┘  └───────────┘  └───────────┘  └───────────────┘ │
└────────────┬──────────────────────────────────┬──────────────────┘
             │                                  │
      ┌──────▼───────┐                  ┌───────▼─────────────────┐
      │  PostgreSQL  │                  │  ProviderManager        │
      └──────────────┘                  │  gemini · groq · nvidia │
                                        │  ollama · openai        │
                                        │  anthropic              │
                                        └─────────────────────────┘
```

### Module layering

The `packaging` and `workflow` packages span layers, which their `__init__`
files document explicitly:

| Layer | Modules |
|---|---|
| 0 | `core` — config, enums, exceptions, logging, security |
| 1 | `packaging.workspace`, `packaging.zip_builder`, `llm.*`, `adapters.*` |
| 2 | `workflow.memory`, `workflow.events` |
| 3 | `packaging.compose`, `packaging.ignore` |
| 4 | `agents.*` |
| 5 | `workflow.planner`, `workflow.engine` |
| 6 | `packaging.report` |
| 7 | `services.*`, `api.*` |

Package `__init__` files re-export **only their own layer**. Re-exporting
upward creates an import cycle — `workflow.memory` imports
`packaging.workspace`, so a `packaging/__init__` that eagerly imported
`packaging.report` (which imports `workflow.engine`, which imports the agents)
would close the loop. Both `__init__` files carry a comment saying so, and the
direct import path to use instead.

---

## The agent layer

### Contract

```python
class Agent(ABC):
    role: AgentRole
    display_name: str
    depends_on: tuple[AgentRole, ...] = ()   # ordering
    requires:   tuple[AgentRole, ...] = ()   # hard requirement

    def should_execute(self, ctx) -> SkipDecision: ...
    def system_prompt(self, ctx) -> str: ...
    async def execute(self, ctx) -> AgentResult: ...
```

`CodeAgent` extends this with the two-phase generation strategy every
code-producing engineer uses.

### Two-phase generation

```
plan_files()      →  file manifest: paths, purpose, dependencies, priority
                     small, cheap, forces a coherent structure up front
      ↓
generate_files()  →  ordered batches of N files
                     each batch sees the manifest + paths already written
```

Asking for a whole application in one completion truncates and produces files
importing modules that were never written. Batching also lets a single
malformed file be rejected without discarding the batch around it.

### Prompt structure

Every agent request has three parts:

| Part | Content | Cached |
|---|---|---|
| Cacheable prefix | Platform preamble + this agent's role instructions | yes |
| Volatile system | Current project state from shared memory | no |
| User message | The specific instruction for this call | no |

The cache breakpoint sits on the stable prefix, which is byte-identical across
every call an agent makes in a run — so the expensive preamble is billed at
cache-read rates after the first call. Project-specific content deliberately
follows the breakpoint.

---

## The workflow engine

Deterministic code, not a language model. Asking a model to decide execution
order would trade a guarantee for a probability, and ordering is exactly where
a guarantee is available.

### Planning

`build_plan()` performs a topological sort over `depends_on`, breaking ties by
the registry's canonical order so plans are stable and readable rather than
merely valid. A dependency cycle raises `WorkflowError` naming the agents
involved — it is never silently dropped.

### Execution

```
for step in plan:
    if already skipped:                      → record and continue
    if agent.should_execute() says skip:     → record reason and continue
    if a hard requirement failed:            → skip, naming the blocker
    run the agent
    if it failed and the role is critical:   → abort the run
```

`should_execute()` is re-evaluated **immediately before each agent runs**, not
once up front. That is what makes the workflow dynamic: the Business Analyst's
capability decisions land in shared memory mid-run and silence the agents that
are no longer relevant.

### Failure policy

| Role | On failure |
|---|---|
| Business Analyst, Solution Architect, Artifact Manager | Run aborts |
| Everything else | Recorded, run continues |

A run that produced working code but no tests is still worth delivering. The
`requires` / `depends_on` split is what makes this hold in practice — see the
decision record below.

---

## Shared project memory

One typed dataclass threaded through every agent:

```python
@dataclass
class SharedProjectMemory:
    workspace:    ProjectWorkspace       # every generated file
    analysis:     RequirementAnalysis    # requirements + capability decisions
    tech_stack:   TechStack
    architecture: ArchitectureDesign     # modules, layers, API contract
    database:     DatabaseDesign         # tables, relationships, DDL
    review:       ReviewFindings
    confidence:   dict[str, float]
    agent_summaries: dict[str, str]
```

`context_digest()` renders a compact view injected into every prompt. It is
ordered so nothing project-specific appears before the cache breakpoint.

### Why no vector database

The state is small, structured and fully enumerable. Exact recall of a typed
object beats similarity search over embeddings when you can simply hold the
whole thing. A vector store would add operational weight and non-determinism to
solve a problem this system does not have.

---

## The adapter system

The extension point. An adapter encapsulates everything the platform knows
about one technology:

```python
class TechnologyAdapter(ABC):
    key: str
    display_name: str
    kind: AdapterKind
    version: str

    def scaffold(self, ctx) -> list[ScaffoldFile]:  ...  # deterministic files
    def conventions(self, ctx) -> str:              ...  # prompt contract
```

### The scaffold / generation split

| Emitted by the adapter (deterministic) | Generated by an agent |
|---|---|
| `package.json`, `pyproject.toml`, `build.gradle` | Pages, components, routes |
| `tsconfig.json`, `vite.config.ts`, `angular.json` | Services, repositories |
| `Dockerfile`, `nginx.conf`, `.dockerignore` | Models, schemas, DTOs |
| `.env.example` | Tests |

Build tooling is hand-verified and version-pinned. A subtly wrong `tsconfig.json`
or a `package.json` with a hallucinated dependency breaks a project in ways the
reader cannot diagnose, and no amount of prompt engineering makes that risk
acceptable when the file is fully determined anyway.

Each adapter's `conventions()` explicitly lists the files it already provides
under a **"Do not generate"** heading, so the agent never recreates them. A test
asserts every adapter includes that section.

---

## The LLM layer

Agents depend on the `LLMProvider` protocol, never on a vendor. `ProviderManager`
implements that same protocol, so introducing multi-provider orchestration
changed no agent, no workflow step and no adapter — the seam already existed for
testability, and this is what it was for.

```
agent.complete_structured(prompt)
        |
        v
  ProviderManager          <- the only thing that talks to a vendor
        |
   cache -> route -> retry -> fail over -> record
        |
        v
  ProviderAdapter (gemini | groq | nvidia | ollama | openai | anthropic)
```

### The five stages

| Stage | Module | Behaviour |
|---|---|---|
| Cache | `llm/cache.py` | An identical prompt already answered returns immediately and costs nothing. Keyed on content, not vendor, so an answer from one provider serves a request routed to another. |
| Route | `llm/routing.py` | The calling agent's role implies a task kind, which orders the candidates. Preference only — every provider stays reachable behind the preferred one. |
| Retry | `llm/retry.py` | Exponential backoff with jitter against the *same* provider. Only `RETRYABLE` failures qualify. |
| Fail over | `llm/manager.py` | A quota, rejected key or missing model moves to the next candidate and cools the failed one down. |
| Record | `llm/health.py` | Latency, tokens, retries, failovers and cooldowns, per provider. Backs the dashboard *and* the routing decision. |

### Failure classification

The whole design turns on one question per failure: retry, fail over, or stop?

| Kind | Meaning | Action |
|---|---|---|
| `RETRYABLE` | Timeout, connection error, 5xx | Retry the same provider |
| `QUOTA` | Rate limited or out of credit | Next provider; cool this one down |
| `AUTH` | Credentials rejected | Next provider; retrying cannot help |
| `UNAVAILABLE` | Model or endpoint missing, or a refusal | Next provider |
| `FATAL` | The request itself is malformed | Stop — every provider rejects it identically |

Adapters tag the errors they raise and the manager reads the tag. Parsing
messages was the alternative and is the wrong one: vendor wording changes
without notice, and routing that silently degrades when a vendor rewrites a
string is worse than no routing at all. Untagged errors default to `FATAL`,
because an unknown failure repeated across five providers costs five quotas and
still fails.

Classification walks the exception chain. Both first-party clients wrap their
last transport failure in a generic error; reading only the outer exception
turned an exhausted quota into an ordinary timeout, which earned no cooldown and
made every remaining agent rediscover it.

### The adapters

| Module | Providers | Structured output |
|---|---|---|
| `providers/native.py` | Anthropic, Gemini | Server-enforced JSON Schema |
| `providers/openai_compatible.py` | Groq, NVIDIA NIM, OpenAI, Ollama | `json_schema` where supported, else `json_object` plus prompt-stated schema, validated locally |

Groq, NVIDIA, OpenAI and Ollama share one implementation because they share one
wire protocol. A response that fails local validation is reported as a provider
failure, so the manager fails over rather than handing a malformed object to an
agent.

That reuse is what makes adding a vendor a configuration change. NVIDIA NIM was
added as a registry entry and a block of settings: no new client, no change to
the manager, and nothing above the LLM layer. Its one variation — how reliably a
given NIM model honours `response_format` — is read from
`NVIDIA_STRUCTURED_OUTPUT` rather than assumed, because the catalogue is
heterogeneous and the weakest mode (schema in the prompt, validated locally) is
correct for every model in it.

Schema construction goes through `llm/schema.py`, which applies
`additionalProperties: false` and the `required` list automatically. Every
construct it emits is on every provider's supported list, so a schema needs no
translation when the provider changes.

### ADR: the manager implements the protocol it replaces

`ProviderManager` could have been a new interface that agents were migrated to.
Making it satisfy the existing `LLMProvider` protocol instead meant the entire
agent layer was already compatible: the change was one factory returning a
different object.

The manager is a process-wide singleton, which is the point rather than an
optimisation. Cooldowns and the cache only mean anything if they outlive a
single run; rebuilt per request, the system would rediscover an exhausted quota
on every agent and never serve a cache hit. It is closed once, from the
application lifespan.

### ADR: non-AI work stays non-AI

Packaging, ZIP assembly, folder creation, manifests, the execution timeline,
progress tracking and validation are ordinary Python. They are deterministic
problems with exact answers; a model would make them slower, more expensive and
occasionally wrong. The Artifact Manager agent issues no completion at all.

---

## Packaging

### Virtual workspace

Agents never touch the filesystem. Every write goes through `ProjectWorkspace`,
which enforces:

- **Path safety** — traversal, absolute paths, drive letters, null bytes and
  Windows-reserved names are rejected, not silently rewritten.
- **Size limits** — per file and per project.
- **Provenance** — which agent produced each file, and its revision count.

Only the packaging step materialises the tree, as a ZIP with a single top-level
directory and deterministic timestamps.

### The report

`build_report()` produces the structured payload; `render_report_markdown()`
produces the document shipped inside the ZIP.

Effort estimates are **derived and shown**, not asserted. Lines of code are
converted at a published industry average, fixed-cost activities are added for
the artefacts actually delivered, and a ±35% band reflects real variance. The
report prints the basis so a reader can judge the number rather than take it on
faith.

---

## Real-time streaming

```
Agent  →  ctx.progress() / ctx.log()
              ↓
       RunOrchestrator._publish()
          ├── RunEventBus  (in-process fan-out, bounded per-subscriber queue)
          └── run_events   (persisted, unless a high-frequency progress tick)
              ↓
       GET /runs/{id}/stream
          1. replay persisted history after `?after=<sequence>`
          2. tail live events, suppressing anything already replayed
          3. heartbeat every 20s to survive intermediary timeouts
```

A slow consumer drops its own oldest events rather than applying backpressure to
the run. Progress ticks are broadcast but not persisted — they are only
meaningful live, and writing every one would bloat the log without making run
history more useful.

On the client, `useRunStream` folds events into agent state and reconnects with
exponential backoff, resuming from the last sequence it saw.

---

## Data model

```
users
  └── projects            idea, slug, cached analysis + stack
        └── generation_runs      status, plan, report, memory snapshot, usage
              ├── agent_executions   per-agent status, timing, tokens, output
              ├── artifacts          versioned deliverables
              └── run_events         durable timeline
```

`JSONType` resolves to native `JSONB` on PostgreSQL and generic `JSON`
elsewhere, so identical models run against both the production database and the
SQLite development fallback.

Ownership is enforced in the query, not by obscurity: `get_owned()` methods join
through to `projects.owner_id`, so a request for another user's resource returns
404 from the database layer rather than relying on a check that could be
forgotten in a route. Integration tests assert this directly.

---

## Decision record

### ADR-01 — The workflow engine is code, not an agent

*Sequencing has a correct answer that a topological sort computes exactly.
Delegating it to a model would trade a guarantee for a probability with no
compensating benefit. The intelligence lives in the agents; the guarantees live
in the engine.*

### ADR-02 — Adapters emit build tooling; agents never do

*Build configuration is fully determined by the technology choice, so there is
nothing for a model to decide. A wrong `tsconfig.json` produces failures a
reader cannot diagnose, which is a disproportionate cost for zero upside.*

### ADR-03 — Two-phase code generation

*A single completion for a whole application truncates and produces dangling
imports. Planning first forces a coherent structure and lets each batch see what
already exists.*

### ADR-04 — `requires` is separate from `depends_on`

*Conflating ordering with requirement meant a failed QA Engineer cascaded into
skipping documentation and packaging, discarding an otherwise complete project.
The integration suite caught this. Only a failed hard requirement now blocks;
a test enforces `requires ⊆ depends_on`.*

### ADR-05 — No vector database in v1

*The shared state is small, structured and fully enumerable. Exact recall beats
similarity search here, and a vector store would add operational weight and
non-determinism for no gain.*

### ADR-06 — SSE over `fetch`, not `EventSource`

*`EventSource` cannot set request headers, so authenticating it would require a
token in the query string — which leaks into browser history, proxy logs and the
`Referer` header. A streamed `fetch` sends a normal `Authorization` header.*

### ADR-07 — PostgreSQL of record, SQLite for development

*A contributor should be able to clone and run without provisioning a database
server. `JSONType` and portable column choices keep the same models working on
both; production configuration is enforced at startup, so the fallback cannot
reach production by accident.*

### ADR-08 — Analysis is synchronous, generation is not

*The user waits on the analysis to review the recommended stack, and it is a
single bounded call. Generation takes minutes and spans many calls, so it runs
as a detached task with its own database session and streams progress.*
