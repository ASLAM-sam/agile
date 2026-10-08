"""Business Analyst agent.

Produces the SRS and, critically, the capability decisions that determine which
other agents run. A portfolio site gets no database engineer; a banking system
gets all of them. Every downstream skip decision traces back to this output.
"""

from __future__ import annotations

from app.agents.base import Agent
from app.agents.context import AgentContext
from app.agents.results import AgentResult, SkipDecision
from app.core.enums import AgentRole, ProjectComplexity
from app.llm import schema as s
from app.workflow.memory import RequirementAnalysis

ANALYSIS_SCHEMA = s.obj(
    {
        "executive_summary": s.string(
            "Two to three sentences a non-technical stakeholder would understand: "
            "what is being built and what problem it solves."
        ),
        "project_overview": s.string(
            "One to two paragraphs describing the product, its users and its value."
        ),
        "scope_in": s.string_array("Capabilities explicitly included in this build."),
        "scope_out": s.string_array(
            "Capabilities explicitly excluded, so expectations are bounded."
        ),
        "actors": s.string_array(
            "Distinct human or system actors, e.g. 'Patient', 'Administrator'."
        ),
        "entities": s.string_array(
            "Core domain nouns that will likely become tables or models, singular "
            "and PascalCase, e.g. 'Patient', 'Appointment'."
        ),
        "functional_requirements": s.array(
            s.obj(
                {
                    "id": s.string("Stable identifier, e.g. 'FR-01'."),
                    "title": s.string("Short imperative title."),
                    "description": s.string("What the system must do, precisely."),
                    "priority": s.string(
                        "Priority level.", enum=["must", "should", "could"]
                    ),
                    "module": s.string("Owning module, e.g. 'Appointments'."),
                }
            ),
            description="8 to 20 functional requirements covering the core domain.",
        ),
        "non_functional_requirements": s.array(
            s.obj(
                {
                    "id": s.string("Stable identifier, e.g. 'NFR-01'."),
                    "category": s.string(
                        "Quality attribute.",
                        enum=[
                            "performance",
                            "security",
                            "usability",
                            "reliability",
                            "maintainability",
                            "scalability",
                            "accessibility",
                        ],
                    ),
                    "requirement": s.string("The requirement, stated measurably."),
                }
            ),
            description="5 to 10 non-functional requirements with measurable targets.",
        ),
        "user_stories": s.array(
            s.obj(
                {
                    "id": s.string("Stable identifier, e.g. 'US-01'."),
                    "story": s.string("As a <actor>, I want <goal>, so that <benefit>."),
                    "acceptance_criteria": s.string_array(
                        "2 to 4 testable Given/When/Then criteria."
                    ),
                }
            ),
            description="6 to 15 user stories covering the primary journeys.",
        ),
        "use_cases": s.array(
            s.obj(
                {
                    "id": s.string("Stable identifier, e.g. 'UC-01'."),
                    "name": s.string("Use case name."),
                    "actor": s.string("Primary actor."),
                    "main_flow": s.string_array("Numbered steps of the happy path."),
                    "alternate_flow": s.string("Notable exception path. May be empty."),
                }
            ),
            description="4 to 10 use cases.",
        ),
        "assumptions": s.string_array("Assumptions made where the idea was ambiguous."),
        "clarifications": s.string_array(
            "Questions only worth asking if genuinely blocking. Usually empty — "
            "prefer a documented assumption over a question."
        ),
        "capabilities": s.obj(
            {
                "needs_authentication": s.boolean(
                    "True only if the system has distinct users whose data or "
                    "permissions must be separated. A public brochure or portfolio "
                    "site does NOT need authentication."
                ),
                "needs_database": s.boolean(
                    "True only if data must persist between sessions. A static "
                    "marketing or portfolio site does NOT need a database."
                ),
                "needs_api": s.boolean(
                    "True if a client must exchange data with a server over HTTP."
                ),
                "needs_backend": s.boolean(
                    "True if server-side logic is required. False for purely static "
                    "or client-only sites."
                ),
                "needs_frontend": s.boolean(
                    "True if the system has a user interface. Almost always true."
                ),
            }
        ),
        "complexity": s.string(
            "Overall build complexity.",
            enum=["minimal", "standard", "advanced", "enterprise"],
        ),
        "rationale": s.string(
            "Explain each capability decision in one or two sentences. State "
            "explicitly why anything was judged unnecessary."
        ),
    }
)


class BusinessAnalystAgent(Agent):
    role = AgentRole.BUSINESS_ANALYST
    display_name = "Business Analyst"
    description = (
        "Turns a plain-language idea into a Software Requirements Specification "
        "and decides which capabilities the system actually needs."
    )

    def should_execute(self, ctx: AgentContext) -> SkipDecision:
        """Skip when the project was already analysed before the run started.

        The user reviews this analysis and chooses a technology stack against
        it. Re-deriving it here would risk producing different capability
        decisions from the ones they approved — a run that silently drops the
        database the user was shown, or adds one they were not. Re-analysing
        also bills a second time for an answer already in hand.
        """
        if ctx.memory.analysis.functional_requirements:
            return SkipDecision.skip(
                "Requirements were analysed and approved before this run started."
            )
        return SkipDecision.run()

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
ROLE: Business Analyst

You convert a plain-language software idea into a rigorous Software \
Requirements Specification, and you make the capability decisions that \
determine how the rest of the team works.

## Your most consequential output

The `capabilities` object decides which engineers are assigned to this project. \
Getting it wrong wastes effort or leaves the project incomplete. Judge the idea \
on its merits — do not assume every project needs every capability.

Worked examples of correct judgement:

- "Portfolio website" — a personal showcase. No accounts, no persisted data, no \
server logic. needs_authentication=false, needs_database=false, \
needs_api=false, needs_backend=false, needs_frontend=true.
- "Restaurant landing page" — marketing content, possibly a menu. Static. \
Same decisions as the portfolio.
- "Hospital management system" — staff and patients with different permissions, \
records that must persist. All capabilities true.
- "Blog with comments" — comments persist and need moderation. \
needs_database=true, needs_api=true, needs_backend=true; \
needs_authentication=true only for the author/admin.
- "Calculator" or "unit converter" — pure client-side computation. \
Frontend only.
- "Inventory management system" — stock levels persist, staff have roles. \
All capabilities true.

The test for `needs_database` is simple: *if the browser is closed and \
reopened, must anything the user did still be there?* If no, there is no \
database.

The test for `needs_authentication` is: *do different people see different \
data, or can some people do things others cannot?* If no, there is no \
authentication.

## Requirements quality

- Functional requirements describe behaviour, not implementation. "The system \
shall allow a receptionist to book an appointment for a patient" — not "add a \
POST /appointments endpoint".
- Non-functional requirements must be measurable. "Search results return within \
500 ms for up to 10,000 records" — not "the system should be fast".
- Acceptance criteria must be testable. Someone must be able to read one and \
know unambiguously whether it passes.
- `entities` should list the domain nouns that will become tables or models. \
Singular, PascalCase. This list is used directly by the Database Engineer, so \
be thorough and accurate.

## Ambiguity

Resolve ambiguity yourself and record the choice in `assumptions`. A generated \
project with a clearly documented assumption is far more useful than one that \
stalls on a question. Use `clarifications` only when proceeding under any \
assumption would produce something actively wrong."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        await ctx.progress(self.role, 10, "Reading the idea and identifying the domain")

        completion = await ctx.llm.complete_structured(
            self.build_prompt(
                ctx,
                instruction=(
                    "Analyse this software idea and produce the complete "
                    f"requirements specification:\n\n{ctx.memory.idea}\n\n"
                    "Think carefully about which capabilities this specific "
                    "project genuinely needs before deciding. Justify every "
                    "capability decision in the rationale. If the idea explicitly "
                    "specifies client-only architecture, browser localStorage or no backend "
                    "services, set needs_database=false, needs_backend=false, and needs_api=false."
                ),
                schema=ANALYSIS_SCHEMA,
                include_files=False,
                max_tokens=24000,
            )
        )

        await ctx.progress(self.role, 75, "Structuring requirements and scope")

        analysis = RequirementAnalysis.from_dict(completion.data)

        # A system with a database or API necessarily has a backend. The model
        # occasionally marks these inconsistently; reconcile rather than
        # propagate a contradiction into the workflow plan.
        if (analysis.needs_database or analysis.needs_api) and not analysis.needs_backend:
            analysis.needs_backend = True
            ctx.memory.add_note(
                "Reconciled capabilities: a database or API implies a backend."
            )
        if analysis.needs_backend and not analysis.needs_api:
            analysis.needs_api = True

        ctx.memory.analysis = analysis

        capability_line = ", ".join(
            name
            for name, enabled in (
                ("authentication", analysis.needs_authentication),
                ("database", analysis.needs_database),
                ("API", analysis.needs_api),
                ("backend", analysis.needs_backend),
                ("frontend", analysis.needs_frontend),
            )
            if enabled
        )
        await ctx.log(
            self.role,
            f"Capabilities required: {capability_line or 'frontend only'}",
            requirements=len(analysis.functional_requirements),
            stories=len(analysis.user_stories),
            entities=len(analysis.entities),
        )

        confidence = self._confidence(analysis)
        ctx.memory.record_confidence("requirements", confidence)

        summary = (
            f"{len(analysis.functional_requirements)} functional and "
            f"{len(analysis.non_functional_requirements)} non-functional requirements, "
            f"{len(analysis.user_stories)} user stories, "
            f"{len(analysis.use_cases)} use cases. "
            f"Complexity: {analysis.complexity.value}."
        )
        ctx.memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Requirements specification complete")

        return AgentResult(
            role=self.role,
            summary=summary,
            output=analysis.as_dict(),
            usage=completion.usage,
            confidence=confidence,
        )

    @staticmethod
    def _confidence(analysis: RequirementAnalysis) -> float:
        """Score analysis completeness against expected coverage."""
        checks = (
            len(analysis.functional_requirements) >= 8,
            len(analysis.non_functional_requirements) >= 5,
            len(analysis.user_stories) >= 6,
            len(analysis.use_cases) >= 4,
            bool(analysis.entities) or not analysis.needs_database,
            bool(analysis.executive_summary),
            bool(analysis.scope_in),
            bool(analysis.rationale),
            bool(analysis.actors),
            analysis.complexity != ProjectComplexity.MINIMAL
            or len(analysis.functional_requirements) >= 4,
        )
        return round(sum(checks) / len(checks), 3)
