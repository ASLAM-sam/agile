"""Technology recommendation engine.

Scores every registered adapter against the analysed requirements and returns a
ranked recommendation the user may override. Scoring is deterministic and
explained: each recommendation carries the reasoning that produced it, so the
user is choosing between arguments rather than accepting an opaque verdict.

Because it reads the adapter registry rather than a hardcoded list, a newly
registered adapter is scored automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.adapters.registry import AdapterRegistry
from app.core.enums import AdapterKind, ProjectComplexity
from app.core.logging import get_logger
from app.workflow.memory import RequirementAnalysis, TechStack

logger = get_logger(__name__)


@dataclass(slots=True)
class ScoredOption:
    """One adapter's suitability for the analysed project."""

    key: str
    display_name: str
    score: float
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "score": round(self.score, 3),
            "reasons": self.reasons,
        }


@dataclass(slots=True)
class Recommendation:
    """The full recommendation with ranked alternatives per layer."""

    stack: TechStack
    options: dict[str, list[ScoredOption]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "recommended": self.stack.as_dict(),
            "options": {
                kind: [option.as_dict() for option in ranked]
                for kind, ranked in self.options.items()
            },
        }


# Keyword signals mined from the project idea and requirements. Each maps to a
# score delta for a specific adapter, with the reason shown to the user.
_FRONTEND_SIGNALS: dict[str, list[tuple[str, float, str]]] = {
    "nextjs": [
        ("seo", 3.0, "Server-side rendering gives search engines fully rendered HTML"),
        ("blog", 2.5, "Content sites benefit from static generation and SSR"),
        ("marketing", 2.5, "Marketing pages need fast first paint and good SEO"),
        ("landing", 2.5, "Landing pages benefit from static generation"),
        ("ecommerce", 2.0, "Product pages need to be indexable by search engines"),
        ("e-commerce", 2.0, "Product pages need to be indexable by search engines"),
        ("portfolio", 2.0, "Static generation suits a portfolio's mostly-fixed content"),
        ("public", 1.5, "Public-facing content benefits from server rendering"),
        ("cms", 1.5, "Content management pairs naturally with SSR"),
    ],
    "angular": [
        ("enterprise", 3.0, "Prescriptive structure suits large enterprise teams"),
        ("erp", 2.5, "ERP systems benefit from Angular's enforced conventions"),
        ("banking", 2.0, "Regulated domains benefit from a strongly opinionated framework"),
        ("insurance", 2.0, "Complex forms are Angular's strongest use case"),
        ("large team", 2.0, "Enforced structure scales across many contributors"),
        ("form", 1.5, "Reactive forms handle complex data entry well"),
    ],
    "react": [
        ("react", 5.0, "Direct match for React requirement"),
        ("typescript", 3.0, "TypeScript pairs naturally with React component architecture"),
        ("dashboard", 2.5, "Component model suits data-dense interactive dashboards"),
        ("admin", 2.0, "Rich admin panels benefit from the large component ecosystem"),
        ("realtime", 2.0, "Client-side interactivity is React's strength"),
        ("real-time", 2.0, "Client-side interactivity is React's strength"),
        ("chat", 2.0, "Highly interactive UIs suit a client-rendered SPA"),
        ("interactive", 1.5, "Interactive interfaces benefit from React's ecosystem"),
        ("analytics", 1.5, "Charting and visualisation libraries are richest in React"),
    ],
}

_BACKEND_SIGNALS: dict[str, list[tuple[str, float, str]]] = {
    "fastapi": [
        ("ai", 3.0, "Python is the default language for AI and ML workloads"),
        ("machine learning", 3.0, "Python has the strongest ML ecosystem"),
        ("ml", 2.5, "Python has the strongest ML ecosystem"),
        ("data", 2.5, "Python leads for data processing and analysis"),
        ("analytics", 2.0, "Python's analytical libraries are unmatched"),
        ("recommendation", 2.0, "Recommendation engines are typically built in Python"),
        ("nlp", 2.5, "Natural language processing is Python-dominated"),
        ("report", 1.5, "Python has mature reporting and document libraries"),
    ],
    "express": [
        ("realtime", 3.0, "Node's event loop suits WebSockets and streaming"),
        ("real-time", 3.0, "Node's event loop suits WebSockets and streaming"),
        ("chat", 3.0, "Real-time messaging is a natural fit for Node"),
        ("notification", 2.0, "Push and streaming workloads suit Node"),
        ("streaming", 2.5, "Node handles many concurrent open connections efficiently"),
        ("socket", 2.5, "WebSocket support is first-class in the Node ecosystem"),
    ],
    "spring-boot": [
        ("enterprise", 3.0, "Mature enterprise ecosystem and long-term support"),
        ("banking", 3.0, "Strong transaction management suits financial systems"),
        ("financial", 2.5, "JVM is the established choice in financial services"),
        ("erp", 2.5, "Complex transactional domains suit Spring's capabilities"),
        ("insurance", 2.0, "Regulated industries commonly standardise on the JVM"),
        ("payment", 2.5, "Transactional integrity is critical for payment flows"),
        ("compliance", 2.0, "Enterprise auditing and security tooling is mature on the JVM"),
    ],
}


class RecommendationService:
    """Produces an explained technology recommendation."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def recommend(self, idea: str, analysis: RequirementAnalysis) -> Recommendation:
        """Rank every adapter and select the best fit per layer."""
        corpus = self._corpus(idea, analysis)

        frontend = (
            self._rank(AdapterKind.FRONTEND, _FRONTEND_SIGNALS, corpus, analysis)
            if analysis.needs_frontend
            else []
        )
        backend = (
            self._rank(AdapterKind.BACKEND, _BACKEND_SIGNALS, corpus, analysis)
            if analysis.needs_backend
            else []
        )
        database = self._rank_database(analysis, corpus) if analysis.needs_database else []

        selected_backend = backend[0].key if backend else None
        selected_database = database[0].key if database else None

        # A backend that cannot drive the chosen database is not a valid pair.
        if selected_backend and selected_database:
            adapter = self._registry.backend(selected_backend)
            if not adapter.supports_database(selected_database):
                for candidate in backend:
                    if self._registry.backend(candidate.key).supports_database(selected_database):
                        logger.info(
                            "backend_switched_for_database_compatibility",
                            extra={"from": selected_backend, "to": candidate.key},
                        )
                        selected_backend = candidate.key
                        break

        stack = TechStack(
            frontend=frontend[0].key if frontend else None,
            backend=selected_backend,
            database=selected_database,
            authentication="JWT" if analysis.needs_authentication else None,
            rationale=self._rationale(frontend, backend, database, analysis),
        )

        return Recommendation(
            stack=stack,
            options={
                AdapterKind.FRONTEND.value: frontend,
                AdapterKind.BACKEND.value: backend,
                AdapterKind.DATABASE.value: database,
            },
        )

    # --- scoring ---------------------------------------------------------

    @staticmethod
    def _corpus(idea: str, analysis: RequirementAnalysis) -> str:
        """Searchable text describing the project."""
        parts = [
            idea,
            analysis.executive_summary,
            analysis.project_overview,
            " ".join(analysis.scope_in),
            " ".join(str(r.get("description", "")) for r in analysis.functional_requirements),
            " ".join(str(r.get("requirement", "")) for r in analysis.non_functional_requirements),
            " ".join(analysis.entities),
        ]
        return " ".join(parts).lower()

    def _rank(
        self,
        kind: AdapterKind,
        signals: dict[str, list[tuple[str, float, str]]],
        corpus: str,
        analysis: RequirementAnalysis,
    ) -> list[ScoredOption]:
        scored: list[ScoredOption] = []

        for adapter in self._registry.list_kind(kind):
            # Baseline keeps a sensible default when no signal fires at all.
            score = 5.0
            reasons: list[str] = []

            for keyword, weight, reason in signals.get(adapter.key, []):
                if keyword in corpus:
                    score += weight
                    if reason not in reasons:
                        reasons.append(reason)

            score, extra = self._complexity_adjustment(adapter.key, analysis, score)
            reasons.extend(extra)

            if not reasons:
                reasons.append(f"Solid general-purpose choice: {adapter.description}")

            scored.append(
                ScoredOption(
                    key=adapter.key,
                    display_name=adapter.display_name,
                    score=score,
                    reasons=reasons[:4],
                )
            )

        # Stable tie-break on display name keeps output deterministic.
        return sorted(scored, key=lambda option: (-option.score, option.display_name))

    @staticmethod
    def _complexity_adjustment(
        key: str, analysis: RequirementAnalysis, score: float
    ) -> tuple[float, list[str]]:
        """Nudge scores by project size and shape."""
        reasons: list[str] = []
        complexity = analysis.complexity

        if complexity in {ProjectComplexity.MINIMAL, ProjectComplexity.STANDARD}:
            if key in {"react", "fastapi", "express"}:
                score += 1.5
                reasons.append("Low ceremony keeps a smaller project fast to build")
            if key == "spring-boot":
                score -= 2.0
                reasons.append("Heavier framework than this project's scope warrants")
        else:
            if key in {"spring-boot", "angular"}:
                score += 1.5
                reasons.append("Enforced structure pays off at this scale")

        if not analysis.needs_backend and key == "nextjs":
            score += 1.0
            reasons.append("Static generation covers a project with no backend")

        if len(analysis.functional_requirements) > 15 and key == "angular":
            score += 0.5
            reasons.append("Large feature set benefits from a prescriptive framework")

        return score, reasons

    def _rank_database(self, analysis: RequirementAnalysis, corpus: str) -> list[ScoredOption]:
        scored: list[ScoredOption] = []
        table_estimate = max(len(analysis.entities), 1)
        heavy = analysis.complexity in {
            ProjectComplexity.ADVANCED,
            ProjectComplexity.ENTERPRISE,
        }

        for adapter in self._registry.list_kind(AdapterKind.DATABASE):
            score = 5.0
            reasons: list[str] = []

            if adapter.key == "mongodb":
                score += 2.0
                reasons.append("Document collections support flexible, evolving application data")
                document_signals = (
                    "content", "catalog", "inventory", "event", "feed", "chat", "nested",
                    "document", "flexible", "social", "realtime", "real-time",
                )
                if any(signal in corpus for signal in document_signals):
                    score += 2.0
                    reasons.append("The requirements include document-oriented or evolving data")
                if heavy or table_estimate > 6:
                    score += 1.0
                    reasons.append("A managed document service suits the expected scale and concurrency")
            else:  # sqlite
                if analysis.complexity == ProjectComplexity.MINIMAL and table_estimate <= 5:
                    score += 2.5
                    reasons.append("Zero-configuration and file-backed — right size for this scope")
                elif any(signal in corpus for signal in ("prototype", "mvp", "single-user", "internal tool")):
                    score += 1.5
                    reasons.append("An embedded database keeps this small deployment simple")
                else:
                    score -= 2.0
                    reasons.append(
                        "Serialised writes make it a poor fit for concurrent use at this scale"
                    )

            scored.append(
                ScoredOption(
                    key=adapter.key,
                    display_name=adapter.display_name,
                    score=score,
                    reasons=reasons[:4],
                )
            )

        return sorted(scored, key=lambda option: (-option.score, option.display_name))

    @staticmethod
    def _rationale(
        frontend: list[ScoredOption],
        backend: list[ScoredOption],
        database: list[ScoredOption],
        analysis: RequirementAnalysis,
    ) -> dict[str, str]:
        rationale: dict[str, str] = {}
        if frontend:
            rationale["frontend"] = frontend[0].reasons[0]
        if backend:
            rationale["backend"] = backend[0].reasons[0]
        if database:
            rationale["database"] = database[0].reasons[0]
        if analysis.needs_authentication:
            rationale["authentication"] = (
                "JWT suits a stateless API: no server-side session store, and the "
                "same token works across web and mobile clients"
            )
        return rationale


def validate_stack(
    registry: AdapterRegistry, stack: TechStack, analysis: RequirementAnalysis
) -> list[str]:
    """Check a user-customised stack. Returns human-readable problems."""
    problems: list[str] = []

    if analysis.needs_frontend and not stack.frontend:
        problems.append("This project needs a user interface, so a frontend must be selected.")
    if analysis.needs_backend and not stack.backend:
        problems.append("This project needs server-side logic, so a backend must be selected.")
    if analysis.needs_database and not stack.database:
        problems.append("This project persists data, so a database must be selected.")

    for kind, key in (
        (AdapterKind.FRONTEND, stack.frontend),
        (AdapterKind.BACKEND, stack.backend),
        (AdapterKind.DATABASE, stack.database),
    ):
        if key and not registry.has(kind, key):
            available = ", ".join(registry.keys(kind))
            problems.append(f"Unknown {kind.value} '{key}'. Available: {available}.")

    if stack.backend and stack.database and registry.has(AdapterKind.BACKEND, stack.backend):
        adapter = registry.backend(stack.backend)
        if not adapter.supports_database(stack.database):
            problems.append(
                f"{adapter.display_name} does not support {stack.database}. "
                f"Supported: {', '.join(adapter.supported_databases)}."
            )

    return problems
