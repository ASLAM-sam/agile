"""Deterministic diagnostic generation for partial / failed generation artifacts."""

from __future__ import annotations

from typing import Any

from app.packaging.workspace import ProjectWorkspace

MODEL_ROUTING_CONFIG: dict[str, dict[str, str]] = {
    "PLANNER": {
        "slot": "PLANNER_API_KEY01",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "provider": "openrouter",
    },
    "FRONTEND": {
        "slot": "FRONTEND_API_KEY01",
        "model": "google/gemini-2.5-flash",
        "provider": "gemini",
    },
    "BACKEND": {
        "slot": "BACKEND_API_KEY01",
        "model": "google/gemini-2.5-flash",
        "provider": "gemini",
    },
    "DATABASE": {
        "slot": "DATABASE_API_KEY01",
        "model": "google/gemini-2.5-flash",
        "provider": "gemini",
    },
    "QA": {
        "slot": "QA_API_KEY01",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "provider": "openrouter",
    },
    "REVIEW": {
        "slot": "REVIEW_API_KEY01",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "provider": "openrouter",
    },
    "DEBUG": {
        "slot": "DEBUG_API_KEY01",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "provider": "openrouter",
    },
}


def count_preserved_files(workspace: ProjectWorkspace) -> dict[str, int]:
    """Deterministically count preserved files across frontend, backend, and database layers."""
    frontend = 0
    backend = 0
    database = 0

    for path in workspace.paths:
        norm = path.replace("\\", "/").lower()
        if (
            norm.startswith("frontend/")
            or norm.startswith("src/")
            or norm in {"package.json", "tsconfig.json", "vite.config.ts", "index.html"}
            or norm.endswith((".tsx", ".jsx", ".vue", ".svelte", ".css", ".html"))
        ):
            frontend += 1
        elif (
            norm.startswith("backend/")
            or norm.startswith("app/")
            or norm in {"pyproject.toml", "requirements.txt", "main.py"}
            or norm.endswith((".py", ".go", ".rs", ".java"))
        ):
            backend += 1
        elif (
            norm.startswith("database/")
            or norm.startswith("db/")
            or norm.endswith((".sql", ".prisma", ".migration"))
        ):
            database += 1

    return {
        "frontend": frontend,
        "backend": backend,
        "database": database,
    }


def build_generation_status_readme(
    *,
    failed_stage: str,
    failed_command: str = "None",
    exit_code: int | str = "N/A",
    failure_count: int = 0,
    repair_cycles: int = 0,
    llm_requests_used: int = 0,
    llm_request_limit: int = 15,
    frontend_files: int = 0,
    backend_files: int = 0,
    database_files: int = 0,
) -> str:
    """Generate README-GENERATION-STATUS.md deterministically without using an LLM."""
    return f"""# AEGIS AI — Generation Status: FAILED

## Release Status

RELEASE BLOCKED

This archive contains the current partial project state for debugging and inspection.

It has NOT passed final release validation.

## Failure Summary

- Failed stage: {failed_stage}
- Failed command: {failed_command}
- Exit code: {exit_code}
- Failure count: {failure_count}
- Repair cycles: {repair_cycles}
- LLM requests used: {llm_requests_used} / {llm_request_limit}

## Preserved Work

- Frontend files: {frontend_files}
- Backend files: {backend_files}
- Database files: {database_files}

## Important

This is a partial artifact.

This is NOT production-ready. Do not treat it as production-ready.
"""


def build_diagnostics(
    *,
    generation_id: str,
    failed_stage: str,
    llm_requests_used: int = 0,
    llm_request_limit: int = 15,
    repair_cycles: int = 0,
    files_generated: int = 0,
    files_modified: int = 0,
    commands_passed: list[str] | None = None,
    commands_failed: list[str] | None = None,
    failure_signatures: list[str] | None = None,
    models_used: list[str] | None = None,
    validation_failures: list[dict[str, Any]] | None = None,
    agent_execution_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate deterministic diagnostic payloads matching specification."""
    models = models_used or [
        "nvidia/nemotron-3-super-120b-a12b",
        "google/gemini-2.5-flash",
    ]

    report = {
        "generation_id": generation_id,
        "status": "failed",
        "release_eligible": False,
        "failed_stage": failed_stage,
        "llm_requests_used": llm_requests_used,
        "llm_request_limit": llm_request_limit,
        "repair_cycles": repair_cycles,
        "files_generated": files_generated,
        "files_modified": files_modified,
        "commands_passed": commands_passed or [],
        "commands_failed": commands_failed or [],
        "failure_signatures": failure_signatures or [],
        "models_used": models,
    }

    return {
        "generation_report": report,
        "validation_failures": validation_failures or [],
        "agent_execution_log": agent_execution_log or [],
        "failure_signatures": failure_signatures or [],
        "model_routing": MODEL_ROUTING_CONFIG,
    }
