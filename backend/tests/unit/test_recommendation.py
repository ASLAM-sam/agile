"""Technology recommendation scoring."""

from __future__ import annotations

import pytest

from app.adapters.registry import AdapterRegistry
from app.core.enums import ProjectComplexity
from app.services.recommendation_service import RecommendationService, validate_stack
from app.workflow.memory import RequirementAnalysis, TechStack


@pytest.fixture
def service(adapters: AdapterRegistry) -> RecommendationService:
    return RecommendationService(adapters)


def analysis(**overrides: object) -> RequirementAnalysis:
    defaults: dict[str, object] = {
        "needs_authentication": True,
        "needs_database": True,
        "needs_api": True,
        "needs_backend": True,
        "needs_frontend": True,
        "complexity": ProjectComplexity.STANDARD,
        "entities": ["User", "Order"],
    }
    defaults.update(overrides)
    return RequirementAnalysis(**defaults)  # type: ignore[arg-type]


class TestRecommendations:
    def test_recommends_a_complete_stack_for_a_full_project(
        self, service: RecommendationService
    ) -> None:
        result = service.recommend("An inventory management system", analysis())

        assert result.stack.frontend is not None
        assert result.stack.backend is not None
        assert result.stack.database is not None
        assert result.stack.authentication == "JWT"

    def test_omits_layers_the_project_does_not_need(
        self, service: RecommendationService
    ) -> None:
        result = service.recommend(
            "A personal portfolio website",
            analysis(
                needs_authentication=False,
                needs_database=False,
                needs_api=False,
                needs_backend=False,
                complexity=ProjectComplexity.MINIMAL,
                entities=[],
            ),
        )

        assert result.stack.frontend is not None
        assert result.stack.backend is None
        assert result.stack.database is None
        assert result.stack.authentication is None

    def test_every_option_carries_its_reasoning(self, service: RecommendationService) -> None:
        """A recommendation the user cannot interrogate is not useful."""
        result = service.recommend("A CRM system", analysis())

        for options in result.options.values():
            for option in options:
                assert option.reasons, f"{option.key} was ranked without a reason"
                assert all(len(reason) > 10 for reason in option.reasons)

    def test_options_are_ranked_by_score(self, service: RecommendationService) -> None:
        result = service.recommend("A dashboard application", analysis())

        for options in result.options.values():
            scores = [option.score for option in options]
            assert scores == sorted(scores, reverse=True)

    @pytest.mark.parametrize(
        ("idea", "expected_backend"),
        [
            ("An AI-powered document analysis and machine learning platform", "fastapi"),
            ("A real-time chat application with websocket streaming", "express"),
            ("An enterprise banking system with payment compliance", "spring-boot"),
        ],
    )
    def test_domain_signals_steer_the_backend_choice(
        self, service: RecommendationService, idea: str, expected_backend: str
    ) -> None:
        result = service.recommend(
            idea, analysis(complexity=ProjectComplexity.ADVANCED)
        )
        assert result.stack.backend == expected_backend

    def test_seo_signals_steer_towards_server_rendering(
        self, service: RecommendationService
    ) -> None:
        result = service.recommend(
            "A public marketing site with blog content and strong SEO", analysis()
        )
        assert result.stack.frontend == "nextjs"

    def test_postgres_is_preferred_for_substantial_projects(
        self, service: RecommendationService
    ) -> None:
        result = service.recommend(
            "A hospital management system",
            analysis(
                complexity=ProjectComplexity.ADVANCED,
                entities=["Patient", "Doctor", "Appointment", "Ward", "Prescription"],
            ),
        )
        assert result.stack.database == "postgresql"

    def test_recommendation_is_deterministic(self, service: RecommendationService) -> None:
        """The same input must always produce the same recommendation."""
        first = service.recommend("A CRM system", analysis())
        second = service.recommend("A CRM system", analysis())

        assert first.stack.as_dict() == second.stack.as_dict()

    def test_recommended_pair_is_always_compatible(
        self, service: RecommendationService, adapters: AdapterRegistry
    ) -> None:
        for idea in (
            "An AI research platform",
            "A real-time trading dashboard",
            "An enterprise resource planning system",
        ):
            result = service.recommend(idea, analysis(complexity=ProjectComplexity.ENTERPRISE))
            if result.stack.backend and result.stack.database:
                adapter = adapters.backend(result.stack.backend)
                assert adapter.supports_database(result.stack.database)


class TestStackValidation:
    def test_accepts_a_valid_stack(self, adapters: AdapterRegistry) -> None:
        problems = validate_stack(
            adapters,
            TechStack(frontend="react", backend="fastapi", database="postgresql"),
            analysis(),
        )
        assert problems == []

    def test_reports_unknown_technology(self, adapters: AdapterRegistry) -> None:
        problems = validate_stack(
            adapters,
            TechStack(frontend="svelte", backend="fastapi", database="postgresql"),
            analysis(),
        )
        assert any("svelte" in problem for problem in problems)

    def test_reports_missing_required_layer(self, adapters: AdapterRegistry) -> None:
        problems = validate_stack(
            adapters,
            TechStack(frontend="react", backend=None, database="postgresql"),
            analysis(),
        )
        assert any("backend" in problem.lower() for problem in problems)

    def test_reports_incompatible_database(self, adapters: AdapterRegistry) -> None:
        problems = validate_stack(
            adapters,
            TechStack(frontend="react", backend="fastapi", database="mongodb"),
            analysis(),
        )
        assert problems, "an unknown database must be rejected"
