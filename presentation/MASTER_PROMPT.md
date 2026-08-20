# Master Prompt — AgileAgent Abstract Seminar Deck

Paste everything between the `====` markers into Gamma, Canva, ChatGPT, Claude,
or any other deck generator. Appendix A at the bottom has a short paragraph to
append depending on which tool you use.

> ### ⚠️ Read this before you submit
>
> **Verify every citation on Slide 7 yourself.** The five papers below are real
> and directly relevant, but you must confirm the author list, year, venue and
> title against the actual paper before putting them in front of an examiner. A
> wrong citation in a viva costs more than a missing one.
>
> **Confirm the academic year.** This prompt says 2026–27, inferred from your
> 22-08-2026 seminar date. Change it if your department notice says otherwise.

---

====

You are an expert academic presentation designer. Produce a **12-slide Final
Year Major Project Abstract Seminar presentation** for a Computer Science
engineering department. Follow the structure below **exactly** — the slide
order and slide titles are prescribed by the department and must not be
changed, merged, reordered, or added to.

## HARD CONSTRAINTS

1. **Exactly 12 slides.** No agenda slide, no thank-you slide, no filler.
2. **The project is named `AgileAgent`.** Use this name and only this name
   throughout. Never substitute, abbreviate, or invent an alternative name.
3. **Maximum 6 bullets per slide, maximum 14 words per bullet.** The department
   explicitly penalises lengthy text.
4. **Prefer visuals.** Every slide that can carry a diagram, table, flowchart or
   comparison matrix must do so instead of prose. Each slide below has a
   `VISUAL:` line stating what to draw — follow it.
5. **Total speaking time 8–10 minutes.** Write speaker notes for each slide and
   keep the whole deck within that budget.
6. **Write in proposal framing** — "the proposed system will…", not "we built…".
   This is an *abstract* seminar presenting planned work.
7. **Maintain a visible thread** between Slide 3 (Problem), Slide 6
   (Objectives), Slide 5 (Proposed System) and Slide 8 (Methodology). Each must
   visibly answer the one before it. The department checks for this explicitly.

---

## SLIDE 1 — Title Slide

Reproduce this block **verbatim**. Do not reword, reorder or embellish it.

```
AgileAgent
Multi-Agent AI Software Engineering Platform for Autonomous Software Development

Team Members:
Mohammed Abdul Akif Ahmed   — 245123733173
Mohammed Aslam Uddin        — 245123733182
Puneeth Reddy               — 245123733186

Guide: V. Swarna
Department of Computer Science & Engineering
M V S R Engineering College (A)
Academic Year 2026–27
```

VISUAL: Centred title, project name largest. No image.

---

## SLIDE 2 — Introduction

Domain: AI-assisted software engineering and autonomous multi-agent systems.

Content to use:
- Software development spans requirements, design, coding, testing and
  documentation — a chain of dependent decisions, not a single task.
- Large language models can now write correct code, but assist at the level of a
  function or a file.
- The developer remains the integrator, carrying context between every prompt.
- Multi-agent systems — several specialised LLM agents with distinct roles —
  are the emerging response to this gap.
- AgileAgent applies that idea to the complete software development lifecycle.

VISUAL: A left-to-right band showing the SDLC (Requirements → Design → Code →
Test → Document) with a small "LLM assists here" marker sitting under only the
Code stage, making the uncovered stages obvious at a glance.

---

## SLIDE 3 — Problem Statement

Content to use — four concrete defects in current AI-assisted development:
- **No shared context.** Each prompt starts blind; the developer manually
  carries decisions between them.
- **No traceability.** Nothing links a generated file back to the requirement
  that justified it.
- **Single-model dependency.** One rate limit, quota exhaustion or outage aborts
  a long generation with no recovery.
- **Unverified output.** Code arrives without review, without structural
  validation, and without tests.
- **Consequence:** AI accelerates typing but not engineering; the integration
  burden simply moves to the developer.

VISUAL: Four red-outlined problem cards in a 2×2 grid, each with an icon and a
one-line consequence underneath.

---

## SLIDE 4 — Existing System

Present as a comparison table with these exact columns:
**Approach | How it works | Limitation**

| Approach | How it works | Limitation |
|---|---|---|
| GitHub Copilot, Cursor | Inline completion inside the editor | Snippet scope; produces no SDLC artifacts, no requirements, no docs |
| ChatGPT / Claude chat | Whole application requested in one conversation | Long completions truncate; generated files import modules never written |
| MetaGPT, ChatDev, AutoGen | Multi-agent research frameworks with role play | Fixed pipeline for every input; single LLM backend; build files LLM-generated |
| Low-code platforms | Template assembly through a visual builder | Fixed templates; no real source ownership or architectural control |

Add one closing line beneath the table:
"Common gap: no shared project state, no provider resilience, and no verification
of what was produced."

VISUAL: The table itself, with the Limitation column tinted red.

---

## SLIDE 5 — Proposed System

One-line definition: **AgileAgent is a platform where eleven specialised AI
engineering agents collaborate under a deterministic workflow engine to turn a
plain-language idea into a complete, reviewed, downloadable software project.**

Map each mechanism directly onto the limitation it removes:

| Limitation (Slide 4) | AgileAgent mechanism |
|---|---|
| No shared context | One typed **Shared Project Memory** threaded through every agent |
| Fixed pipeline | **Capability-driven workflow** — only the agents a project needs, each skip shown with its reason |
| Single-model dependency | **Provider-agnostic LLM layer** — routing, retry, failover and caching across six providers |
| Build files generated by an LLM | **Deterministic scaffolding** — build tooling emitted by hand-verified code, never by a model |
| Unverified output | **Review and improvement pass** plus structural validation and generated tests |

VISUAL: Two-column "Limitation → Mechanism" mapping with arrows. This is the
single most important slide; give it the cleanest layout in the deck.

---

## SLIDE 6 — Objectives & Scope

Five measurable objectives:
1. Design a **multi-agent architecture of eleven specialised roles** operating
   over a single typed shared project state.
2. Build a **capability-driven workflow engine** that assigns only the agents a
   project requires and states an explicit reason for every skipped agent.
3. Implement a **provider-agnostic LLM orchestration layer** with intelligent
   routing, exponential-backoff retry, automatic failover and prompt caching
   across six model providers.
4. Guarantee structural correctness through **deterministically emitted build
   tooling** and **two-phase code generation** (plan a file manifest, then
   generate contents in ordered batches).
5. Deliver a **packaged, reviewed, documented project** with an auditable
   engineering report and downloadable archive.

**Scope — included:** requirement analysis, architecture and database design,
frontend and backend code generation, automated review and improvement, test
generation, documentation, containerisation, packaging.

**Scope — excluded:** cloud deployment and live URLs, CI/CD pipeline generation,
automated GitHub push, vector/semantic memory, multi-tenant SaaS isolation.

VISUAL: Numbered objective cards on the left; a green "In Scope" / grey "Out of
Scope" two-column panel on the right.

---

## SLIDE 7 — Literature Survey & Research Gap

Render as a table with columns:
**Author, Year | Method / Technique | Findings | Limitation**

| Author, Year | Method / Technique | Findings | Limitation |
|---|---|---|---|
| Chen et al., 2021 — *Codex / HumanEval* | LLM trained on public code; function-level benchmark | 28.8% pass@1, approx. 70% pass@100 on HumanEval | Evaluates isolated functions; no multi-file project structure |
| Yao et al., 2022 — *ReAct* | Interleaves reasoning traces with tool actions | Reduces hallucination compared with chain-of-thought alone | Single agent; no role specialisation or persistent artifacts |
| Hong et al., 2023 — *MetaGPT* | Encodes standard operating procedures into agent roles | Outperforms single-agent baselines on software tasks | Fixed waterfall for every input; one LLM backend; no capability-based skipping |
| Qian et al., 2023 — *ChatDev* | Chat-chain "virtual software company" of paired roles | Completes small software in minutes at low cost | Toy-scale outputs; build configuration LLM-generated; correctness unverified |
| Wu et al., 2023 — *AutoGen* | Generic framework of conversable, composable agents | Flexible orchestration across many domains | Developer must design the loop; no SDLC artifacts or packaging |

**Research Gap** (state as a distinct, highlighted block):
Existing multi-agent software-engineering frameworks share four unaddressed
weaknesses — (a) they execute a **fixed pipeline** regardless of what the
project actually requires, (b) they depend on a **single model provider**, so one
quota or outage aborts a long run, (c) they allow the **language model to write
build configuration**, which is where silent, hard-to-diagnose breakage
originates, and (d) they return code with **no review pass and no traceable
artifact set**. AgileAgent is designed to address all four.

VISUAL: The table, with the Research Gap in an accent-coloured box beneath it.

---

## SLIDE 8 — Proposed Methodology

Present as a numbered end-to-end flow:
1. **Idea intake** — the user describes the software in plain language.
2. **Requirement analysis** — the Business Analyst agent produces an SRS and
   answers five capability questions (persistence? multiple user roles?
   client-server exchange? user interface?).
3. **Technology recommendation** — candidate stacks scored against the analysed
   requirements, each ranking explained.
4. **Stack review** — the user may override any layer before execution.
5. **Workflow planning** — execution order derived by topological sort over each
   agent's declared `depends_on` (ordering) and `requires` (hard dependency).
6. **Deterministic scaffolding** — adapters emit build tooling: package
   manifests, build configs, Dockerfiles. No model involvement.
7. **Dynamic agent execution** — only the required agents run, each reading and
   writing the shared project memory.
8. **Two-phase code generation** — each code agent first emits a file manifest,
   then generates contents in ordered batches that see what already exists.
9. **Review and improvement** — a review agent finds file-specific issues; an
   improvement agent applies them.
10. **Packaging** — documentation, container definitions, manifest, engineering
    report and a downloadable archive.

Note alongside: progress streams live to the browser over Server-Sent Events
throughout, and any client that reconnects replays from its last sequence number.

VISUAL: A vertical or serpentine numbered flowchart. Colour steps 6 and 8
differently to mark them as the deterministic, non-LLM stages.

---

## SLIDE 9 — System Architecture / Block Diagram

**This slide must be a diagram. No bullet lists.** Draw four horizontal bands
with labelled arrows between them:

**Band 1 — Client:** React 18 + TypeScript web client. Arrow down labelled
"REST + Server-Sent Events".

**Band 2 — API layer:** FastAPI routes → Services → Repositories → PostgreSQL.
Label the band "strict one-way dependency".

**Band 3 — Core subsystems** (four boxes side by side, all connected to a
central Shared Project Memory box):
- Agent Registry — 11 specialised agents
- Workflow Engine — planner, executor, event bus
- Adapter Registry — 9 technology plugins
- Packaging — workspace, archive, report

**Band 4 — LLM orchestration:** a single `Provider Manager` box, with the
pipeline **Cache → Route → Retry → Failover → Record** shown inside it, fanning
out to six provider boxes: Gemini · Groq · NVIDIA NIM · Ollama · OpenAI ·
Anthropic.

Add a short caption: "Agents never address a provider directly — every model
call passes through one manager, which is what makes failover automatic."

---

## SLIDE 10 — Technologies & Requirements

Group into a compact table or four labelled columns:

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2,
Alembic, JWT authentication, httpx, pytest
**Frontend:** React 18, TypeScript (strict), Vite, Tailwind CSS, Server-Sent
Events over fetch/ReadableStream, Vitest
**Database:** PostgreSQL 16 in production; SQLite for local development
**Model providers:** Google Gemini, Groq, NVIDIA NIM, Ollama (local), OpenAI,
Anthropic — accessed through one provider-agnostic interface
**Infrastructure:** Docker, Docker Compose, non-root containers
**Stacks the platform can generate:** React 18 / Next.js 15 / Angular 18 ·
FastAPI / Express.js / Spring Boot 3.4 · PostgreSQL 16 / MySQL 8.4 / SQLite 3
**Hardware:** standard development machine, 8 GB RAM; hosted provider API keys,
or a local GPU for offline inference

Then add this block under the heading **"Dataset & Evaluation"** — do not omit
it:

> AgileAgent trains no model, so it has no dataset, no preprocessing stage and
> no train/test split. It is an **orchestration system** built on pre-trained
> language models, and its inputs are structured requirement objects rather than
> samples. Evaluation is therefore system-level rather than statistical:
> **artifact completeness**, **structural validity of generated code**, **build
> success rate**, **per-agent success rate**, **failover recovery rate**,
> **end-to-end generation latency**, and **token cost per project**.

VISUAL: Four technology columns with small logos; the Dataset & Evaluation block
in a distinct bordered box beneath them.

---

## SLIDE 11 — Expected Outcomes & Applications

**Expected outcomes:**
- A complete starter project: requirements, architecture, database schema with
  executable DDL, REST API specification, frontend and backend source, tests,
  documentation and container definitions.
- Runs that survive a model provider failing mid-generation, by automatically
  continuing on another provider.
- Every skipped agent reported with the reason it was not required.
- A downloadable archive plus an auditable AI Engineering Report.

**Applications:** startup prototyping · academic project bootstrapping ·
developer onboarding and reference architectures · internal tooling ·
hackathon scaffolding · teaching the software development lifecycle.

**Significance:** AgileAgent moves AI from a snippet-level assistant to an
accountable engineering team — one that records why each decision was taken and
produces a project a developer can own, extend and defend.

VISUAL: Left half — a deliverables checklist with tick icons. Right half — six
small application tiles. Significance as a single highlighted strip along the
bottom.

---

## SLIDE 12 — Work Plan & References

**Project phases** — render as a horizontal timeline or Gantt strip:

| Phase | Period | Work |
|---|---|---|
| 1 | Aug – Sep 2026 | Literature survey, requirement analysis, architecture design |
| 2 | Oct 2026 | Core platform: API layer, authentication, database schema |
| 3 | Nov 2026 | Agent implementation, shared project memory, workflow engine |
| 4 | Dec 2026 – Jan 2027 | LLM orchestration: routing, retry, failover, caching; technology adapters |
| 5 | Feb 2027 | Web client, live event streaming, monitoring dashboards |
| 6 | Mar 2027 | Packaging, testing, evaluation against defined metrics |
| 7 | Apr 2027 | Documentation, final report, demonstration |

**Team responsibilities:**
- **Mohammed Abdul Akif Ahmed (245123733173)** — LLM orchestration layer,
  provider integration, backend core
- **Mohammed Aslam Uddin (245123733182)** — agent implementation, workflow
  engine, shared project memory
- **Puneeth Reddy (245123733186)** — web client, event streaming, packaging,
  reporting and testing

**References (IEEE format):**
1. M. Chen et al., "Evaluating Large Language Models Trained on Code," *arXiv preprint* arXiv:2107.03374, 2021.
2. S. Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models," in *Proc. ICLR*, 2023.
3. S. Hong et al., "MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework," in *Proc. ICLR*, 2024.
4. C. Qian et al., "ChatDev: Communicative Agents for Software Development," in *Proc. ACL*, 2024.
5. Q. Wu et al., "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation," *arXiv preprint* arXiv:2308.08155, 2023.
6. C. E. Jimenez et al., "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?," in *Proc. ICLR*, 2024.

VISUAL: Timeline across the top two-thirds, references in smaller text at the
bottom.

---

## DESIGN SPECIFICATION

- **Aspect ratio:** 16:9.
- **Palette:** deep navy or charcoal background (#0F172A), off-white body text
  (#E2E8F0), a single accent colour (#38BDF8) used only for headings, arrows and
  emphasis. No gradients behind text.
- **Typography:** one clean sans-serif family (Inter, Calibri or Segoe UI).
  Titles 32–36 pt, body 18–20 pt, table text no smaller than 14 pt — it must be
  readable from the back of a lecture hall.
- **Consistency:** identical title position and slide-number placement on every
  slide.
- **Prohibited:** clip-art, stock photographs of people at laptops, emoji, more
  than two colours of body text, and any text below 14 pt.
- **Speaker notes:** write them for every slide. Budget roughly 45 seconds per
  slide, with 90 seconds for Slides 5 and 9. Total must land inside 10 minutes.

Produce all 12 slides now, in order, with speaker notes for each.

====

---

## Appendix A — Tool-specific additions

Append **one** of these to the end of the prompt above, depending on where you
paste it.

**Gamma / Canva Magic / SlidesAI:**
> Generate one card per slide. Keep every text block under 40 words. For each
> slide, also output a one-line image or diagram prompt matching the VISUAL
> instruction. Use a dark professional theme.

**ChatGPT / Claude:**
> Output the result as markdown, one `##` section per slide, containing: the
> slide title, the bullet text exactly as it should appear, a description of the
> visual to be drawn, and a `Speaker notes:` paragraph. Do not write any prose
> outside this structure — I will paste it directly into PowerPoint.

**If you want the deck rebuilt as a file:**
> Output a complete `python-pptx` script that builds this deck as a `.pptx`,
> using a dark theme, native PowerPoint shapes for all diagrams, and speaker
> notes attached to each slide.

---

## Appendix B — Likely examiner questions

Prepare answers to these. The first three are near-certain.

1. **"Where is your dataset and what are your accuracy metrics?"** — Covered on
   Slide 10. No model is trained; evaluation is system-level. Know the seven
   metrics listed there by name.
2. **"How is this different from ChatDev or MetaGPT?"** — Four differences, all
   on Slide 7: capability-driven rather than fixed pipeline, multi-provider
   rather than single, deterministic build tooling rather than LLM-generated,
   and a review/improvement pass rather than raw output.
3. **"What happens when the model API fails?"** — Retry with exponential backoff
   against the same provider; on quota, authentication or outage errors, fail
   over to the next provider and place the failed one in cooldown. The run
   continues rather than aborting.
4. **"Why eleven agents and not one large prompt?"** — A single completion for a
   whole application truncates and produces files importing modules that were
   never written. Role separation plus a shared memory keeps each output small
   enough to be correct and consistent with the others.
5. **"Is the generated code production-ready?"** — No, and the deck should not
   claim it is. It is a production-*oriented* starter project: complete and
   coherent, requiring review before deployment.
