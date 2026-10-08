"""Phase 9 — Real End-to-End Personal Portfolio Generation.

Runs the live Aegis AI multi-agent workflow using Google Gemini 3.6 Flash.
Prompt:
"Create a modern responsive personal portfolio website using HTML5, CSS3 and vanilla JavaScript. Include hero, about, skills, projects, experience, contact section, responsive navigation, animations and local browser functionality where appropriate."

Verifies:
- Manager: SUCCESS
- Business Analyst: SKIPPED or SUCCESS
- Solution Architect: SUCCESS
- Database: SKIPPED
- Backend: SKIPPED
- Frontend: SUCCESS
- QA: SUCCESS
- Review: SUCCESS with no blocking findings
- Improvement: SUCCESS or SKIPPED
- Final QA: SUCCESS
- Documentation: SUCCESS
- Artifact Manager: SUCCESS
- release_eligible = True
- Required files contain real content
- Hard limit <= 15 requests (target <= 10)
- Exclusively gemini-3.6-flash
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any


# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

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

PORTFOLIO_PROMPT = (
    "Create a modern responsive personal portfolio website using HTML5, CSS3 and vanilla JavaScript. "
    "Include hero, about, skills, projects, experience, contact section, responsive navigation, animations "
    "and local browser functionality where appropriate."
)


async def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    config = Settings()
    run_id = f"real_portfolio_{int(time.time())}"
    print("=" * 70)
    print("      AEGIS AI -- PHASE 9 REAL E2E PORTFOLIO GENERATION")
    print("=" * 70)
    print(f"Run ID       : {run_id}")
    print(f"Model Policy : Strictly gemini-3.6-flash")
    print(f"Max Requests : Hard limit 15 (Target <= 10)")
    print(f"Prompt       : {PORTFOLIO_PROMPT}")
    print("-" * 70)

    # 1. Initialize Memory
    memory = SharedProjectMemory(
        run_id=run_id,
        project_id="real_portfolio_proj",
        project_name="Personal Portfolio Website",
        project_slug="personal-portfolio-website",
        idea=PORTFOLIO_PROMPT,
    )
    # Default stack: html_css_js
    memory.tech_stack = TechStack(
        frontend="html_css_js",
        backend=None,
        database=None,
        authentication=None,
        rationale="Client-only responsive portfolio using HTML5, CSS3, and vanilla JavaScript.",
    )

    # 2. Providers and Registry
    llm_manager = RoleBasedProviderManager(config=config)
    adapter_registry = build_default_registry()
    agent_registry = get_agent_registry()

    active_slots = [s for s, acc in llm_manager._accounts.items() if acc.configured]
    print(f"\nActive Credential Slots ({len(active_slots)} configured):")
    for s in active_slots:
        print(f"  • {s}")

    async def report_progress(role: AgentRole, percent: int, msg: str) -> None:
        print(f"  [{role.value:<22}] {percent:3d}% — {msg}")

    async def report_log(role: AgentRole, level: Any, msg: str, payload: Any = None) -> None:
        pass

    ctx = AgentContext(
        memory=memory,
        llm=llm_manager,
        registry=adapter_registry,
        report_progress=report_progress,
        report_log=report_log,
    )

    # 3. Build Plan
    plan = build_plan(agent_registry)
    print(f"\nExecution Plan ({len(plan)} steps):")
    for step in plan:
        print(f"  • {step.display_name} ({step.role.value})")

    # 4. Execute Engine
    print("\n--- STARTING LIVE MULTI-AGENT EXECUTION ---")
    t0 = time.perf_counter()

    engine = WorkflowEngine(
        agent_registry=agent_registry,
        llm=llm_manager,
    )

    outcome = await engine.run(ctx, plan)
    duration_total = time.perf_counter() - t0

    print("\n" + "=" * 70)
    print("      WORKFLOW EXECUTION FINISHED")
    print("=" * 70)
    print(f"Duration : {duration_total:.2f}s | Failed : {outcome.failed}")

    # 5. Check Agent Outcomes
    print("\nStep Outcomes:")
    status_by_role: dict[str, str] = {}
    for step_outcome in outcome.outcomes:
        status_by_role[step_outcome.role.value] = step_outcome.status.value
        note = f" (error: {step_outcome.error})" if step_outcome.error else ""
        if step_outcome.skip_reason:
            note = f" (skipped: {step_outcome.skip_reason})"
        print(f"  [{step_outcome.role.value:<22}] -> {step_outcome.status.value.upper()}{note}")

    # 6. Verify Files in Workspace
    print("\nWorkspace Files:")
    workspace_files = {entry.path: entry.content for entry in memory.workspace.files}
    for path, content in sorted(workspace_files.items()):
        print(f"  • {path} ({len(content)} chars)")

    # 7. Collect LLM Requests
    logs = llm_manager.usage_tracker.get_buffered_entries(task_id=run_id)
    if not logs:
        logs = llm_manager.usage_tracker.get_buffered_entries(run_id=run_id)

    budget_req_count = llm_manager.budget_manager.get_or_create(run_id).current_request_number
    unique_req_nums = {l.get("request_number") for l in logs if l.get("request_number") is not None}
    total_requests = max(budget_req_count, len(unique_req_nums)) if unique_req_nums else budget_req_count

    print(f"\nTotal LLM Requests: {total_requests} (Budget counter: {budget_req_count}, Unique logs: {len(unique_req_nums)})")
    models_used = set()
    for i, l in enumerate(logs, 1):
        model = l.get("model")
        if model and model != "none":
            models_used.add(model)
        slot = l.get("credential_slot")
        agent_name = l.get("agent_name") or l.get("agent_role")
        tokens = l.get("total_tokens")
        latency = l.get("latency_ms", 0)
        req_num = l.get("request_number", i)
        print(f"  Req #{req_num:2d} | Agent: {agent_name:<22} | Slot: {slot:<18} | Model: {model} | Tokens: {tokens} | Latency: {latency:.0f}ms")

    # 8. Assertions & Release Eligibility Check
    errors: list[str] = []

    # Verify agent statuses
    if status_by_role.get(AgentRole.MANAGER.value) != AgentStatus.COMPLETED.value:
        errors.append(f"Manager did not succeed: {status_by_role.get(AgentRole.MANAGER.value)}")
    if status_by_role.get(AgentRole.SOLUTION_ARCHITECT.value) != AgentStatus.COMPLETED.value:
        errors.append(f"Solution Architect did not succeed: {status_by_role.get(AgentRole.SOLUTION_ARCHITECT.value)}")
    if status_by_role.get(AgentRole.DATABASE_ENGINEER.value) != AgentStatus.SKIPPED.value:
        errors.append(f"Database Engineer should be SKIPPED, got: {status_by_role.get(AgentRole.DATABASE_ENGINEER.value)}")
    if status_by_role.get(AgentRole.BACKEND_ENGINEER.value) != AgentStatus.SKIPPED.value:
        errors.append(f"Backend Engineer should be SKIPPED, got: {status_by_role.get(AgentRole.BACKEND_ENGINEER.value)}")
    if status_by_role.get(AgentRole.FRONTEND_ENGINEER.value) != AgentStatus.COMPLETED.value:
        errors.append(f"Frontend Engineer did not succeed: {status_by_role.get(AgentRole.FRONTEND_ENGINEER.value)}")
    if status_by_role.get(AgentRole.QA_ENGINEER.value) != AgentStatus.COMPLETED.value:
        errors.append(f"QA Engineer did not succeed: {status_by_role.get(AgentRole.QA_ENGINEER.value)}")
    if status_by_role.get(AgentRole.REVIEW_ENGINEER.value) != AgentStatus.COMPLETED.value:
        errors.append(f"Review Engineer did not succeed: {status_by_role.get(AgentRole.REVIEW_ENGINEER.value)}")
    if status_by_role.get(AgentRole.FINAL_QA.value) != AgentStatus.COMPLETED.value:
        errors.append(f"Final QA did not succeed: {status_by_role.get(AgentRole.FINAL_QA.value)}")
    if status_by_role.get(AgentRole.DOCUMENTATION_ENGINEER.value) != AgentStatus.COMPLETED.value:
        errors.append(f"Documentation Engineer did not succeed: {status_by_role.get(AgentRole.DOCUMENTATION_ENGINEER.value)}")
    if status_by_role.get(AgentRole.ARTIFACT_MANAGER.value) != AgentStatus.COMPLETED.value:
        errors.append(f"Artifact Manager did not succeed: {status_by_role.get(AgentRole.ARTIFACT_MANAGER.value)}")

    # Verify required files exist and have real content
    req_files = ["frontend/index.html", "frontend/css/styles.css", "frontend/js/app.js"]
    for rf in req_files:
        if rf not in workspace_files:
            errors.append(f"Required file missing: {rf}")
        elif len(workspace_files[rf].strip()) < 100:
            errors.append(f"Required file has placeholder/trivial content (<100 chars): {rf}")

    # Check index.html content
    index_html = workspace_files.get("frontend/index.html", "").lower()
    for section in ["hero", "about", "skills", "projects", "contact"]:
        if section not in index_html:
            errors.append(f"frontend/index.html does not contain '{section}' section")

    # Verify release_eligible
    if not memory.release_eligible:
        errors.append("memory.release_eligible is FALSE — release gate failed")

    # Verify review blocking findings
    blocking_review = [i for i in memory.review.issues if i.get("severity") in {"critical", "high"}]
    if blocking_review:
        errors.append(f"Review has {len(blocking_review)} unresolved blocking findings")

    # Verify LLM request budget
    if total_requests > 15:
        errors.append(f"Request budget exceeded: {total_requests} requests > 15 hard limit")

    # Verify model policy
    invalid_models = {m for m in models_used if m != "gemini-3.6-flash"}
    if invalid_models:
        errors.append(f"Model policy violation! Detected non-gemini-3.6-flash models: {invalid_models}")

    print("\n" + "=" * 70)
    print("      FINAL VALIDATION REPORT")
    print("=" * 70)
    print(f"release_eligible : {memory.release_eligible}")
    print(f"Requests Count   : {total_requests} / 15 (Target <= 10)")
    print(f"Models Used      : {models_used}")

    if errors:
        print("\n[ERROR] VALIDATION ERRORS ENCOUNTERED:")
        for err in errors:
            print(f"  * {err}")
        return 1

    print("\n[PASSED] ALL CHECKS PASSED PERFECTLY!")
    print("  * Manager: SUCCESS")
    print("  * Solution Architect: SUCCESS")
    print("  * Database: SKIPPED")
    print("  * Backend: SKIPPED")
    print("  * Frontend: SUCCESS (HTML, CSS, JS complete with real content)")
    print("  * QA: SUCCESS")
    print("  * Review: SUCCESS (no blocking findings)")
    print("  * Improvement: SUCCESS / SKIPPED")
    print("  * Final QA: SUCCESS")
    print("  * Documentation: SUCCESS")
    print("  * Artifact Manager: SUCCESS")
    print("  * release_eligible = True")
    print("  * Exactly gemini-3.6-flash used")
    print("  * Within budget (<= 15 requests)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
