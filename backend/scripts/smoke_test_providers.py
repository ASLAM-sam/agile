"""Live smoke test script for all 5 role-based LLM provider credentials."""

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

from app.core.enums import AgentRole
from app.llm.manager import RoleBasedProviderManager
from app.llm.types import PromptBundle

mgr = RoleBasedProviderManager()

tests = [
    ("Planner", AgentRole.MANAGER, "gemini-3.6-flash", "PLANNER_API_KEY01", "PLANNER_API_KEY01"),
    ("Frontend", AgentRole.FRONTEND_ENGINEER, "gemini-3.6-flash", "FRONTEND_API_KEY01", "FRONTEND_API_KEY01"),
    ("Backend", AgentRole.BACKEND_ENGINEER, "gemini-3.6-flash", "BACKEND_API_KEY01", "BACKEND_API_KEY01"),
    ("Database", AgentRole.DATABASE_ENGINEER, "gemini-3.6-flash", "DATABASE_API_KEY01", "DATABASE_API_KEY01"),
    ("QA", AgentRole.QA_ENGINEER, "gemini-3.6-flash", "QA_API_KEY01", "QA_API_KEY01"),
    ("Debug", AgentRole.FINAL_QA, "gemini-3.6-flash", "DEBUG_API_KEY01", "DEBUG_API_KEY01"),
    ("Review", AgentRole.REVIEW_ENGINEER, "gemini-3.6-flash", "REVIEW_API_KEY01", "REVIEW_API_KEY01"),
    ("Improvement", AgentRole.IMPROVEMENT_ENGINEER, "gemini-3.6-flash", "REVIEW_API_KEY01", "REVIEW_API_KEY01"),
]

results = []

async def run_smoke():
    print("================ LIVE PROVIDER SMOKE TEST ================")
    for label, role, exp_model, key_var, slot in tests:
        print(f"\n--- Testing {label} (Slot: '{slot}', Role: '{role.value}') ---")
        prompt = PromptBundle(
            cacheable_system="You are an AI engineering assistant.",
            user_message="Return a JSON object with key status and value ok.",
            schema={
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"],
                "additionalProperties": False,
            },
            metadata={"agent": role.value},
        )
        t0 = time.time()
        provider = mgr._providers.get(slot)
        if not provider:
            print(f"Result: FAIL - Slot '{slot}' is not configured.")
            results.append({
                "provider": label,
                "slot": slot,
                "role": role.value,
                "status": "FAIL",
                "model_served": "None",
                "error": "Slot not configured",
                "duration": 0.0,
            })
            continue

        # Snapshot call counts on all slots to detect any unexpected leakage
        initial_counts = {s: stat.requests for s, stat in mgr._slot_stats.items()}

        try:
            res = await mgr.complete_structured(prompt)
            duration = round(time.time() - t0, 2)
            print(f"Result: PASS ({duration}s)")
            print(f"Model Served: {res.model}")
            print(f"Response: {res.data}")

            # Verify no cross-account fallback
            leakage = False
            for other_slot, count in mgr._slot_stats.items():
                if other_slot != slot and count != initial_counts.get(other_slot, 0):
                    print(f"CRITICAL: Cross-account leakage on slot '{other_slot}'!")
                    leakage = True

            results.append({
                "provider": label,
                "slot": slot,
                "role": role.value,
                "status": "PASS" if not leakage else "FAIL (LEAKAGE)",
                "model_served": res.model,
                "error": None,
                "duration": duration,
                "leakage": leakage,
            })
        except Exception as e:
            duration = round(time.time() - t0, 2)
            print(f"Result: FAIL ({duration}s)")
            print(f"Error: {type(e).__name__}: {e}")
            results.append({
                "provider": label,
                "slot": slot,
                "role": role.value,
                "status": "FAIL",
                "model_served": "None",
                "error": f"{type(e).__name__}: {e}",
                "duration": duration,
                "leakage": False,
            })

    print("\n================ SUMMARY ================")
    for r in results:
        status_str = f"[{r['status']}]".ljust(8)
        print(f"{status_str} {r['provider'].ljust(20)} | Slot: {r['slot'].ljust(18)} | Model: {r['model_served']} ({r['duration']}s)")

if __name__ == "__main__":
    asyncio.run(run_smoke())
