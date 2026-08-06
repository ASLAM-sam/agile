"""Manager agent.

Opens the run: normalises the project identity, states the delivery approach
and sets the success criteria the team is working toward.

Mechanical orchestration — sequencing, dependency resolution, skip handling —
lives in the `WorkflowEngine`, which is deterministic code. Asking a language
model to decide execution order would trade a guarantee for a probability. The
Manager's contribution is judgement, not scheduling.
"""

from __future__ import annotations

import re

from app.agents.base import Agent
from app.agents.context import AgentContext
from app.agents.results import AgentResult
from app.core.enums import AgentRole
from app.llm import schema as s

BRIEF_SCHEMA = s.obj(
    {
        "project_name": s.string(
            "A concise, professional product name in Title Case, 2 to 5 words. "
            "Derive it from the idea; do not simply echo the idea verbatim."
        ),
        "one_liner": s.string("A single sentence describing what this product is."),
        "delivery_approach": s.string(
            "Two to four sentences on how the team will approach this build and "
            "what the starter project will contain."
        ),
        "success_criteria": s.string_array(
            "4 to 6 concrete, checkable statements that define a successful "
            "delivery for this specific project."
        ),
        "key_risks": s.array(
            s.obj(
                {
                    "risk": s.string("What could go wrong in delivery."),
                    "mitigation": s.string("How the team will handle it."),
                }
            ),
            description="2 to 4 genuine delivery risks for this project.",
        ),
    }
)

_SLUG_INVALID = re.compile(r"[^a-z0-9]+")


class ManagerAgent(Agent):
    role = AgentRole.MANAGER
    display_name = "Manager"
    description = (
        "Opens the engagement: names the project, sets the delivery approach "
        "and defines what a successful delivery looks like."
    )

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
ROLE: Engineering Manager

You open the engagement. Your output frames the work for every engineer who \
follows, and it is what the client reads first.

## Naming

Give the project a name a real product would carry: concise, professional, \
Title Case. "Meridian Clinic Manager" reads like a product; "Build An App For \
Hospital" reads like a ticket title. Derive the name from the domain, do not \
echo the request.

## Success criteria

Write criteria someone could actually check against the delivered project. \
"Users can register, log in, and see only their own records" is checkable. \
"High quality code" is not. Make them specific to *this* project — criteria \
that would apply equally to any software are not doing any work.

## Risks

Name risks that are real for this particular build — an ambiguous requirement, \
a domain rule that needs a decision, a piece of scope that could balloon. Do \
not list generic project-management platitudes. For each, state what the team \
will actually do about it.

Be direct and concise. This is a brief, not a proposal."""

    async def execute(self, ctx: AgentContext) -> AgentResult:
        await ctx.progress(self.role, 25, "Framing the engagement")

        completion = await ctx.llm.complete_structured(
            self.build_prompt(
                ctx,
                instruction=(
                    "Open the engagement for this software idea:\n\n"
                    f"{ctx.memory.idea}\n\n"
                    "Name the project, state the delivery approach, and define what "
                    "a successful delivery looks like for this specific product."
                ),
                schema=BRIEF_SCHEMA,
                include_files=False,
                max_tokens=6000,
            )
        )

        await ctx.progress(self.role, 80, "Recording the delivery brief")

        data = completion.data
        name = str(data.get("project_name", "")).strip()
        if name and 2 <= len(name) <= 80:
            ctx.memory.project_name = name
            ctx.memory.project_slug = self._slugify(name)

        brief = {
            "project_name": ctx.memory.project_name,
            "one_liner": data.get("one_liner", ""),
            "delivery_approach": data.get("delivery_approach", ""),
            "success_criteria": data.get("success_criteria", []),
            "key_risks": data.get("key_risks", []),
        }

        await ctx.log(
            self.role,
            f"Engagement opened: {ctx.memory.project_name}",
            criteria=len(brief["success_criteria"]),
        )

        confidence = round(
            sum(
                (
                    bool(brief["one_liner"]),
                    bool(brief["delivery_approach"]),
                    len(brief["success_criteria"]) >= 4,
                    len(brief["key_risks"]) >= 2,
                )
            )
            / 4,
            3,
        )
        ctx.memory.record_confidence("coordination", confidence)

        summary = f"{ctx.memory.project_name} — {brief['one_liner']}"
        ctx.memory.record_summary(self.role, summary)
        await ctx.progress(self.role, 100, "Delivery brief complete")

        return AgentResult(
            role=self.role,
            summary=summary,
            output=brief,
            usage=completion.usage,
            confidence=confidence,
        )

    @staticmethod
    def _slugify(value: str) -> str:
        slug = _SLUG_INVALID.sub("-", value.lower()).strip("-")
        return (slug or "generated-project")[:60].rstrip("-")
