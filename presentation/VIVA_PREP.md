# AgileAgent — Complete Project Reference (Viva Preparation)

Everything the project is and does, as of 22 August 2026. Paste this into an AI
tool to generate practice questions, or read it straight through.

---

## 1. IDENTITY

**Name:** AgileAgent
**Full title:** Multi-Agent AI Software Engineering Platform for Autonomous Software Development
**Team:** Mohammed Abdul Akif Ahmed (245123733173), Mohammed Aslam Uddin (245123733182), Puneeth Reddy (245123733186)
**Guide:** V. Swarna
**Department:** Computer Science & Engineering, M V S R Engineering College (A)

**One sentence:** AgileAgent turns a plain-language software idea into a
complete, reviewed, documented, downloadable project by coordinating eleven
specialised AI agents under a deterministic workflow engine.

---

## 2. WHAT IT IS NOT (memorise these — they are the most common questions)

| Question | Answer |
|---|---|
| Do you train a model? | **No.** No dataset, no training, no weights, no epochs, no gradients. The platform orchestrates pre-trained models through APIs. |
| What is your accuracy / F1? | **Does not apply** — nothing is trained. Evaluation is system-level (see §11). |
| Is it a chatbot? | **No.** A chatbot waits for your next message. AgileAgent takes one input and runs eleven agents autonomously to completion. |
| Do you use RAG? | **No, deliberately.** See §7. |
| Is it just a wrapper? | **No.** See §14. |

---

## 3. THE PROBLEM

Four defects in current AI-assisted development:

1. **No shared context.** Each prompt starts blind; the developer carries decisions between them.
2. **No traceability.** Nothing links a generated file back to the requirement that justified it.
3. **Single-model dependency.** One quota, rate limit or outage aborts a long generation entirely.
4. **Unverified output.** Code arrives without review, structural validation or tests.

**Net effect:** AI accelerates typing but not engineering. The integration burden moves onto the developer.

---

## 4. THE ELEVEN AGENTS

| # | Agent | Responsibility | Runs when |
|---|---|---|---|
| 1 | Manager | Names project, delivery approach, success criteria | Always |
| 2 | Business Analyst | SRS, requirements, user stories, **capability decisions** | Always |
| 3 | Solution Architect | Architecture, modules, layers, folder structure, API contract | Always |
| 4 | Database Engineer | Schema, relationships, indexes, migrations | Data persists |
| 5 | Backend Engineer | APIs, services, data access, validation, auth | Server logic needed |
| 6 | Frontend Engineer | Pages, routing, components, API integration | UI needed |
| 7 | QA Engineer | Structural validation and unit tests | Code was generated |
| 8 | AI Review Engineer | Architectural, security and correctness review | Enough source to review |
| 9 | Code Improvement Engineer | Applies the review findings | Review found issues |
| 10 | Documentation Engineer | README, installation, API docs, developer guide | Always |
| 11 | Artifact Manager | Compose file, ignore rules, manifest, package | Always |

Two things are deliberately **not** agents: the Workflow Engine sequences
execution in ordinary code, and the Artifact Manager derives Compose files and
manifests mechanically from state already in memory. A guarantee beats a
probability.

---

## 5. THE FIVE CAPABILITY QUESTIONS

The Business Analyst answers these, and the answers decide which agents run:

- Does anything need to persist between sessions? → **database**
- Do different people see different data? → **authentication**
- Must a client exchange data with a server? → **API** and **backend**
- Is there a user interface? → **frontend**

Worked examples:

| Project | Agents engaged | Skipped |
|---|---|---|
| Hospital management system | 11 of 11 | — |
| Portfolio website | 9 of 11 | Database Engineer, Backend Engineer |

Every skipped agent is displayed **with its reason**. The decision is legible,
not mysterious.

---

## 6. THE PIPELINE (ten steps)

1. **Idea intake** — user describes software in plain language
2. **Intent guard** — non-software input is refused before any agent starts (§12)
3. **Requirement analysis** — Business Analyst produces SRS + capability decisions
4. **Technology recommendation** — stacks scored against requirements, each ranking explained
5. **Stack review** — user may override any layer
6. **Workflow planning** — execution order by topological sort of agent dependencies
7. **Deterministic scaffolding** — build tooling emitted by code, no model involved
8. **Dynamic agent execution** — only required agents run, over shared memory
9. **Two-phase code generation** — file manifest, then contents in ordered batches
10. **Review → improvement → packaging** — ZIP, manifest, engineering report

Progress streams live over Server-Sent Events throughout.

---

## 7. SHARED PROJECT MEMORY (why not RAG)

One typed state object threads through every agent. The Backend Engineer sees
the schema the Database Engineer designed; the Documentation Engineer sees
everything.

| | RAG | Shared Project Memory |
|---|---|---|
| Retrieval | Approximate, by vector similarity | Exact, by direct field access |
| Storage | Vector database | One typed object |
| Failure mode | Retrieves the wrong chunk | Cannot — you asked for a named field |

**The defence:** RAG solves finding relevant information in a large unstructured
corpus. We do not have that problem. Our state is small, structured and fully
enumerable, so exact recall beats similarity search. RAG becomes necessary only
when we extend the system to learn from previously generated projects or index
external framework documentation — which is listed as future scope.

---

## 8. THE DETERMINISTIC / AI BOUNDARY

**Adapters emit build tooling** — `package.json`, `tsconfig.json`,
`vite.config.ts`, `pyproject.toml`, Dockerfiles, nginx configs. Hand-verified,
version-pinned. Agents never generate build configuration.

**Agents generate application logic** — pages, components, routes, services,
repositories, schema, tests.

**Why:** a subtly wrong build file breaks a project in ways a reader cannot
diagnose. Ask a chat model for a `package.json` and it invents dependency
versions that look right and do not resolve. This boundary converts a
probability into a guarantee.

---

## 9. TWO-PHASE CODE GENERATION

- **Phase 1 — Plan:** emit a file manifest (paths, purpose, dependencies, order)
- **Phase 2 — Generate:** produce contents in ordered batches, each batch seeing
  the manifest and the paths already written

**Why:** a single completion for an entire application reliably truncates and
produces files importing modules the model never wrote. This is a context-window
limit, not a prompting problem.

---

## 10. LLM ORCHESTRATION (the strongest differentiator)

Every model call passes through one Provider Manager. **No agent addresses a
provider directly** — that single constraint is what makes failover automatic.

**Pipeline:** `Cache → Route → Retry → Fail over → Record`

**Six providers:** Gemini · Groq · NVIDIA NIM · Ollama · OpenAI · Anthropic

**Priority is decided in four steps:**

1. **Base order** from configuration — `LLM_PROVIDER` first, then `LLM_PROVIDER_PRIORITY`
2. **Health filter** — cooling-down, unconfigured and disabled providers removed
3. **Task-based reordering** — the calling agent's role implies a task kind:
   - Code / reasoning / review → gemini, anthropic, openai, nvidia, groq, ollama
   - Documentation / summary → groq, gemini, nvidia, ollama, openai, anthropic
   - *Reason:* writing a README is not worth spending a scarce reasoning quota
4. **Capacity check** — providers whose token budget cannot hold the prompt are
   moved to the back, never dropped

**On failure:** retry with exponential backoff and jitter (transient errors
only) → fail over to the next provider → cool the failed one down (300 s after
a quota or rejected key, 60 s after 3 consecutive failures).

**Failure classification** — the whole design turns on one question per failure:

| Kind | Meaning | Action |
|---|---|---|
| RETRYABLE | Timeout, connection error, 5xx | Retry the same provider |
| QUOTA | Rate limited or out of credit | Next provider; cool this one down |
| AUTH | Credentials rejected | Next provider; retrying cannot help |
| UNAVAILABLE | Model missing, prompt too large, refusal | Next provider |
| FATAL | The request itself is malformed | Stop — every provider rejects it identically |

**Prompt cache:** keyed on content, not vendor — so an answer from one provider
serves a request routed to another.

---

## 11. EVALUATION METRICS (there is no accuracy — nothing is trained)

- Artifact completeness
- Structural validity of generated code
- Build success rate
- Per-agent success rate
- Failover recovery rate
- End-to-end generation latency
- Token cost per project

---

## 12. INPUT INTENT GUARD

The platform accepts a software brief, not a conversation. A greeting reaching
the Business Analyst comes back as an **invented project**, because its output
schema has no shape for "this is not one" — and eleven agents then build it.

**Length is not the signal.** "hi" is 2 characters; "hello, I hope you are well,
how do you work?" is 47. Any threshold that rejects the second also rejects
"A todo app". Intent must be judged, not measured.

**Two layers:**
1. **Screening** — free, instant, no model call. Rejects unambiguous
   conversation, admits unambiguous briefs, defers on anything subtle.
2. **Classification** — one small structured model call for the remainder.

**Bias:** rejecting a genuine brief is worse than admitting a doubtful one, so
layer two **fails open** — if classification cannot complete, the request
proceeds. Screening still refuses what it has already judged.

**Prompt injection** ("ignore all previous instructions…") is refused at layer
one, and the classifier is told that text arguing with its rules is input to be
classified, not an instruction to obey.

---

## 13. ARCHITECTURE

**Backend layering, strict one-way dependency:**

```
api/          HTTP only: routing, serialisation, status codes
  ↓
services/     Business logic. Never imports FastAPI.
  ↓
repositories/ All SQL. Accepts an AsyncSession.
  ↓
models/       SQLAlchemy 2.0 typed ORM
```

**Four subsystems carrying the capability:**

| Subsystem | Role |
|---|---|
| `agents/` | The eleven engineers; each declares its skip rule and prompt |
| `workflow/` | Shared memory, topological planner, execution engine, event bus, intent guard |
| `adapters/` | Plugin technology system: scaffolds, conventions, containers |
| `packaging/` | Virtual workspace, ZIP builder, Compose generation, reporting |

**Ordering vs. requirement** — two kinds of dependency, deliberately separated:
- `depends_on` = **ordering** ("run me after X so I can see its output")
- `requires` = **hard requirement** ("I cannot function without X")

Only a failed `requires` blocks an agent. Conflating them means one
non-essential failure (say the QA Engineer) cascades into skipping documentation
and packaging, discarding an otherwise complete project. A test enforces that
`requires` is always a subset of `depends_on`.

**Live streaming** — events broadcast over SSE and persisted simultaneously. A
client that reconnects replays from its last sequence number with no gap. Uses
`fetch` + `ReadableStream` rather than `EventSource`, because `EventSource`
cannot set request headers — the only way to authenticate it would be a token in
the query string, which leaks into browser history, proxy logs and the `Referer`
header.

---

## 14. TECHNOLOGY

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic, JWT, httpx, pytest
**Frontend:** React 18, TypeScript (strict), Vite, Tailwind CSS, SSE, Vitest
**Database:** PostgreSQL 16 (SQLite for local development)
**Infrastructure:** Docker, Docker Compose, non-root containers
**Testing:** 406 backend tests, 43 frontend tests — all hermetic, none touch the network

**Stacks the platform can generate:**
- Frontend: React 18 · Next.js 15 · Angular 18
- Backend: FastAPI · Express.js · Spring Boot 3.4
- Database: PostgreSQL 16 · MySQL 8.4 · SQLite 3

**Extensibility:** adding a technology is one file plus one registration line.
Adding a model provider that speaks the OpenAI protocol is a config change —
NVIDIA NIM was added as a registry entry and a settings block, with no change to
the manager, the agents, or anything above the LLM layer.

---

## 15. RELATED RESEARCH

**Closest work:**
- **MetaGPT** (Hong et al., 2023) — SOP-encoded multi-agent roles. *Limitation:* fixed waterfall for every input; single LLM backend.
- **ChatDev** (Qian et al., 2023) — chat-chain virtual software company. *Limitation:* toy scale; build config LLM-written; correctness unverified.
- **AgileCoder** (Nguyen et al., 2024) — multi-agent development on Agile sprints. *Note the name similarity.*

**Second literature we touch that they do not:**
- **FrugalGPT** (Chen, Zaharia & Zou, 2023) — LLM cascades for cost reduction
- **RouteLLM** (Ong et al., 2024) — routing between strong and weak models
- **GPTCache** (Bang, 2023) — semantic caching of LLM calls

**Foundations:** Codex (Chen et al., 2021) · ReAct (Yao et al., 2022) ·
Self-Refine (Madaan et al., 2023) and Reflexion (Shinn et al., 2023) — the basis
for our review→improve loop · SWE-bench (Jimenez et al., 2023)

**Research gap:** existing multi-agent frameworks (a) run a fixed pipeline
regardless of need, (b) depend on one provider, (c) let the model write build
configuration, (d) return code with no review pass or traceability. AgileAgent
addresses all four.

**Honest positioning:** the multi-agent SDLC concept is *not* novel — MetaGPT
and ChatDev established it in 2023. Our contribution is the combination of
capability-driven assignment, provider-resilient orchestration, the
deterministic build boundary, and decision traceability.

---

## 16. THE "WHY NOT JUST PAY FOR CHATGPT" ANSWER

> "You're right that you can. But notice what you described — *you* would be
> doing it. AgileAgent doesn't compete with ChatGPT; it **calls** it. ChatGPT is
> a component inside my system, not an alternative to it."

Five differences:
1. **Truncation is a hard wall.** By file 30 the model has forgotten file 5's function signature. Two-phase generation exists because of it.
2. **You are the integrator.** Forty files still have to be created, pasted and wired by hand.
3. **Build files: guaranteed vs. probable.** Ours are emitted by pinned code; a chat model invents versions that do not resolve.
4. **A paid account is a single point of failure.** A subscription raises the cap on the same one provider; it does not add resilience.
5. **Conversation vs. pipeline.** Same prompt twice in ChatGPT gives two structures. Ours has stages, a dependency graph, a review pass and a report.

**Never claim:** better output quality (same models), that ChatGPT "cannot" do
it, or cost savings without measurements.

---

## 17. HONEST LIMITATIONS

- Output is a **production-oriented starter project**, not a finished product. Review before deploying.
- Only React / Next.js / Angular are available as frontends — **no plain HTML/CSS/JavaScript adapter yet**.
- No empirical evaluation of generated-project build success has been published yet.
- Out of scope in v1: cloud deployment, CI/CD generation, GitHub push, vector memory, multi-tenant SaaS isolation.

---

## 18. LIKELY VIVA QUESTIONS

1. Where is your dataset and what is your accuracy? → §2, §11
2. How is this different from MetaGPT / ChatDev? → §15
3. Why not RAG? → §7
4. Why eleven agents instead of one large prompt? → §9
5. What happens when a model API fails? → §10
6. Why is build configuration not AI-generated? → §8
7. Is the generated code production-ready? → §17 (answer: no, and say so)
8. What if I type "hello" into your system? → §12
9. How do you decide which agents run? → §5
10. What is `depends_on` vs `requires`? → §13
11. Why SSE and not WebSockets or EventSource? → §13
12. How would you add a new technology or provider? → §14
