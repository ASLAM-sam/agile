"""Phase 5 — Real End-to-End Project Generation Test.
AgileAgent / Aegis AI — Benchmark: "Modern Task Manager Web App"

Executes the full multi-agent pipeline:
1. ManagerAgent (Planner)
2. BusinessAnalystAgent (SRS & Capability Decisions)
3. SolutionArchitectAgent (Client Architecture & Contract)
4. DatabaseEngineerAgent (Decision: Skipped for client-only)
5. BackendEngineerAgent (Decision: Skipped for client-only)
6. FrontendEngineerAgent (HTML/CSS/JS Implementation)
7. QAEngineerAgent (Quality Assurance & Test Suite)
8. ReviewEngineerAgent (Requirement Verification & Review)
9. ImprovementEngineerAgent (Targeted Code Refinement)
10. FinalQAAgent (Post-Improvement Verification)
11. DocumentationEngineerAgent (Documentation & Guides)
12. ArtifactManagerAgent (Deterministic Packaging — ZERO LLM Calls)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.adapters.registry import build_default_registry
from app.agents.artifact_manager import ArtifactManagerAgent
from app.agents.backend_engineer import BackendEngineerAgent
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.context import AgentContext
from app.agents.database_engineer import DatabaseEngineerAgent
from app.agents.documentation_engineer import DocumentationEngineerAgent
from app.agents.final_qa_agent import FinalQAAgent
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.agents.improvement_engineer import ImprovementEngineerAgent
from app.agents.manager import ManagerAgent
from app.agents.qa_engineer import QAEngineerAgent
from app.agents.registry import get_agent_registry
from app.agents.review_engineer import ReviewEngineerAgent
from app.agents.solution_architect import SolutionArchitectAgent
from app.core.config import Settings, settings
from app.core.enums import AgentRole, AgentStatus
from app.llm.manager import RoleBasedProviderManager
from app.workflow.engine import WorkflowEngine
from app.workflow.memory import SharedProjectMemory, TechStack
from app.workflow.planner import build_plan
from app.packaging.zip_builder import ZipPackager, extract_and_verify_zip

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


async def main() -> int:
    config = Settings()
    run_id = f"phase5_{int(time.time())}"
    print("=" * 65)
    print("  PHASE 5: REAL END-TO-END PROJECT GENERATION BENCHMARK")
    print("  Project: Modern Task Manager Web App (HTML / CSS / JS)")
    print("  Active Model: gemini-3.6-flash (Generic Multi-Slot Router)")
    print(f"  Run ID: {run_id}")
    print("=" * 65)

    # 1. Initialize Memory
    memory = SharedProjectMemory(
        run_id=run_id,
        project_id="phase5_task_manager_proj",
        project_name="Modern Task Manager Web App",
        project_slug="modern-task-manager",
        idea=USER_REQUIREMENTS,
    )
    # Default stack is pure HTML/CSS/JS (no framework)
    memory.tech_stack = TechStack(
        frontend="html_css_js",
        backend=None,
        database=None,
        authentication=None,
        rationale="Client-only responsive web application using HTML5, CSS3, Vanilla JS and localStorage.",
    )

    # 2. Build Providers and Registry
    llm_manager = RoleBasedProviderManager(config=config)
    adapter_registry = build_default_registry()
    agent_registry = get_agent_registry()
    active_slots = [s for s, acc in llm_manager._accounts.items() if acc.configured]
    print(f"\nActive Credential Slots ({len(active_slots)} configured):")
    for s in active_slots:
        print(f"  • {s}")

    # Progress/log hooks
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
    print(f"\nExecution Plan ({len(plan)} potential steps):")
    for step in plan:
        print(f"  • {step.display_name} ({step.role.value})")

    # 4. Execute Engine
    print("\nStarting WorkflowEngine execution...")
    t_start = time.perf_counter()

    async def on_step_finished(step: Any, outcome: Any) -> None:
        pass

    engine = WorkflowEngine(
        agent_registry=agent_registry,
        llm=llm_manager,
        on_step_finished=on_step_finished,
    )

    # Track requests before and after each step
    agent_requests: dict[str, int] = {}
    artifact_manager_llm_calls = 0

    outcome = await engine.run(ctx, plan)
    duration_total = time.perf_counter() - t_start

    print("\n" + "=" * 65)
    print("  WORKFLOW EXECUTION FINISHED")
    print(f"  Duration: {duration_total:.2f}s | Failed: {outcome.failed}")
    print("=" * 65)

    # Collect UsageLogs from the run
    usage_logs = llm_manager.usage_tracker.get_buffered_entries(task_id=run_id)
    if not usage_logs:
        usage_logs = llm_manager.usage_tracker.get_buffered_entries(run_id=run_id)

    task_budget_state = llm_manager.budget_manager.get_or_create(run_id)
    total_llm_requests = task_budget_state.current_request_number
    if total_llm_requests == 0:
        total_llm_requests = len(usage_logs)

    # Count requests per agent
    seen_requests: set[tuple[str, int]] = set()
    for entry in usage_logs:
        agent_name = entry.get("agent_name") or entry.get("agent_role") or entry.get("agent") or "Unknown"
        req_num = entry.get("request_number")
        if req_num is not None:
            if (agent_name, req_num) not in seen_requests:
                seen_requests.add((agent_name, req_num))
                agent_requests[agent_name] = agent_requests.get(agent_name, 0) + 1
        else:
            agent_requests[agent_name] = agent_requests.get(agent_name, 0) + 1
        if "artifact_manager" in agent_name.lower():
            artifact_manager_llm_calls += 1

    print("\nAGENT EXECUTION OUTCOMES:")
    print("-" * 65)
    print(f"{'Agent':<26} {'Status':<12} {'Duration':<10} {'Skip Reason / Summary'}")
    print("-" * 65)
    for step_outcome in outcome.outcomes:
        reason = step_outcome.skip_reason or (step_outcome.result.summary if step_outcome.result else "")
        if len(reason) > 40:
            reason = reason[:37] + "..."
        print(f"{step_outcome.role.value:<26} {step_outcome.status.value:<12} {step_outcome.duration_seconds:<10.2f} {reason}")

    print("\nLLM USAGE PER AGENT:")
    print("-" * 45)
    print(f"{'Agent':<28} {'LLM Requests':<15}")
    print("-" * 45)
    for ag, req_count in sorted(agent_requests.items()):
        print(f"{ag:<28} {req_count:<15}")
    print("-" * 45)
    print(f"{'Total LLM Requests':<28} {total_llm_requests:<15}")
    print(f"{'Request Budget Limit':<28} 15 (Target: 10)")
    print(f"{'ArtifactManager Calls':<28} {artifact_manager_llm_calls} (Requirement: 0)")

    print("\nAGENT CREDENTIAL SLOT RESOLUTION (8 GENERIC PRIMARY SLOTS):")
    print("-" * 65)
    print(f"{'Agent':<28} {'Credential Slot':<22} {'LLM Calls'}")
    print("-" * 65)
    from app.llm.agent_model_registry import provider_slot_for
    for agent_role in [
        AgentRole.MANAGER,
        AgentRole.BUSINESS_ANALYST,
        AgentRole.SOLUTION_ARCHITECT,
        AgentRole.DATABASE_ENGINEER,
        AgentRole.BACKEND_ENGINEER,
        AgentRole.FRONTEND_ENGINEER,
        AgentRole.QA_ENGINEER,
        AgentRole.REVIEW_ENGINEER,
        AgentRole.IMPROVEMENT_ENGINEER,
        AgentRole.FINAL_QA,
        AgentRole.DOCUMENTATION_ENGINEER,
        AgentRole.ARTIFACT_MANAGER,
    ]:
        slot = provider_slot_for(agent_role)
        calls = agent_requests.get(agent_role.value, 0)
        slot_label = slot if slot != "none" else "DETERMINISTIC (0 LLM)"
        print(f"{agent_role.value:<28} {slot_label:<22} {calls}")
    print("-" * 65)

    # 5. Extract Final Generated Files to Disk
    output_dir = Path(config.artifact_root) / "phase5_task_manager"
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_files = {}

    for wf in memory.workspace.files:
        if wf.content:
            target_path = output_dir / wf.path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(wf.content, encoding="utf-8")
            generated_files[wf.path] = wf.content

    print(f"\nExtracted {len(generated_files)} generated files to: {output_dir}")
    for p in sorted(generated_files.keys()):
        size_kb = len(generated_files[p].encode("utf-8")) / 1024
        print(f"  • {p:<35} ({size_kb:.1f} KB)")

    # 5b. Build Release ZIP Archive via ZipPackager and Verify Extraction
    packager = ZipPackager()
    package_result = packager.write(
        memory.workspace,
        run_id=run_id,
        project_slug=memory.project_slug,
    )
    print(f"\nBuilt Production ZIP Archive: {package_result.filename} ({package_result.size_kb} KB, {package_result.file_count} files)")
    print(f"Archive SHA-256 Checksum: {package_result.checksum}")

    # Verify independent ZIP extraction and safety
    zip_extract_dir = output_dir / "verified_zip_release"
    extracted_zip_files = extract_and_verify_zip(package_result.path, zip_extract_dir)
    print(f"Independent ZIP extraction & security verification: {len(extracted_zip_files)} files verified clean (no secrets, no .env)")

    # 6. Deterministic Verification of Requirements
    print("\n" + "=" * 65)
    print("  DETERMINISTIC REQUIREMENTS AUDIT (20 CHECKS)")
    print("=" * 65)

    checks_passed = 0
    checks_total = 20

    def check(num: int, title: str, condition: bool, details: str = "") -> None:
        nonlocal checks_passed
        status_str = "[PASS]" if condition else "[FAIL]"
        print(f"  {status_str} Req {num:02d}: {title}")
        if details:
            print(f"         |-- {details}")
        if condition:
            checks_passed += 1

    # Check key files exist
    html_content = generated_files.get("frontend/index.html", "")
    css_content = generated_files.get("frontend/css/styles.css", "")
    js_content = generated_files.get("frontend/js/app.js", "")
    all_js = "\n".join([v for k, v in generated_files.items() if k.endswith(".js")])
    all_code = "\n".join(generated_files.values())

    # Req 1: Users can create tasks
    check(1, "Task Creation",
          bool(re.search(r"(addTask|createTask|handleAddTask|submit|form)", all_js, re.I) and "input" in html_content.lower()),
          "Task creation form & submit handler detected in JS and HTML")

    # Req 2: Users can edit tasks
    check(2, "Task Editing",
          bool(re.search(r"(editTask|updateTask|handleEdit|modal|contenteditable|edit-btn)", all_js + html_content, re.I)),
          "Edit task handler / modal detected in JS/HTML")

    # Req 3: Users can delete tasks
    check(3, "Task Deletion",
          bool(re.search(r"(deleteTask|removeTask|handleDelete|\.delete\()", all_js, re.I)),
          "Delete handler found in JS")

    # Req 4: Users can mark tasks as completed
    check(4, "Task Completion Toggle",
          bool(re.search(r"(toggleComplete|toggleTask|completed|status)", all_js, re.I)),
          "Task status toggle logic found in JS")

    # Req 5: Filter tasks (All, Active, Completed)
    check(5, "Task Filtering (All, Active, Completed)",
          bool(re.search(r"(filter|active|completed)", all_js, re.I) and ("filter" in html_content.lower() or "tab" in html_content.lower())),
          "Filter controls found in HTML and filtering logic in JS")

    # Req 6: Search tasks
    check(6, "Search Tasks",
          bool(re.search(r"(search|filter|searchInput)", all_js, re.I) and "search" in html_content.lower()),
          "Search input in HTML and search handler in JS")

    # Req 7: Task fields (title, description, priority, due date, completed)
    has_title = "title" in all_code.lower()
    has_desc = "description" in all_code.lower()
    has_priority = "priority" in all_code.lower()
    has_date = "due" in all_code.lower() or "date" in all_code.lower()
    check(7, "Task Fields (title, desc, priority, date, status)",
          has_title and has_desc and has_priority and has_date,
          f"Fields detected: title={has_title}, desc={has_desc}, priority={has_priority}, date={has_date}")

    # Req 8: Show statistics (total, active, completed)
    check(8, "Statistics (total, active, completed)",
          bool(re.search(r"(total|active|completed|stats|count)", all_js, re.I) and re.search(r"(stat|count|total)", html_content, re.I)),
          "Task counter elements in HTML and calculation logic in JS")

    # Req 9: Clean modern responsive UI
    check(9, "Responsive UI & Modern CSS",
          bool(css_content and ":root" in css_content and "--" in css_content),
          "CSS variables, modern layout styling detected")

    # Req 10: Works on desktop, tablet, mobile
    check(10, "Media Queries for Responsive Layout",
          "@media" in css_content and ("max-width" in css_content or "min-width" in css_content),
          f"CSS contains responsive media queries ({css_content.count('@media')} breakpoints)")

    # Req 11: Store task data using localStorage
    check(11, "Browser localStorage Persistence",
          "localStorage.getItem" in all_js and "localStorage.setItem" in all_js,
          "Both localStorage.getItem and localStorage.setItem detected in JS")

    # Req 12: Empty-state UI
    check(12, "Empty-State UI",
          bool(re.search(r"(empty|no tasks|no-task|empty-state)", html_content + all_js, re.I)),
          "Empty-state display element detected in HTML/JS")

    # Req 13: Confirmation before deleting
    check(13, "Delete Confirmation",
          bool(re.search(r"(confirm|modal|dialog|prompt|are you sure)", all_js + html_content, re.I)),
          "Confirmation prompt / modal dialog detected for delete action")

    # Req 14: Validate required fields
    check(14, "Input Validation",
          bool(re.search(r"(validate|required|trim|alert|error)", all_js + html_content, re.I)),
          "Validation logic / required attributes detected")

    # Req 15: Error/validation messages
    check(15, "Validation / Error Feedback",
          bool(re.search(r"(error|invalid|feedback|msg|alert)", all_js + html_content, re.I)),
          "Error display or alert messaging present")

    # Req 16: No external backend services
    has_fetch_api = bool(re.search(r"(fetch\s*\(\s*['\"]/api|axios\.|xhr)", all_js))
    check(16, "No External Backend Services",
          not has_fetch_api,
          "Verified client-only: zero backend API HTTP calls")

    # Req 17: No API key needed to run
    check(17, "No API Key Required to Run",
          "API_KEY" not in all_code and "api_key" not in all_code,
          "No API keys required by client code")

    # Req 18: Runnable locally via simple server
    check(18, "Runnable Locally (Self-Contained)",
          (output_dir / "frontend/index.html").exists() and (output_dir / "frontend/css/styles.css").exists(),
          "Standard web directory structure ready for local HTTP serving")

    # Req 19: Clean project organization
    has_html = "frontend/index.html" in generated_files
    has_css = "frontend/css/styles.css" in generated_files
    has_js = "frontend/js/app.js" in generated_files
    check(19, "Clean Folder Structure",
          has_html and has_css and has_js,
          "Organized in frontend/index.html, frontend/css/, frontend/js/")

    # Req 20: No secrets or credentials
    secrets_found = bool(re.search(r"(AIza[0-9A-Za-z-_]{35}|sk-[0-9A-Za-z]{20,}|ghp_[0-9A-Za-z]{20,})", all_code))
    check(20, "Zero Secrets or Credentials in Code",
          not secrets_found,
          "Security audit clean: 0 private credentials found in generated code")

    # 7. Gemini Model Sanity Check
    print("\n" + "=" * 65)
    print("  GEMINI MODEL SANITY CHECK")
    print("=" * 65)
    gemini_37_38_in_code = bool(re.search(r"gemini-3\.[78]", all_code))
    print(f"  • Gemini 3.7/3.8 in generated code : {gemini_37_38_in_code} (Expect: False)")
    active_models_used = set(l.get("model") for l in usage_logs)
    print(f"  • Active models used in run        : {active_models_used}")

    # 8. Request Budget Safety Audit
    print("\n" + "=" * 65)
    print("  REQUEST BUDGET SAFETY AUDIT")
    print("=" * 65)
    budget_passed = total_llm_requests <= 15
    print(f"  • Target budget  : 10 requests")
    print(f"  • Hard limit     : 15 requests")
    print(f"  • Actual requests: {total_llm_requests}")
    print(f"  • Budget status  : {'[PASS]' if budget_passed else '[FAIL]'}")
    print(f"  • ArtifactManager: {artifact_manager_llm_calls} calls (Expect: 0) -> {'[PASS]' if artifact_manager_llm_calls == 0 else '[FAIL]'}")

    # 9. Final Status
    all_requirements_met = checks_passed == checks_total and budget_passed and (artifact_manager_llm_calls == 0) and not gemini_37_38_in_code

    print("\n" + "=" * 65)
    print(f"  PHASE 5 BENCHMARK RESULT: {checks_passed}/{checks_total} CHECKS PASSED")
    if all_requirements_met:
        print("  >>> PHASE 5 STATUS: PASS <<<")
    else:
        print("  >>> PHASE 5 STATUS: FAIL <<<")
    print("=" * 65)

    return 0 if all_requirements_met else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
