"""Business logic layer.

Services depend on repositories and domain objects, never on FastAPI. This keeps
business rules testable without an HTTP client and reusable outside the API.
"""

from app.services.auth_service import AuthService
from app.services.generation_service import GenerationService
from app.services.orchestration_service import RunOrchestrator, get_orchestrator
from app.services.project_service import ProjectService, derive_name, slugify
from app.services.recommendation_service import RecommendationService, validate_stack

__all__ = [
    "AuthService",
    "GenerationService",
    "ProjectService",
    "RecommendationService",
    "RunOrchestrator",
    "derive_name",
    "get_orchestrator",
    "slugify",
    "validate_stack",
]
