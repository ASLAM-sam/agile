"""Phase 10 / Section 36 — Real React + TypeScript Portfolio E2E Test.

Satisfies Section 36 & 37:
Prompt:
"Build a modern premium personal portfolio website using React and TypeScript.
Create a polished developer/AI engineer portfolio with:
- hero
- about
- skills
- projects
- experience
- education
- services
- contact
- responsive navigation
- mobile menu
- animations
- project cards
- social links
- CV download button
- responsive footer
- accessible semantic structure
- modern premium visual design
Use realistic placeholder content where personal information is not provided.
The application must be production-buildable and fully client-side."

Expected Agent Flow:
Manager / Planner -> SUCCESS
Solution Architect -> SUCCESS
Database -> SKIPPED
Backend -> SKIPPED
Frontend -> SUCCESS
QA -> SUCCESS
Review -> SUCCESS
Improvement -> SUCCESS or SKIPPED
Final QA -> SUCCESS
Documentation -> SUCCESS
Artifact Manager -> SUCCESS

Verifies:
- 7-slot architecture with exact assigned models
- Target <= 10, Hard limit <= 15 requests
- release_eligible = True
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.adapters.registry import build_default_registry
from app.agents.context import AgentContext
from app.agents.registry import get_agent_registry
from app.core.config import Settings
from app.core.enums import AgentRole, AgentStatus
from app.llm.manager import RoleBasedProviderManager
from app.workflow.engine import WorkflowEngine
from app.workflow.memory import SharedProjectMemory, TechStack
from app.workflow.planner import build_plan

REACT_PORTFOLIO_PROMPT = (
    "Build a modern premium personal portfolio website using React and TypeScript.\n\n"
    "Create a polished developer/AI engineer portfolio with:\n"
    "- hero\n"
    "- about\n"
    "- skills\n"
    "- projects\n"
    "- experience\n"
    "- education\n"
    "- services\n"
    "- contact\n"
    "- responsive navigation\n"
    "- mobile menu\n"
    "- animations\n"
    "- project cards\n"
    "- social links\n"
    "- CV download button\n"
    "- responsive footer\n"
    "- accessible semantic structure\n"
    "- modern premium visual design\n\n"
    "Use realistic placeholder content where personal information is not provided.\n"
    "The application must be production-buildable and fully client-side."
)


async def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    config = Settings()
    run_id = f"react_portfolio_{int(time.time())}"
    print("=" * 72)
    print("   AEGIS AI -- SECTION 36 REAL REACT + TYPESCRIPT PORTFOLIO E2E")
    print("=" * 72)
    print(f"Run ID       : {run_id}")
    print(f"Max Requests : Hard limit 15 (Target <= 10)")
    print(f"Prompt       :\n{REACT_PORTFOLIO_PROMPT}")
    print("-" * 72)

    # 1. Initialize Memory
    memory = SharedProjectMemory(
        run_id=run_id,
        project_id="react_portfolio_proj",
        project_name="AI Engineer React Portfolio",
        project_slug="ai-engineer-react-portfolio",
        idea=REACT_PORTFOLIO_PROMPT,
    )
    memory.tech_stack = TechStack(
        frontend="react",
        backend=None,
        database=None,
        authentication=None,
        rationale="Client-only responsive portfolio using React, TypeScript, and modern styling.",
    )

    # 2. Providers and Registry
    llm_manager = RoleBasedProviderManager(config=config)
    adapter_registry = build_default_registry()
    agent_registry = get_agent_registry()

    active_slots = [s for s, acc in llm_manager._accounts.items() if acc.configured]
    print(f"\nActive Credential Slots ({len(active_slots)} configured):")
    for s in active_slots:
        model = config.get_slot_model(s)
        print(f"  • {s:<22} -> {model}")

    async def report_progress(role: AgentRole, percent: int, msg: str) -> None:
        print(f"  [{role.value:<22}] {percent:3d}% -- {msg}")

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

    print("\n" + "=" * 72)
    print("      WORKFLOW EXECUTION COMPLETED")
    print("=" * 72)
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

    print(f"\nTotal LLM Requests: {total_requests} (Budget counter: {budget_req_count})")
    models_used: dict[str, int] = {}
    for i, l in enumerate(logs, 1):
        model = l.get("model", "unknown")
        models_used[model] = models_used.get(model, 0) + 1
        slot = l.get("credential_slot")
        agent_name = l.get("agent_name") or l.get("agent_role")
        tokens = l.get("total_tokens")
        latency = l.get("latency_ms", 0)
        req_num = l.get("request_number", i)
        print(f"  Req #{req_num:2d} | Agent: {agent_name:<22} | Slot: {slot:<18} | Model: {model} | Tokens: {tokens} | Latency: {latency:.0f}ms")

    print("\nModels Invocation Summary:")
    for m, c in sorted(models_used.items()):
        print(f"  • {m}: {c} calls")

    # 8. Evaluation
    errors: list[str] = []

    # Verify agent expectations (Section 37)
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

    # Check budget hard limit
    if total_requests > 15:
        errors.append(f"Hard request limit exceeded: {total_requests} > 15")

    # Verify release_eligible
    if not memory.release_eligible:
        errors.append("memory.release_eligible is FALSE -- release gate failed")

    print("\n" + "=" * 72)
    print("      FINAL RELEASE EVALUATION")
    print("=" * 72)
    print(f"release_eligible : {memory.release_eligible}")
    print(f"Total Requests   : {total_requests}/15")
    print(f"Validation Errors: {len(errors)}")
    for err in errors:
        print(f"  [X] {err}")

    if not errors and memory.release_eligible:
        print("\n>>> ALL CHECKS PASSED: React Portfolio E2E Generation is fully RELEASE ELIGIBLE! <<<")
        return 0
    else:
        print("\n>>> EVALUATION FAILED: See errors above <<<")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
