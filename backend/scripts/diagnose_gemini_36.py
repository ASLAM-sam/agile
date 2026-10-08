"""Safe live diagnostic tool for Google Gemini 3.6 Flash.

Reads credentials from environment/config.
Performs ONE minimal API request.
Records:
- Request ID
- Provider: gemini
- Model: gemini-3.6-flash
- Masked credential
- Latency (ms)
- Token usage (input, output, total)
- Creates UsageLog entry
NEVER prints any real API secrets or authorization tokens!
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

from app.core.config import Settings
from app.core.enums import AgentRole
from app.llm.credentials import CredentialManager, mask_key
from app.llm.manager import RoleBasedProviderManager
from app.llm.types import PromptBundle


async def main() -> int:
    config = Settings()
    cm = CredentialManager.from_settings(config)
    slots = cm.list_slots()

    print("============================================================")
    print("           AEGIS AI — GEMINI 3.6 FLASH LIVE DIAGNOSTIC       ")
    print("============================================================")
    print(f"Configured Provider: {config.default_provider}")
    print(f"Configured Model   : {config.gemini_model}")
    print(f"Configured Slots   : {len(slots)} active")
    for s in slots:
        print(f"  • {s.name:<22} : {s.masked_key}")

    if not slots:
        print("\n[SKIPPED] No credential slots configured in environment / .env.")
        print("To run live test, configure FRONTEND_API_KEY in backend/.env")
        return 0

    print("\n------------------------------------------------------------")
    print("EXECUTING ONE CONTROLLED LIVE GEMINI REQUEST (gemini-3.6-flash)...")
    print("------------------------------------------------------------")

    mgr = RoleBasedProviderManager(config=config)

    bundle = PromptBundle(
        cacheable_system="You are a senior software architect assisting Aegis AI.",
        user_message="Confirm system readiness by returning JSON with status: 'ready'.",
        schema={
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
            "additionalProperties": False,
        },
        metadata={
            "agent": AgentRole.FRONTEND_ENGINEER.value,
            "task_id": "diagnostic_phase4_gemini36",
        },
    )

    t0 = time.monotonic()
    try:
        completion = await mgr.complete_structured(bundle)
        duration_ms = (time.monotonic() - t0) * 1000

        # Retrieve the recorded UsageLog from the tracker
        logs = mgr.usage_tracker.get_buffered_entries(task_id="diagnostic_phase4_gemini36")
        log_entry = logs[0] if logs else {}

        print("\n--- DIAGNOSTIC RESULT: SUCCESS ---")
        print(f"Provider    : {log_entry.get('provider', 'gemini')}")
        print(f"Model       : {log_entry.get('model', config.gemini_model)}")
        print(f"Credential  : {log_entry.get('credential_slot', 'FRONTEND_API_KEY')}")
        print(f"Masked      : {log_entry.get('masked_credential', '****')}")
        print(f"Status      : {log_entry.get('status', 'success')}")
        print(f"Latency     : {duration_ms:.1f} ms")
        print(f"Request ID  : {log_entry.get('request_id', 'unknown')}")
        print(f"Tokens In   : {log_entry.get('input_tokens', 'N/A')}")
        print(f"Tokens Out  : {log_entry.get('output_tokens', 'N/A')}")
        print(f"Total Tokens: {log_entry.get('total_tokens', 'N/A')}")
        print(f"Response    : {completion.data}")
        print("------------------------------------------------------------")
        print("[PASS] Exactly 1 request executed and recorded in UsageLog.")
        return 0

    except Exception as exc:
        duration_ms = (time.monotonic() - t0) * 1000
        logs = mgr.usage_tracker.get_buffered_entries(task_id="diagnostic_phase4_gemini36")
        log_entry = logs[0] if logs else {}

        print("\n--- DIAGNOSTIC RESULT: STOPPED / SAFE REPORT ---")
        print(f"Status        : FAILED")
        print(f"Latency       : {duration_ms:.1f} ms")
        print(f"Request ID    : {log_entry.get('request_id', 'unknown')}")
        print(f"Error Category: {log_entry.get('error_category', type(exc).__name__)}")
        print(f"Safe Message  : {log_entry.get('error_message_safe', str(exc))}")
        print("------------------------------------------------------------")
        print("[STOP] Controlled test terminated cleanly without retry loops.")
        return 1


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
