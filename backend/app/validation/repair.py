"""Self-repair loop and Frontend Reliability Rescue Pipeline for AEGIS AI.

When validation fails, this loop:
1. Computes deterministic, normalized failure signatures (scrubbing timestamps, temp paths, hex addresses).
2. Selects the responsible engineering agent (routed through assigned 7-slot model).
   - Frontend Engineer (Gemini 3.6 Flash) is the primary repair model for frontend failures.
3. Detects stagnation when the exact same failure signature repeats across cycles.
4. On stagnation, escalates to Nemotron Frontend Rescue via the DEBUG slot (DEBUG_API_KEY01 with
   nvidia/nemotron-3-super-120b-a12b).
5. Provides a structured failure context (exact commands, exit codes, affected files, package.json,
   tsconfig, previous repair attempts).
6. Applies targeted minimal patches (affected files only, preventing random whole-project rewrites).
7. Deterministically validates again. Stops if still failing rather than looping indefinitely.
"""

from __future__ import annotations

import json
import posixpath
import re
from datetime import UTC, datetime
from typing import Any

from app.agents.context import AgentContext
from app.core.config import settings
from app.core.enums import AgentRole, LogLevel
from app.core.logging import get_logger
from app.llm import schema as s
from app.llm.types import PromptBundle
from app.validation.classifier import classify_failures
from app.validation.executor import WorkspaceValidator
from app.workflow.memory import RepairCycle, ValidationResult

logger = get_logger(__name__)

REPAIR_FILES_SCHEMA = s.obj(
    {
        "root_cause": s.string("Root cause analysis of the exact failure."),
        "repair_reason": s.string("Explanation of why these specific files are changed."),
        "files": s.array(
            s.obj(
                {
                    "path": s.string("Repository-relative path of the modified/fixed file."),
                    "content": s.string("Complete, corrected file content."),
                    "description": s.string("Summary of what was fixed in this file."),
                }
            ),
            description="The minimal set of files changed to fix the validation failure.",
        ),
        "explanation": s.string("Brief summary of the fix and how it ensures successful build."),
    }
)


def normalize_failure_signature(failure: dict[str, Any]) -> str:
    """Create a deterministic, normalized signature for one failure.

    Normalizes dynamic information like timestamps, temp directories, hex memory addresses,
    and request IDs.
    """
    cmd = str(failure.get("command", "")).strip()
    file_path = str(failure.get("file", "")).strip()
    category = str(failure.get("category", "")).strip()
    error_raw = str(failure.get("error", "")).strip()

    # 1. Strip ANSI escape sequences
    error = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", error_raw)

    # 2. Extract specific error code (TS2688, TS2307, E123, ERR_*)
    code_match = re.search(r"\b(TS\d{3,5}|E\d{3,5}|ERR_[A-Z0-9_]+)\b", error)
    code = code_match.group(1) if code_match else category or "ERROR"

    # 3. Strip bracketed annotations (e.g. [duration: ...], [time ...])
    error = re.sub(r"\[.*?\]", "", error)

    # 4. Strip dynamic paths (Windows/POSIX temporary workspaces, drive letters, etc.)
    error = re.sub(r"([A-Za-z]:)?(?:[\\/][\w\.\-]+)+(?:aegis-[^\\/\s]+|Temp[^\\/\s]*)[\\/]?", "", error)
    error = re.sub(r"\baegis-[a-zA-Z0-9_\-]+", "", error)
    error = error.replace("\\", "/")

    # 5. Strip timestamps, hex addresses, request IDs, durations
    error = re.sub(r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", "", error)
    error = re.sub(r"0x[0-9a-fA-F]+", "", error)
    error = re.sub(r"req_[a-zA-Z0-9_]+", "", error)
    error = re.sub(r"\b\d+(\.\d+)?(ms|s|min)\b", "", error)

    # 6. Strip compiler prefixes and extract core first error line
    # Strip e.g. "src/App.tsx(2,24): error TS2307: " or "TS2307: "
    error = re.sub(r"^[\w\.\-\/\\]+\(\d+(?:,\d+)?\):\s*(?:error\s*)?(?:[A-Z0-9]+:)?\s*", "", error.strip())
    error = re.sub(r"^(?:error\s*)?(?:[A-Z0-9]+:)?\s*", "", error.strip())
    error = re.sub(r"\s+or its corresponding type declarations\.?", "", error)

    first_err_line = ""
    for line in error.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned and not cleaned.startswith(("at ", "npm error", "npm notice")):
            first_err_line = cleaned[:100]
            break
    if not first_err_line:
        first_err_line = error[:100]

    # 7. Normalize file path (strip leading frontend/, backend/, or ./ so compiler and repo paths align)
    norm_file = posixpath.normpath(file_path.replace("\\", "/")) if file_path else "unknown"
    for prefix in ("frontend/", "backend/", "./"):
        if norm_file.startswith(prefix):
            norm_file = norm_file[len(prefix):]

    return f"{cmd}|{code}|{first_err_line}|{norm_file}"


def compute_aggregate_failure_signature(failures: list[dict[str, Any]]) -> str:
    """Create a composite normalized signature for a set of failures."""
    if not failures:
        return "none"
    sigs = [normalize_failure_signature(f) for f in failures]
    sigs.sort()
    return ";;".join(sigs)


def build_structured_rescue_context(
    ctx: AgentContext,
    failures: list[dict[str, Any]],
    repair_history: list[dict[str, Any]],
    current_request_count: int = 0,
) -> dict[str, Any]:
    """Construct structured failure context for Nemotron Frontend Rescue.

    Section 7 compliance:
    - Original user requirement
    - Project type
    - Current project structure
    - Exact failing command
    - Exact stdout where relevant
    - Exact stderr
    - Exit code
    - Timeout information
    - Affected files
    - Relevant source snippets
    - package.json
    - tsconfig.json
    - eslint configuration if applicable
    - Dependency state
    - Previous repair attempts
    - Previous failure signatures
    - Current request count
    """
    memory = ctx.memory
    workspace = memory.workspace

    # Gather affected files from failure reports
    affected_files: list[str] = []
    for f in failures:
        raw_f = str(f.get("file", "")).strip()
        if raw_f and raw_f != "N/A" and raw_f != "unknown":
            norm_f = posixpath.normpath(raw_f.replace("\\", "/"))
            if norm_f not in affected_files:
                affected_files.append(norm_f)

    # If no specific file was identified, include primary entrypoints
    if not affected_files:
        for candidate in ("frontend/package.json", "frontend/tsconfig.json", "frontend/src/App.tsx", "frontend/src/main.tsx"):
            if workspace.exists(candidate) and candidate not in affected_files:
                affected_files.append(candidate)

    # Relevant source snippets
    source_snippets: dict[str, str] = {}
    for path in affected_files[:8]:
        content = workspace.read(path)
        if content:
            source_snippets[path] = content[:3000]

    first_failure = failures[0] if failures else {}

    # Read config files
    pkg_json = workspace.read("frontend/package.json") or workspace.read("package.json") or ""
    tsconfig_json = (
        workspace.read("frontend/tsconfig.json")
        or workspace.read("frontend/tsconfig.node.json")
        or workspace.read("tsconfig.json")
        or ""
    )
    eslint_config = (
        workspace.read("frontend/.eslintrc.json")
        or workspace.read("frontend/eslint.config.js")
        or workspace.read("frontend/.eslintrc.js")
        or ""
    )

    return {
        "original_user_requirement": memory.idea or memory.user_prompt or memory.analysis.project_overview,
        "project_type": memory.tech_stack.frontend or "react",
        "current_project_structure": [f.path for f in workspace.files if not f.path.startswith("artifacts/")][:50],
        "exact_failing_command": first_failure.get("command", "npm run build"),
        "exact_stdout": str(first_failure.get("stdout", ""))[:1200],
        "exact_stderr": str(first_failure.get("error", first_failure.get("stderr", "")))[:2500],
        "exit_code": first_failure.get("exit_code", 1),
        "timeout_information": bool(first_failure.get("timed_out", False)),
        "affected_files": affected_files,
        "relevant_source_snippets": source_snippets,
        "package_json": pkg_json[:2000],
        "tsconfig_json": tsconfig_json[:2000],
        "eslint_configuration": eslint_config[:1000] if eslint_config else "None configured",
        "dependency_state": "Synchronized with declared package.json",
        "previous_repair_attempts": repair_history,
        "previous_failure_signatures": [r.get("failure_signature_before") for r in repair_history if r.get("failure_signature_before")],
        "current_request_count": current_request_count,
    }


async def run_repair_loop(
    ctx: AgentContext,
    initial_validation: ValidationResult,
    *,
    validator: WorkspaceValidator | None = None,
    max_cycles: int | None = None,
) -> ValidationResult:
    """Execute the repair loop with Gemini primary repair and Nemotron Frontend Rescue on stagnation."""
    if initial_validation.passed:
        return initial_validation

    limit = max_cycles or settings.max_repair_cycles
    current_validation = initial_validation
    validator = validator or WorkspaceValidator(timeout_seconds=120)

    seen_failure_signatures: dict[str, int] = {}
    nemotron_rescue_invoked = False
    repair_history_records: list[dict[str, Any]] = []

    for cycle_num in range(1, limit + 1):
        failures = current_validation.failures
        if not failures:
            break

        sig_before = compute_aggregate_failure_signature(failures)
        count_seen = seen_failure_signatures.get(sig_before, 0)
        seen_failure_signatures[sig_before] = count_seen + 1

        is_frontend_failure = any(
            f.get("responsible_agent") == AgentRole.FRONTEND_ENGINEER.value
            or "frontend" in str(f.get("command", "")).lower()
            or "npm" in str(f.get("command", "")).lower()
            or "tsc" in str(f.get("command", "")).lower()
            for f in failures
        )

        # Stagnation rule: same failure signature repeats without progress
        is_stagnation = count_seen >= 1

        pre_cycle_snapshot = ctx.memory.workspace.create_snapshot()

        if is_stagnation and is_frontend_failure and not nemotron_rescue_invoked:
            # Escalate to Nemotron Frontend Rescue via DEBUG slot
            nemotron_rescue_invoked = True
            await ctx.log(
                AgentRole.QA_ENGINEER,
                f"Repair stagnation detected on signature '{sig_before}'. "
                "Stopping normal Gemini repair. Escalating to Nemotron Frontend Rescue (nvidia/nemotron-3-super-120b-a12b via DEBUG slot).",
                level=LogLevel.WARNING,
            )

            modified_paths, rescue_explanation = await _rescue_frontend_nemotron(
                ctx,
                failures=failures,
                repair_history=repair_history_records,
                cycle_num=cycle_num,
            )

            # Re-validate workspace
            workspace_files = {entry.path: entry.content for entry in ctx.memory.workspace.files if entry.content}
            recheck_run = await validator.validate(
                workspace_files, run_id=f"{ctx.memory.run_id}-repair-{cycle_num}-rescue"
            )
            recheck_class = classify_failures(recheck_run.commands)
            sig_after = compute_aggregate_failure_signature([f.as_dict() for f in recheck_class.failures])

            result_str = "passed" if recheck_run.passed else "failed"
            cycle_record = RepairCycle(
                cycle_number=cycle_num,
                failures_found=len(failures),
                agents_involved=["nemotron_frontend_rescue"],
                files_modified=modified_paths,
                validation_passed_after=recheck_run.passed,
                timestamp=datetime.now(UTC).isoformat(),
                model="nvidia/nemotron-3-super-120b-a12b",
                failure_signature_before=sig_before,
                failure_signature_after=sig_after,
                result=result_str,
            )
            ctx.memory.record_repair_cycle(cycle_record)
            repair_history_records.append(cycle_record.as_dict())

            current_validation = ValidationResult(
                passed=recheck_run.passed,
                stack=recheck_run.stack,
                total_commands=recheck_run.total_commands,
                failed_commands=len(recheck_run.failed_commands),
                failures=[f.as_dict() for f in recheck_class.failures],
                timestamp=datetime.now(UTC).isoformat(),
                workspace_fingerprint=ctx.memory.workspace.fingerprint,
            )

            if current_validation.passed:
                await ctx.log(
                    AgentRole.QA_ENGINEER,
                    f"Nemotron Frontend Rescue SUCCESSFUL on cycle {cycle_num}! Build and typecheck pass.",
                    level=LogLevel.INFO,
                )
                break
            else:
                await ctx.log(
                    AgentRole.QA_ENGINEER,
                    f"Nemotron Frontend Rescue could not resolve failure signature. Halting repair loop to prevent infinite requests.",
                    level=LogLevel.ERROR,
                )
                break

        elif is_stagnation and nemotron_rescue_invoked:
            await ctx.log(
                AgentRole.QA_ENGINEER,
                f"Failure persisted after Nemotron rescue attempt. Stopping repair loop to respect hard budget limits.",
                level=LogLevel.WARNING,
            )
            break

        # Normal repair path (Gemini for Frontend/Backend/Database)
        await ctx.progress(
            AgentRole.QA_ENGINEER,
            20 + int(cycle_num * 10),
            f"Repair cycle {cycle_num}/{limit}: resolving {len(failures)} failure(s)",
        )
        await ctx.log(
            AgentRole.QA_ENGINEER,
            f"Starting repair cycle {cycle_num}/{limit} for {len(failures)} issue(s)",
            level=LogLevel.INFO,
        )

        by_agent: dict[str, list[dict[str, Any]]] = {}
        for f in failures:
            agent_key = f.get("responsible_agent", AgentRole.FRONTEND_ENGINEER.value if is_frontend_failure else AgentRole.BACKEND_ENGINEER.value)
            by_agent.setdefault(agent_key, []).append(f)

        agents_involved = list(by_agent.keys())
        all_modified_files: list[str] = []

        for agent_key, agent_failures in by_agent.items():
            try:
                role = AgentRole(agent_key)
            except ValueError:
                role = AgentRole.FRONTEND_ENGINEER if is_frontend_failure else AgentRole.BACKEND_ENGINEER

            modified = await _repair_agent_failures(ctx, role, agent_failures, cycle_num=cycle_num)
            all_modified_files.extend(modified)

        if not all_modified_files:
            await ctx.log(
                AgentRole.QA_ENGINEER,
                f"Repair cycle {cycle_num}: no files were modified by repair agents.",
                level=LogLevel.WARNING,
            )

        workspace_files = {entry.path: entry.content for entry in ctx.memory.workspace.files if entry.content}
        recheck_run = await validator.validate(
            workspace_files, run_id=f"{ctx.memory.run_id}-repair-{cycle_num}"
        )
        recheck_class = classify_failures(recheck_run.commands)
        sig_after = compute_aggregate_failure_signature([f.as_dict() for f in recheck_class.failures])

        result_str = "passed" if recheck_run.passed else ("regressed" if len(recheck_run.failed_commands) > len(failures) else "failed")

        # Rollback check if regressions introduced
        if len(recheck_run.failed_commands) > len(failures) + 1 and not recheck_run.passed:
            ctx.memory.workspace.restore_snapshot(pre_cycle_snapshot)
            await ctx.log(
                AgentRole.QA_ENGINEER,
                f"Repair cycle {cycle_num} introduced regressions. Rolled back workspace changes.",
                level=LogLevel.WARNING,
            )
            cycle_record = RepairCycle(
                cycle_number=cycle_num,
                failures_found=len(failures),
                agents_involved=agents_involved,
                files_modified=[],
                validation_passed_after=False,
                timestamp=datetime.now(UTC).isoformat(),
                model="gemini-3.6-flash",
                failure_signature_before=sig_before,
                failure_signature_after=sig_before,
                result="regressed_rolled_back",
            )
            ctx.memory.record_repair_cycle(cycle_record)
            repair_history_records.append(cycle_record.as_dict())
            continue

        current_validation = ValidationResult(
            passed=recheck_run.passed,
            stack=recheck_run.stack,
            total_commands=recheck_run.total_commands,
            failed_commands=len(recheck_run.failed_commands),
            failures=[f.as_dict() for f in recheck_class.failures],
            timestamp=datetime.now(UTC).isoformat(),
            workspace_fingerprint=ctx.memory.workspace.fingerprint,
        )

        cycle_record = RepairCycle(
            cycle_number=cycle_num,
            failures_found=len(failures),
            agents_involved=agents_involved,
            files_modified=all_modified_files,
            validation_passed_after=current_validation.passed,
            timestamp=datetime.now(UTC).isoformat(),
            model="gemini-3.6-flash",
            failure_signature_before=sig_before,
            failure_signature_after=sig_after,
            result=result_str,
        )
        ctx.memory.record_repair_cycle(cycle_record)
        repair_history_records.append(cycle_record.as_dict())

        if current_validation.passed:
            await ctx.log(
                AgentRole.QA_ENGINEER,
                f"Repair cycle {cycle_num} SUCCESSFUL: project builds and passes checks!",
                level=LogLevel.INFO,
            )
            break
        else:
            await ctx.log(
                AgentRole.QA_ENGINEER,
                f"Repair cycle {cycle_num} partially resolved issues; {current_validation.failed_commands} command(s) still failing.",
                level=LogLevel.WARNING,
            )

    return current_validation


async def _repair_agent_failures(
    ctx: AgentContext,
    role: AgentRole,
    failures: list[dict[str, Any]],
    cycle_num: int = 1,
) -> list[str]:
    """Ask a single responsible implementation agent (Gemini 3.6 Flash) to fix designated failures."""
    relevant_files: dict[str, str] = {}
    for f in failures:
        file_path = str(f.get("file", "")).strip()
        if file_path and ctx.memory.workspace.exists(file_path):
            file_content = ctx.memory.workspace.read(file_path)
            if file_content:
                relevant_files[file_path] = file_content

    # If no specific file path found in compiler/linter error, provide only relevant configs and entrypoint
    if not relevant_files:
        prefix = "frontend/" if role is AgentRole.FRONTEND_ENGINEER else "backend/"
        for candidate in ("frontend/package.json", "frontend/tsconfig.json", "frontend/src/App.tsx"):
            if ctx.memory.workspace.exists(candidate):
                relevant_files[candidate] = ctx.memory.workspace.read(candidate) or ""

    errors_block = "\n\n".join(
        f"--- Failure #{i + 1} ---\n"
        f"Command: {f.get('command')}\n"
        f"Exit code: {f.get('exit_code')}\n"
        f"Category: {f.get('category')}\n"
        f"File: {f.get('file', 'N/A')}:{f.get('line', 'N/A')}\n"
        f"Error details:\n{f.get('error', 'Unknown error')}"
        for i, f in enumerate(failures[:5])
    )

    files_block = "\n\n".join(
        f"=== {path} ===\n{content}"
        for path, content in relevant_files.items()
    )

    tech_stack_desc = (
        f"Frontend: {ctx.memory.tech_stack.frontend or 'vanilla'}, "
        f"Backend: {ctx.memory.tech_stack.backend or 'none'}, "
        f"Database: {ctx.memory.tech_stack.database or 'none'}"
    )

    prompt_instruction = f"""\
You are the {role.value.replace('_', ' ').title()}.
A validation command failed when building or running the project:

{errors_block}

## Tech Stack
{tech_stack_desc}

## Relevant Source Files
{files_block if files_block else "(See full workspace if necessary)"}

## Strict Targeted Repair Instructions
1. Root cause analysis: Identify the EXACT missing module, type, or syntax error.
2. Targeted repair: Modify ONLY the affected files directly responsible for this failure.
3. Do NOT rewrite unrelated files, styling, or architecture.
4. If a module or dependency is missing, check the source import and package.json.
5. Every file you return MUST be complete, valid syntax, and runnable.
6. Return the corrected files in the structured output.
"""

    bundle = PromptBundle(
        cacheable_system=f"ROLE: {role.value}. Fix build and validation failures with minimal, precise edits.",
        user_message=prompt_instruction,
        schema=REPAIR_FILES_SCHEMA,
        metadata={
            "agent": role.value,
            "repair": True,
            "purpose": "normal_repair",
            "cycle": cycle_num,
        },
    )

    try:
        completion = await ctx.llm.complete_structured(bundle)
        fix_files = completion.data.get("files", [])
        if not fix_files:
            return []

        accepted, _ = ctx.memory.workspace.write_many(fix_files, produced_by=role)
        modified_paths = [a.path for a in accepted]

        explanation = completion.data.get("explanation", "Applied targeted fix.")
        await ctx.log(
            role,
            f"Repaired {len(modified_paths)} file(s): {', '.join(modified_paths)}. Note: {explanation}",
            level=LogLevel.INFO,
        )
        return modified_paths

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "repair_agent_call_failed",
            extra={"agent": role.value, "error": str(exc)},
        )
        await ctx.log(
            role,
            f"Repair agent execution encountered an error: {exc}",
            level=LogLevel.WARNING,
        )
        return []


async def _rescue_frontend_nemotron(
    ctx: AgentContext,
    failures: list[dict[str, Any]],
    repair_history: list[dict[str, Any]],
    cycle_num: int = 1,
) -> tuple[list[str], str]:
    """Execute Nemotron Frontend Rescue via DEBUG_API_KEY01.

    Invoked when Gemini frontend repair has stagnated on the same failure signature.
    Receives structured failure context and makes a specialist targeted repair.
    """
    task_id = str(ctx.memory.run_id)
    req_count = 0
    if hasattr(ctx.llm, "budget_manager"):
        req_count = ctx.llm.budget_manager.get_total_requests(task_id)

    context = build_structured_rescue_context(
        ctx,
        failures=failures,
        repair_history=repair_history,
        current_request_count=req_count,
    )

    rescue_instruction = f"""\
You are NVIDIA Nemotron-3 Super 120B acting as the Lead Systems Architect & Frontend Rescue Debugger.
The primary frontend generation model has stagnated on a build/typecheck failure.
You have been escalated via the DEBUG slot to perform a high-precision targeted rescue.

## STRUCTURED FAILURE CONTEXT
- Original User Requirement: {context['original_user_requirement']}
- Project Type: {context['project_type']}
- Failing Command: {context['exact_failing_command']}
- Exit Code: {context['exit_code']}
- Timed Out: {context['timeout_information']}
- Affected Files: {', '.join(context['affected_files'])}
- Current Request Count: {context['current_request_count']}/15

## EXACT ERROR OUTPUT (STDERR / STDOUT)
{context['exact_stderr']}
{context['exact_stdout']}

## CONFIGURATION FILES
### package.json
{context['package_json']}

### tsconfig.json
{context['tsconfig_json']}

## RELEVANT SOURCE SNIPPETS
{json.dumps(context['relevant_source_snippets'], indent=2)}

## PREVIOUS REPAIR ATTEMPTS & FAILURE SIGNATURES
{json.dumps(context['previous_repair_attempts'], indent=2)}

## STRICT RESCUE RULES
1. Perform a root-cause diagnosis of why previous repairs failed to resolve this exact error.
2. Make the MINIMAL TARGETED PATCH. If a dependency is missing, patch package.json. If an import or type is wrong, patch that exact source file.
3. Do NOT rewrite unrelated UI components, styles.css, or index.html.
4. Output complete, valid, syntactically correct files ready for build.
"""

    bundle = PromptBundle(
        cacheable_system="ROLE: Nemotron Frontend Rescue Engineer. Perform precise, targeted repair of persistent frontend build/type failures.",
        user_message=rescue_instruction,
        schema=REPAIR_FILES_SCHEMA,
        metadata={
            "agent": "debug",
            "rescue": True,
            "purpose": "frontend_rescue",
            "cycle": cycle_num,
        },
    )

    try:
        completion = await ctx.llm.complete_structured(bundle)
        fix_files = completion.data.get("files", [])
        if not fix_files:
            return [], "No files produced by Nemotron rescue."

        accepted, _ = ctx.memory.workspace.write_many(fix_files, produced_by=AgentRole.FINAL_QA)
        modified_paths = [a.path for a in accepted]
        explanation = completion.data.get("explanation", "Nemotron targeted rescue applied.")

        await ctx.log(
            AgentRole.QA_ENGINEER,
            f"Nemotron Frontend Rescue modified {len(modified_paths)} file(s): {', '.join(modified_paths)}. Note: {explanation}",
            level=LogLevel.INFO,
        )
        return modified_paths, explanation

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "nemotron_rescue_call_failed",
            extra={"error": str(exc)},
        )
        await ctx.log(
            AgentRole.QA_ENGINEER,
            f"Nemotron rescue encountered an error: {exc}",
            level=LogLevel.ERROR,
        )
        return [], str(exc)
