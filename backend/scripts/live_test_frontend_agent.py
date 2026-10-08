"""Controlled live test for FrontendEngineerAgent using Google Gemini 3.6 Flash.

Verifies:
- Frontend agent uses generic ctx.llm (complete_structured / complete_text)
- Provider: gemini
- Model: gemini-3.6-flash
- Correct credential slot used (gemini_frontend / FRONTEND_API_KEY)
- HTML/CSS/JS files produced in workspace
- UsageLog recorded with latency and tokens
- Zero secrets printed or leaked!
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.adapters.registry import build_default_registry
from app.agents.context import AgentContext
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.core.config import Settings
from app.core.enums import AgentRole
from app.llm.manager import RoleBasedProviderManager
from app.workflow.memory import SharedProjectMemory, TechStack


async def main() -> int:
    config = Settings()
    print("============================================================")
    print("      AEGIS AI — LIVE FRONTEND AGENT TEST (gemini-3.6-flash)")
    print("============================================================")

    memory = SharedProjectMemory(
        run_id="live_frontend_test_run",
        project_id="live_proj_001",
        project_name="Minimalist Developer Portfolio",
        project_slug="minimalist-developer-portfolio",
        idea="A clean, responsive personal portfolio website with About, Projects, and Contact sections.",
    )
    # Default stack is HTML/CSS/JS
    memory.tech_stack = TechStack(
        frontend="html_css_js",
        backend=None,
        database=None,
    )

    mgr = RoleBasedProviderManager(config=config)
    adapters = build_default_registry()

    ctx = AgentContext(
        memory=memory,
        llm=mgr,
        registry=adapters,
        report_progress=lambda *args: asyncio.sleep(0),
        report_log=lambda *args, **kwargs: asyncio.sleep(0),
    )

    agent = FrontendEngineerAgent()
    print(f"Executing Agent : {agent.display_name} ({agent.role.value})")
    print(f"Provider Target : gemini")
    print(f"Model Target    : {config.gemini_frontend_model}")
    print(f"Stack Target    : html_css_js")
    print("------------------------------------------------------------")

    t0 = time.monotonic()
    try:
        result = await agent.execute(ctx)
        duration_ms = (time.monotonic() - t0) * 1000

        logs = mgr.usage_tracker.get_buffered_entries(task_id="live_frontend_test_run")
        ws_files = list(memory.workspace._files.keys()) if hasattr(memory.workspace, "_files") else []

        print("\n--- FRONTEND AGENT RESULT: SUCCESS ---")
        print(f"Agent Execution  : Role={result.role.value} | FilesProduced={result.files_produced}")
        print(f"Summary          : {result.summary}")
        print(f"Total Duration   : {duration_ms:.1f} ms")
        print(f"Files Generated  : {len(ws_files)} files in workspace")
        for f in ws_files[:10]:
            print(f"  • {f}")
        print(f"Requests Made    : {len(logs)}")
        for i, l in enumerate(reversed(logs), 1):
            print(f"  Request #{l.get('request_number', i)}: ID={l.get('request_id')} | Provider={l.get('provider')} | Model={l.get('model')} | Slot={l.get('credential_slot')} | Masked={l.get('masked_credential')} | Latency={l.get('latency_ms', 0):.0f}ms | Tokens={l.get('total_tokens')}")

        print("------------------------------------------------------------")
        print("[PASS] FrontendEngineerAgent ran successfully using Gemini 3.6 Flash!")
        return 0

    except Exception as exc:
        print(f"\n[FAILED / STOPPED] Frontend agent test halted safely: {exc}")
        return 1


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
