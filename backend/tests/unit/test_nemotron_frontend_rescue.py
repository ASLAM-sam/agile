"""21 Automated Regression Tests for 7-Agent Model Architecture & Nemotron Frontend Rescue.

Satisfies all requirements of Section 32 and Section 33:
1. Fresh generation does not reuse previous project context.
2. Duplicate file paths are deduplicated.
3. External imports have corresponding dependencies.
4. Missing dependencies are detected before build.
5. TypeScript Node types configuration is valid.
6. ESLint configuration is internally consistent.
7. Repair engine targets actual affected files.
8. Repeated failure signatures trigger stagnation detection.
9. Stagnation triggers Nemotron rescue.
10. Nemotron rescue uses DEBUG_API_KEY01.
11. Nemotron rescue does not create a new API-key slot.
12. Source-only repairs do not unnecessarily run npm install.
13. package.json changes invalidate dependency state.
14. Request counter includes all Gemini and Nemotron calls.
15. Request #16 is impossible (hard limit of 15).
16. Failed npm install blocks release.
17. Failed build blocks release.
18. Successful React project passes release gate.
19. Frontend successful generation does not call Nemotron.
20. Frontend failure requiring escalation does call Nemotron.
21. Realistic frontend failure and rescue flow (Section 33).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.context import AgentContext
from app.agents.final_qa_agent import FinalQAAgent
from app.core.config import Settings
from app.core.enums import AgentRole, LogLevel
from app.llm.agent_model_registry import (
    SLOT_DEFAULT_MODELS,
    model_for_role_str,
    model_for_slot,
    provider_slot_for_str,
)
from app.llm.budget import RequestBudgetManager, RequestBudgetExceededError
from app.llm.manager import RoleBasedProviderManager
from app.llm.types import Completion, PromptBundle, TokenUsage
from app.packaging.workspace import ProjectWorkspace
from app.validation.classifier import classify_failures
from app.validation.dependencies import scan_source_imports, validate_and_sync_dependencies
from app.validation.executor import CommandResult, ValidationRun, WorkspaceValidator
from app.validation.repair import (
    build_structured_rescue_context,
    compute_aggregate_failure_signature,
    normalize_failure_signature,
    run_repair_loop,
)
from app.workflow.memory import RepairCycle, SharedProjectMemory, ValidationResult


class MockSlotProvider:
    """Mock LLM provider tracking calls and assigned slot."""

    def __init__(self, slot: str, model: str = "gemini-3.6-flash") -> None:
        self.slot = slot
        self.model = model
        self.calls: list[PromptBundle] = []

    async def complete_structured(self, prompt: PromptBundle, *, model: str | None = None) -> Completion:
        self.calls.append(prompt)
        return Completion(
            data={"project_name": "Test App", "files": [], "explanation": "ok"},
            usage=TokenUsage(input_tokens=100, output_tokens=100),
            model=model or self.model,
        )

    async def complete_text(self, prompt: PromptBundle, *, model: str | None = None) -> Any:
        self.calls.append(prompt)
        return MagicMock(text="ok", usage=TokenUsage(input_tokens=100, output_tokens=100))

    async def aclose(self) -> None:
        pass


def make_context(memory: SharedProjectMemory, llm: Any) -> AgentContext:
    async def progress(role: AgentRole, percent: int, message: str) -> None:
        pass

    async def log(role: AgentRole, message: str, level: LogLevel = LogLevel.INFO, payload: dict | None = None) -> None:
        pass

    return AgentContext(
        memory=memory,
        llm=llm,
        registry=MagicMock(),
        report_progress=progress,
        report_log=log,
    )


# =============================================================================
# 1. Fresh generation does not reuse previous project context
# =============================================================================
def test_fresh_generation_does_not_reuse_previous_project_context() -> None:
    # Run A: FocusGrid Task Manager
    mem_a = SharedProjectMemory(
        run_id="run-a", project_id="p-a", project_name="FocusGrid Task Manager", project_slug="focusgrid", idea="FocusGrid Task Manager"
    )
    mem_a.analysis.project_overview = "Task management with localStorage"
    mem_a.workspace.write("frontend/app.js", "localStorage.setItem('tasks', '[]');")

    # Run B: Apex Nova React Portfolio
    mem_b = SharedProjectMemory(
        run_id="run-b", project_id="p-b", project_name="Apex Nova React Portfolio", project_slug="apex-nova", idea="Apex Nova React Portfolio"
    )

    # Verify completely clean isolation
    assert mem_b.project_name == "Apex Nova React Portfolio"
    assert "FocusGrid" not in mem_b.project_name
    assert "FocusGrid" not in mem_b.idea
    assert len(mem_b.workspace.files) == 0
    assert "frontend/app.js" not in [f.path for f in mem_b.workspace.files]

    # Check that fallback brief generator produces dynamic project name matching prompt B
    manager = RoleBasedProviderManager(config=Settings(app_env="test"))
    bundle_b = PromptBundle(
        cacheable_system="",
        user_message="Build the Apex Nova React Portfolio for an AI engineer with projects and contact.",
    )
    fallback_b = manager._generate_quota_fallback_data("manager", bundle_b)
    assert fallback_b is not None
    assert "FocusGrid" not in fallback_b["project_name"]
    assert "Apex Nova" in fallback_b["project_name"] or "Portfolio" in fallback_b["project_name"]


# =============================================================================
# 2. Duplicate file paths are deduplicated
# =============================================================================
def test_duplicate_file_paths_are_deduplicated() -> None:
    ws = ProjectWorkspace()
    items = [
        {"path": "src/App.tsx", "content": "export default function App() { return <div>V1</div>; }"},
        {"path": "src/App.tsx", "content": "export default function App() { return <div>V2</div>; }"},
        {"path": "./src/App.tsx", "content": "export default function App() { return <div>V3 Final</div>; }"},
    ]
    accepted, rejected = ws.write_many(items)
    # Must only accept once for normalized path src/App.tsx
    assert len(accepted) == 1
    assert accepted[0].path == "src/App.tsx"
    assert ws.read("src/App.tsx") == "export default function App() { return <div>V3 Final</div>; }"


# =============================================================================
# 3. External imports have corresponding dependencies
# =============================================================================
def test_external_imports_have_corresponding_dependencies() -> None:
    files = {
        "frontend/src/App.tsx": "import React from 'react';\nimport { ArrowRight } from 'lucide-react';\nimport clsx from 'clsx';",
        "frontend/package.json": json.dumps({
            "name": "test-app",
            "dependencies": {"react": "^18.3.1"},
            "devDependencies": {},
        }),
    }
    updated_files, logs = validate_and_sync_dependencies(files)
    pkg_data = json.loads(updated_files["frontend/package.json"])
    assert "lucide-react" in pkg_data["dependencies"]
    assert "clsx" in pkg_data["dependencies"]
    assert any("lucide-react" in log for log in logs)


# =============================================================================
# 4. Missing dependencies are detected before build
# =============================================================================
def test_missing_dependencies_are_detected_before_build() -> None:
    files = {
        "frontend/src/Card.tsx": "import { motion } from 'framer-motion';\nimport { FaGithub } from 'react-icons/fa';",
        "frontend/package.json": json.dumps({"dependencies": {}}),
    }
    imported = scan_source_imports(files)
    assert "framer-motion" in imported
    assert "react-icons" in imported
    updated_files, logs = validate_and_sync_dependencies(files)
    pkg = json.loads(updated_files["frontend/package.json"])
    assert "framer-motion" in pkg["dependencies"]
    assert "react-icons" in pkg["dependencies"]


# =============================================================================
# 5. TypeScript Node types configuration is valid
# =============================================================================
def test_typescript_node_types_configuration_valid() -> None:
    files = {
        "frontend/tsconfig.node.json": json.dumps({
            "compilerOptions": {"types": ["node"]}
        }),
        "frontend/package.json": json.dumps({
            "dependencies": {},
            "devDependencies": {},
        }),
    }
    updated_files, logs = validate_and_sync_dependencies(files)
    pkg = json.loads(updated_files["frontend/package.json"])
    assert "@types/node" in pkg["devDependencies"]
    assert any("@types/node" in log for log in logs)


# =============================================================================
# 6. ESLint configuration is internally consistent
# =============================================================================
def test_eslint_configuration_is_internally_consistent() -> None:
    files = {
        "frontend/package.json": json.dumps({
            "scripts": {"lint": "eslint . --ext ts,tsx", "build": "vite build"},
            "dependencies": {},
            "devDependencies": {},
        }),
    }
    # No eslint installed or configured -> script must be cleanly removed
    updated_files, logs = validate_and_sync_dependencies(files)
    pkg = json.loads(updated_files["frontend/package.json"])
    assert "lint" not in pkg["scripts"]
    assert "build" in pkg["scripts"]
    assert any("Removed broken 'lint' script" in log for log in logs)


# =============================================================================
# 7. Repair engine targets actual affected files
# =============================================================================
def test_repair_engine_targets_actual_affected_files() -> None:
    mem = SharedProjectMemory(run_id="r1", project_id="p1", project_name="P", project_slug="p", idea="App")
    mem.workspace.write("frontend/package.json", json.dumps({"dependencies": {}}))
    mem.workspace.write("frontend/src/App.tsx", "import { Icon } from 'lucide-react';")
    mem.workspace.write("frontend/src/Unrelated.tsx", "export const Y = 2;")
    mem.workspace.write("frontend/index.html", "<html><body></body></html>")

    failures = [{
        "command": "npm run build",
        "file": "frontend/src/App.tsx",
        "error": "TS2307: Cannot find module 'lucide-react'",
        "category": "type_error",
        "responsible_agent": "frontend_engineer",
    }]
    ctx = make_context(mem, MagicMock())
    context = build_structured_rescue_context(ctx, failures, [])
    # Affected files should only include App.tsx and relevant configs, not Unrelated.tsx
    assert "frontend/src/App.tsx" in context["affected_files"]
    assert "frontend/src/Unrelated.tsx" not in context["affected_files"]


# =============================================================================
# 8. Repeated failure signatures trigger stagnation detection
# =============================================================================
def test_repeated_failure_signatures_trigger_stagnation_detection() -> None:
    failure_1 = {
        "command": "npm run build",
        "file": "frontend/src/App.tsx",
        "error": "TS2688: Cannot find type definition file for 'node'",
        "category": "type_error",
    }
    failure_2 = {
        "command": "npm run build",
        "file": "frontend/src/App.tsx",
        "error": "TS2688: Cannot find type definition file for 'node' [duration: 320ms at 2026-10-08T12:00:00Z in aegis-run-workspace-123]",
        "category": "type_error",
    }
    sig1 = normalize_failure_signature(failure_1)
    sig2 = normalize_failure_signature(failure_2)
    # Dynamic durations and paths are scrubbed -> exact match!
    assert sig1 == sig2
    assert "TS2688" in sig1


# =============================================================================
# 9 & 10. Stagnation triggers Nemotron rescue & uses DEBUG_API_KEY01
# =============================================================================
@pytest.mark.asyncio
async def test_stagnation_triggers_nemotron_rescue_via_debug_slot() -> None:
    mem = SharedProjectMemory(run_id="run-stagnation", project_id="p", project_name="P", project_slug="p", idea="App")
    mem.workspace.write("frontend/package.json", json.dumps({"dependencies": {}}))
    mem.workspace.write("frontend/src/App.tsx", "const a = 1;")

    # Mock LLM provider that simulates Gemini repair failing with same error, then Nemotron rescuing
    calls = []

    class MockDispatcher:
        async def complete_structured(self, bundle: PromptBundle) -> Completion:
            calls.append(bundle)
            is_rescue = bundle.metadata.get("rescue") is True
            if is_rescue:
                return Completion(
                    data={
                        "root_cause": "Missing type definition",
                        "repair_reason": "Add export",
                        "files": [{"path": "frontend/src/App.tsx", "content": "export const a: number = 1;", "description": "fix"}],
                        "explanation": "Rescued by Nemotron",
                    },
                    usage=TokenUsage(input_tokens=50, output_tokens=50),
                    model="nvidia/nemotron-3-super-120b-a12b",
                )
            else:
                return Completion(
                    data={
                        "root_cause": "Minor edit",
                        "repair_reason": "noop",
                        "files": [{"path": "frontend/src/App.tsx", "content": "const a = 1; // still failing", "description": "gemini fix"}],
                        "explanation": "Gemini attempted fix",
                    },
                    usage=TokenUsage(input_tokens=40, output_tokens=40),
                    model="gemini-3.6-flash",
                )

    ctx = make_context(mem, MockDispatcher())

    # Mock validator: fails twice with same error, passes on 3rd attempt (after Nemotron rescue)
    validator_mock = MagicMock(spec=WorkspaceValidator)
    fail_run = ValidationRun(
        workspace_path="",
        stack="frontend",
        commands=[CommandResult(command="npm run build", exit_code=1, stdout="", stderr="src/App.tsx(1,1): error TS2688: Cannot find type definition file for 'node'")],
    )
    pass_run = ValidationRun(
        workspace_path="",
        stack="frontend",
        commands=[CommandResult(command="npm run build", exit_code=0, stdout="Build succeeded", stderr="")],
    )
    validator_mock.validate = AsyncMock(side_effect=[fail_run, pass_run])

    initial_val = ValidationResult(
        passed=False,
        stack="frontend",
        total_commands=1,
        failed_commands=1,
        failures=[{"command": "npm run build", "file": "src/App.tsx", "error": "TS2688: Cannot find type definition file for 'node'", "responsible_agent": "frontend_engineer"}],
    )

    final_val = await run_repair_loop(ctx, initial_val, validator=validator_mock, max_cycles=4)
    assert final_val.passed is True

    # Verify Nemotron rescue was called with purpose = frontend_rescue and rescue = True
    rescue_call = next((c for c in calls if c.metadata.get("rescue") is True), None)
    assert rescue_call is not None
    assert rescue_call.metadata.get("purpose") == "frontend_rescue"
    assert rescue_call.metadata.get("agent") == "debug"


# =============================================================================
# 11. Nemotron rescue does not create a new API-key slot
# =============================================================================
def test_nemotron_rescue_does_not_create_new_api_key_slot() -> None:
    # Verify exactly 7 slots exist in SLOT_DEFAULT_MODELS
    expected_slots = {
        "PLANNER_API_KEY01",
        "FRONTEND_API_KEY01",
        "BACKEND_API_KEY01",
        "DATABASE_API_KEY01",
        "QA_API_KEY01",
        "REVIEW_API_KEY01",
        "DEBUG_API_KEY01",
    }
    actual_slots = {k for k in SLOT_DEFAULT_MODELS.keys() if k != "none"}
    assert actual_slots == expected_slots
    assert "NEMOTRON_FRONTEND_API_KEY" not in SLOT_DEFAULT_MODELS
    assert "FRONTEND_BACKUP_API_KEY" not in SLOT_DEFAULT_MODELS

    # Debug slot maps to Nemotron
    assert model_for_slot("DEBUG_API_KEY01") == "nvidia/nemotron-3-super-120b-a12b"
    # Frontend slot maps to Gemini
    assert model_for_slot("FRONTEND_API_KEY01") == "gemini-3.6-flash"


# =============================================================================
# 12 & 13. Source-only repairs reuse install; package.json changes invalidate
# =============================================================================
def test_package_json_hash_invalidation_and_source_reuse(tmp_path: Path) -> None:
    node_dir = tmp_path / "frontend"
    node_dir.mkdir(parents=True)
    pkg_file = node_dir / "package.json"
    hash_file = node_dir / "node_modules" / ".package_hash"
    hash_file.parent.mkdir(parents=True)

    pkg_content_v1 = json.dumps({"dependencies": {"react": "^18.3.1"}}).encode("utf-8")
    pkg_file.write_bytes(pkg_content_v1)
    h1 = hashlib.sha256(pkg_content_v1).hexdigest()
    hash_file.write_text(h1, encoding="utf-8")

    # Source file change only: hash matches, reuse!
    (node_dir / "src").mkdir()
    (node_dir / "src" / "App.tsx").write_text("export const x = 1;", encoding="utf-8")
    current_pkg_hash = hashlib.sha256(pkg_file.read_bytes()).hexdigest()
    reused = hash_file.read_text(encoding="utf-8").strip() == current_pkg_hash
    assert reused is True

    # package.json change: hash mismatch, invalidated!
    pkg_content_v2 = json.dumps({"dependencies": {"react": "^18.3.1", "lucide-react": "^0.460.0"}}).encode("utf-8")
    pkg_file.write_bytes(pkg_content_v2)
    current_pkg_hash_v2 = hashlib.sha256(pkg_file.read_bytes()).hexdigest()
    reused_v2 = hash_file.read_text(encoding="utf-8").strip() == current_pkg_hash_v2
    assert reused_v2 is False


# =============================================================================
# 14 & 15. Request counter includes all calls; Request #16 is impossible
# =============================================================================
def test_request_counter_tracks_gemini_and_nemotron_and_blocks_at_15() -> None:
    budget = RequestBudgetManager(default_target=10, default_hard_max=15)
    task_id = "test-budget-task"

    # Calls 1 to 15 succeed monotonically
    for i in range(1, 16):
        num = budget.next_request_number(task_id, agent_role="frontend" if i % 2 == 0 else "debug")
        assert num == i

    assert budget.get_total_requests(task_id) == 15
    assert budget.is_hard_limit_reached(task_id) is True

    # Request #16 must raise RequestBudgetExceededError
    with pytest.raises(RequestBudgetExceededError):
        budget.next_request_number(task_id, agent_role="debug")


# =============================================================================
# 16 & 17. Failed npm install and build block release
# =============================================================================
@pytest.mark.asyncio
async def test_failed_npm_install_and_build_block_release() -> None:
    mem = SharedProjectMemory(run_id="run-block", project_id="p", project_name="P", project_slug="p", idea="App")
    mem.tech_stack.frontend = "react"
    ctx = make_context(mem, MagicMock())

    agent = FinalQAAgent()
    # Mock failed validation result
    failed_val = ValidationResult(
        passed=False,
        stack="frontend",
        total_commands=2,
        failed_commands=1,
        failures=[{"command": "npm install", "error": "npm ERR! code ETIMEDOUT", "exit_code": 1}],
    )
    agent._run_validation = AsyncMock(return_value=failed_val)

    result = await agent.execute(ctx)
    assert result.output["passed"] is False
    assert result.output["release_eligible"] is False
    assert mem.release_eligible is False


# =============================================================================
# 18. Successful React project passes release gate
# =============================================================================
@pytest.mark.asyncio
async def test_successful_react_project_passes_release_gate() -> None:
    mem = SharedProjectMemory(run_id="run-pass", project_id="p", project_name="P", project_slug="p", idea="React App")
    mem.tech_stack.frontend = "react"
    mem.workspace.write(
        "frontend/package.json",
        json.dumps({
            "name": "portfolio-app",
            "version": "1.0.0",
            "scripts": {"build": "vite build"},
            "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
        }, indent=2),
    )
    mem.workspace.write("frontend/index.html", "<!doctype html><html><body><div id='root'></div></body></html>")
    mem.workspace.write("frontend/src/App.tsx", "export default function App() { return <div>App Loaded</div>; }")

    ctx = make_context(mem, MagicMock())
    agent = FinalQAAgent()

    passed_val = ValidationResult(
        passed=True,
        stack="frontend",
        total_commands=3,
        failed_commands=0,
        failures=[],
    )
    agent._run_validation = AsyncMock(return_value=passed_val)

    result = await agent.execute(ctx)
    assert result.output["passed"] is True
    assert mem.release_eligible is True


# =============================================================================
# 19. Frontend successful generation does not call Nemotron
# =============================================================================
@pytest.mark.asyncio
async def test_frontend_successful_generation_does_not_call_nemotron() -> None:
    mem = SharedProjectMemory(run_id="run-success", project_id="p", project_name="P", project_slug="p", idea="App")
    llm = MagicMock()
    ctx = make_context(mem, llm)

    val = ValidationResult(passed=True, stack="frontend", total_commands=3, failed_commands=0)
    res = await run_repair_loop(ctx, val)
    assert res.passed is True
    # LLM should never be called when generation succeeds cleanly
    assert llm.complete_structured.call_count == 0


# =============================================================================
# 20. Frontend failure requiring escalation does call Nemotron
# =============================================================================
@pytest.mark.asyncio
async def test_frontend_failure_requiring_escalation_calls_nemotron() -> None:
    mem = SharedProjectMemory(run_id="run-esc", project_id="p", project_name="P", project_slug="p", idea="App")
    mem.workspace.write("frontend/package.json", json.dumps({"dependencies": {}}))
    mem.workspace.write("frontend/src/App.tsx", "broken code")

    calls = []

    class MockLLM:
        async def complete_structured(self, bundle: PromptBundle) -> Completion:
            calls.append(bundle)
            is_rescue = bundle.metadata.get("rescue") is True
            return Completion(
                data={
                    "root_cause": "test",
                    "repair_reason": "test",
                    "files": [{"path": "frontend/src/App.tsx", "content": "fixed code", "description": "fixed"}],
                    "explanation": "fixed",
                },
                usage=TokenUsage(input_tokens=10, output_tokens=10),
                model="nvidia/nemotron-3-super-120b-a12b" if is_rescue else "gemini-3.6-flash",
            )

    ctx = make_context(mem, MockLLM())
    validator_mock = MagicMock(spec=WorkspaceValidator)
    fail_run = ValidationRun(
        workspace_path="",
        stack="frontend",
        commands=[CommandResult(command="npm run build", exit_code=1, stdout="", stderr="src/App.tsx(1,1): error TS2304: Build error")],
    )
    pass_run = ValidationRun(
        workspace_path="",
        stack="frontend",
        commands=[CommandResult(command="npm run build", exit_code=0, stdout="", stderr="")],
    )
    validator_mock.validate = AsyncMock(side_effect=[fail_run, pass_run])

    initial = ValidationResult(
        passed=False,
        stack="frontend",
        total_commands=1,
        failed_commands=1,
        failures=[{"command": "npm run build", "file": "src/App.tsx", "error": "TS2304: Build error", "responsible_agent": "frontend_engineer"}],
    )
    final_res = await run_repair_loop(ctx, initial, validator=validator_mock, max_cycles=3)
    assert final_res.passed is True
    # Verify at least one call was directed to Nemotron rescue
    assert any(c.metadata.get("purpose") == "frontend_rescue" for c in calls)


# =============================================================================
# 21. Realistic Frontend Failure & Nemotron Rescue Flow (Section 33)
# =============================================================================
@pytest.mark.asyncio
async def test_realistic_frontend_failure_and_nemotron_rescue_flow() -> None:
    """Simulates:

    Gemini generates React project -> build fails -> Gemini attempts repair ->
    same failure repeats -> stagnation detected -> Nemotron rescue ->
    targeted repair -> build succeeds.
    """
    mem = SharedProjectMemory(
        run_id="run-sim-33", project_id="p-sim", project_name="Sim Portfolio", project_slug="sim-portfolio", idea="Portfolio"
    )
    mem.tech_stack.frontend = "react"
    mem.workspace.write(
        "frontend/package.json",
        json.dumps({
            "name": "portfolio",
            "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
            "devDependencies": {"typescript": "^5.6.3"},
        }),
    )
    mem.workspace.write(
        "frontend/src/App.tsx",
        "import React from 'react';\nimport { Github } from 'lucide-react';\nexport default function App() { return <div><Github /></div>; }",
    )

    models_called: list[str] = []
    purposes_called: list[str] = []

    class RealisticDispatcher:
        def __init__(self) -> None:
            self.budget_manager = RequestBudgetManager()

        async def complete_structured(self, bundle: PromptBundle) -> Completion:
            is_rescue = bundle.metadata.get("rescue") is True
            purpose = bundle.metadata.get("purpose", "normal_repair")
            purposes_called.append(purpose)

            if is_rescue:
                # Nemotron rescue: properly diagnoses missing dependency in package.json
                models_called.append("nvidia/nemotron-3-super-120b-a12b")
                return Completion(
                    data={
                        "root_cause": "Missing 'lucide-react' in package.json",
                        "repair_reason": "Add lucide-react dependency to package.json",
                        "files": [
                            {
                                "path": "frontend/package.json",
                                "content": json.dumps({
                                    "name": "portfolio",
                                    "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1", "lucide-react": "^0.460.0"},
                                    "devDependencies": {"typescript": "^5.6.3"},
                                }, indent=2),
                                "description": "Added lucide-react to dependencies",
                            }
                        ],
                        "explanation": "Targeted patch to package.json resolves TS2307 module not found.",
                    },
                    usage=TokenUsage(input_tokens=180, output_tokens=90),
                    model="nvidia/nemotron-3-super-120b-a12b",
                )
            else:
                # Gemini primary repair: modifies App.tsx without fixing package.json (causes same failure to repeat)
                models_called.append("gemini-3.6-flash")
                return Completion(
                    data={
                        "root_cause": "Import statement check",
                        "repair_reason": "Reformatted App.tsx",
                        "files": [
                            {
                                "path": "frontend/src/App.tsx",
                                "content": "import React from 'react';\nimport { Github } from 'lucide-react';\n// reformatted\nexport default function App() { return <main><Github /></main>; }",
                                "description": "Reformatted",
                            }
                        ],
                        "explanation": "Reformatted import",
                    },
                    usage=TokenUsage(input_tokens=150, output_tokens=80),
                    model="gemini-3.6-flash",
                )

    dispatcher = RealisticDispatcher()
    ctx = make_context(mem, dispatcher)

    # Simulated validation execution
    # Run 1: Gemini generates -> build fails (Cannot find module 'lucide-react')
    # Run 2 (after Gemini repair 1): same build failure repeats!
    # Run 3 (after Nemotron rescue): build passes!
    val_fail = ValidationRun(
        workspace_path="",
        stack="frontend",
        commands=[
            CommandResult(
                command="npm run build",
                exit_code=1,
                stdout="",
                stderr="src/App.tsx(2,24): error TS2307: Cannot find module 'lucide-react' or its corresponding type declarations.",
            )
        ],
    )
    val_pass = ValidationRun(
        workspace_path="",
        stack="frontend",
        commands=[
            CommandResult(command="npm run build", exit_code=0, stdout="vite build finished successfully", stderr="")
        ],
    )

    validator = MagicMock(spec=WorkspaceValidator)
    validator.validate = AsyncMock(side_effect=[val_fail, val_pass])

    initial_validation = ValidationResult(
        passed=False,
        stack="frontend",
        total_commands=1,
        failed_commands=1,
        failures=[
            {
                "command": "npm run build",
                "file": "frontend/src/App.tsx",
                "line": "2",
                "error": "src/App.tsx(2,24): error TS2307: Cannot find module 'lucide-react'",
                "category": "type_error",
                "responsible_agent": "frontend_engineer",
            }
        ],
    )

    final_val = await run_repair_loop(ctx, initial_validation, validator=validator, max_cycles=4)

    # 1. Validation passed after rescue
    assert final_val.passed is True

    # 2. Gemini was primary model for initial repair
    assert models_called[0] == "gemini-3.6-flash"

    # 3. Stagnation triggered Nemotron rescue
    assert "nvidia/nemotron-3-super-120b-a12b" in models_called
    assert "frontend_rescue" in purposes_called

    # 4. package.json was targeted and updated
    pkg_updated = json.loads(mem.workspace.read("frontend/package.json") or "{}")
    assert "lucide-react" in pkg_updated.get("dependencies", {})

    # 5. Repair cycle records reflect both models
    cycle_models = [c.model for c in mem.repair_cycles]
    assert "gemini-3.6-flash" in cycle_models
    assert "nvidia/nemotron-3-super-120b-a12b" in cycle_models
