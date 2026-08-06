"""Agent registry.

The single place that knows which engineers exist. The workflow engine reads
this to build an execution plan; nothing else enumerates agents.
"""

from __future__ import annotations

from app.agents.artifact_manager import ArtifactManagerAgent
from app.agents.backend_engineer import BackendEngineerAgent
from app.agents.base import Agent
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.database_engineer import DatabaseEngineerAgent
from app.agents.documentation_engineer import DocumentationEngineerAgent
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.agents.improvement_engineer import ImprovementEngineerAgent
from app.agents.manager import ManagerAgent
from app.agents.qa_engineer import QAEngineerAgent
from app.agents.review_engineer import ReviewEngineerAgent
from app.agents.solution_architect import SolutionArchitectAgent
from app.core.enums import AgentRole

#: Canonical execution order. The workflow engine still resolves `depends_on`
#: and applies skip decisions; this sequence resolves ties between agents whose
#: dependencies leave them equally eligible.
DEFAULT_SEQUENCE: tuple[type[Agent], ...] = (
    ManagerAgent,
    BusinessAnalystAgent,
    SolutionArchitectAgent,
    DatabaseEngineerAgent,
    BackendEngineerAgent,
    FrontendEngineerAgent,
    QAEngineerAgent,
    ReviewEngineerAgent,
    ImprovementEngineerAgent,
    DocumentationEngineerAgent,
    ArtifactManagerAgent,
)


class AgentRegistry:
    """Instantiates and indexes the engineering team."""

    def __init__(self, agent_types: tuple[type[Agent], ...] = DEFAULT_SEQUENCE) -> None:
        self._ordered: list[Agent] = [agent_type() for agent_type in agent_types]
        self._by_role: dict[AgentRole, Agent] = {agent.role: agent for agent in self._ordered}

        if len(self._by_role) != len(self._ordered):
            raise ValueError("Two agents were registered with the same role.")

    def all(self) -> list[Agent]:
        """Every agent, in canonical order."""
        return list(self._ordered)

    def get(self, role: AgentRole) -> Agent:
        agent = self._by_role.get(role)
        if agent is None:
            raise KeyError(f"No agent registered for role '{role.value}'.")
        return agent

    def roles(self) -> list[AgentRole]:
        return [agent.role for agent in self._ordered]

    def describe(self) -> list[dict[str, str]]:
        """Team roster for the UI."""
        return [
            {
                "role": agent.role.value,
                "display_name": agent.display_name,
                "description": agent.description,
                "depends_on": ", ".join(r.value for r in agent.depends_on),
            }
            for agent in self._ordered
        ]

    def __len__(self) -> int:
        return len(self._ordered)


_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Process-wide agent registry singleton."""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
