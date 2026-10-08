"""Phase 5 — End-to-End Task Manager Generation and Reliability Gate Test.

Executes the complete Aegis AI / AgileAgent pipeline against the Phase 5 benchmark:
- Project: "Modern Task Manager Web App"
- Stack: HTML5, CSS3, Vanilla JavaScript (zero external frontend frameworks)
- Storage: Browser localStorage (zero backend/database services)
- Active Model: gemini-3.6-flash only
- Budget: <= 10 requests target, <= 15 hard maximum
- ArtifactManager: 0 LLM calls (deterministic)
- Final QA: Independent post-improvement verification, authorizes release ZIP
- Clean ZIP Packaging & Extraction verification
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest

from app.adapters.registry import build_default_registry
from app.agents.context import AgentContext
from app.agents.registry import get_agent_registry
from app.core.config import Settings
from app.core.enums import AgentRole, AgentStatus
from app.llm.manager import RoleBasedProviderManager
from app.packaging.zip_builder import ZipPackager, extract_and_verify_zip
from app.workflow.engine import WorkflowEngine
from app.workflow.memory import SharedProjectMemory, TechStack
from app.workflow.planner import build_plan

USER_REQUIREMENTS = """Build a modern responsive task manager web application.

Requirements:

1. Users can create tasks.
2. Users can edit tasks.
3. Users can delete tasks.
4. Users can mark tasks as completed.
5. Users can filter tasks:
   - All
   - Active
   - Completed

6. Users can search tasks.

7. Each task should support:
   - title
   - description
   - priority
   - due date
   - completed status

8. Show useful statistics:
   - total tasks
   - active tasks
   - completed tasks

9. Include a clean modern responsive UI.

10. The application must work on:
    - desktop
    - tablet
    - mobile

11. Store task data using browser localStorage.

12. Include empty-state UI when there are no tasks.

13. Include confirmation before deleting a task.

14. Validate required fields.

15. Provide useful error/validation messages.

16. Do not use external backend services.

17. Do not require an API key to run the generated application.

18. The final project must be runnable locally by opening the project
    through a simple local web server.

19. Organize the project cleanly.

20. Do not include secrets or credentials anywhere in generated files."""


@pytest.mark.asyncio
async def test_phase5_modern_task_manager_e2e(tmp_path: Path) -> None:
    """Full Phase 5 E2E run generating Modern Task Manager with real validation and packaging."""
    config = Settings(
        artifact_root=str(tmp_path / "artifacts"),
        gemini_frontend_api_key="AQ.test_key_frontend_001",
        gemini_backend_api_key="AQ.test_key_backend_001",
        gemini_qa_api_key="AQ.test_key_qa_001",
        gemini_improvement_api_key="AQ.test_key_improvement_001",
    )
    run_id = "test_phase5_task_manager_001"

    memory = SharedProjectMemory(
        run_id=run_id,
        project_id="phase5_task_manager_proj",
        project_name="Modern Task Manager Web App",
        project_slug="modern-task-manager",
        idea=USER_REQUIREMENTS,
    )
    memory.tech_stack = TechStack(
        frontend="html_css_js",
        backend=None,
        database=None,
        authentication=None,
        rationale="Client-only responsive web application using HTML5, CSS3, Vanilla JS and localStorage.",
    )

    llm_manager = RoleBasedProviderManager(config=config)
    adapter_registry = build_default_registry()
    agent_registry = get_agent_registry()

    async def report_progress(role: AgentRole, percent: int, msg: str) -> None:
        pass

    async def report_log(role: AgentRole, level: Any, msg: str, payload: Any = None) -> None:
        pass

    ctx = AgentContext(
        memory=memory,
        llm=llm_manager,
        registry=adapter_registry,
        report_progress=report_progress,
        report_log=report_log,
    )

    plan = build_plan(agent_registry)
    engine = WorkflowEngine(agent_registry=agent_registry, llm=llm_manager)

    outcome = await engine.run(ctx, plan)
    assert not outcome.failed, f"Workflow execution failed: {outcome.failure_reason}"

    # 1. Verify executed vs skipped agents
    executed_roles = {o.role for o in outcome.executed}
    skipped_roles = {o.role for o in outcome.skipped}

    assert AgentRole.MANAGER in executed_roles
    assert AgentRole.BUSINESS_ANALYST in executed_roles
    assert AgentRole.SOLUTION_ARCHITECT in executed_roles
    assert AgentRole.FRONTEND_ENGINEER in executed_roles
    assert AgentRole.QA_ENGINEER in executed_roles
    assert AgentRole.REVIEW_ENGINEER in executed_roles
    assert AgentRole.IMPROVEMENT_ENGINEER in executed_roles
    assert AgentRole.FINAL_QA in executed_roles
    assert AgentRole.DOCUMENTATION_ENGINEER in executed_roles
    assert AgentRole.ARTIFACT_MANAGER in executed_roles

    # Backend and Database agents must be cleanly skipped for client-only project
    assert AgentRole.DATABASE_ENGINEER in skipped_roles
    assert AgentRole.BACKEND_ENGINEER in skipped_roles

    # 2. Verify Request Budget and UsageLogs
    usage_logs = llm_manager.usage_tracker.get_buffered_entries(task_id=run_id)
    if not usage_logs:
        usage_logs = llm_manager.usage_tracker.get_buffered_entries(run_id=run_id)

    task_budget_state = llm_manager.budget_manager.get_or_create(run_id)
    total_llm_requests = task_budget_state.current_request_number or len(usage_logs)

    assert total_llm_requests <= 10, f"Target request budget (10) exceeded: {total_llm_requests}"
    assert total_llm_requests <= 15, f"Hard max budget (15) exceeded: {total_llm_requests}"

    # ArtifactManagerAgent must make ZERO LLM calls
    artifact_calls = sum(1 for l in usage_logs if "artifact_manager" in (l.get("agent_name") or "").lower())
    assert artifact_calls == 0, f"ArtifactManager made {artifact_calls} LLM calls (must be 0)"

    # 3. Model Sanity Check
    all_code = "\n".join(wf.content for wf in memory.workspace.files if wf.content)
    assert not re.search(r"gemini-3\.[78]", all_code), "Forbidden Gemini 3.7/3.8 found in generated files"
    active_models = set(l.get("model") for l in usage_logs if l.get("model"))
    for m in active_models:
        assert "3.7" not in m and "3.8" not in m, f"Forbidden Gemini model used: {m}"

    # 4. Packaging and Independent ZIP Extraction
    packager = ZipPackager(artifact_root=str(tmp_path / "artifacts"))
    package_result = packager.write(
        memory.workspace,
        run_id=run_id,
        project_slug=memory.project_slug,
    )
    assert package_result.path.exists()
    assert package_result.size_bytes > 0

    extract_dir = tmp_path / "extracted_release"
    extracted_files = extract_and_verify_zip(package_result.path, extract_dir)
    assert len(extracted_files) >= 10

    # Ensure no secrets or .env leaked into the zip package
    for path, content in extracted_files.items():
        assert not path.startswith(".env") or path.endswith(".example"), f"Forbidden .env in ZIP: {path}"
        assert not re.search(r"(AIza[0-9A-Za-z-_]{35}|sk-[0-9A-Za-z]{20,})", content), f"Secret in ZIP file: {path}"

    # 5. Core Requirements Deterministic Checks
    assert "frontend/index.html" in extracted_files
    assert "frontend/css/styles.css" in extracted_files
    assert "frontend/js/app.js" in extracted_files

    index_html = extracted_files["frontend/index.html"]
    styles_css = extracted_files["frontend/css/styles.css"]
    app_js = extracted_files["frontend/js/app.js"]
    all_js = "\n".join(v for k, v in extracted_files.items() if k.endswith(".js"))

    # localStorage persistence
    assert "localStorage.getItem" in all_js
    assert "localStorage.setItem" in all_js

    # Empty state UI
    assert "empty-state" in index_html.lower()

    # Deletion confirmation
    assert "delete-modal" in index_html.lower() or "confirm" in all_js.lower()

    # Search & Filter
    assert "search-input" in index_html.lower()
    assert "filter" in index_html.lower()

    # Final QA released
    assert memory.release_eligible is True
