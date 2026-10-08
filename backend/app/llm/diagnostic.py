"""Diagnostic utility to safely probe the Gemini Account x Model matrix.

Executes exactly ONE minimal request per cell ("Reply with exactly: OK"),
bypassing generation pipelines, measuring latency, classifying errors,
and displaying the matrix without exposing any secrets or API keys.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.llm.agent_model_registry import DEFAULT_GEMINI_FALLBACK_CHAIN
from app.llm.gemini import classify_provider_error

SLOTS: tuple[str, ...] = (
    "PLANNER_API_KEY01",
    "FRONTEND_API_KEY01",
    "BACKEND_API_KEY01",
    "DATABASE_API_KEY01",
    "QA_API_KEY01",
    "REVIEW_API_KEY01",
    "DEBUG_API_KEY01",
)


def _get_api_key_for_slot(slot: str, config: Settings) -> str | None:
    key = getattr(config, slot.lower(), None)
    return key.strip() if key and key.strip() else None


async def probe_cell(
    *,
    slot: str,
    model_id: str,
    api_key: str | None,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """Send exactly one minimal request to a specific (account, model) cell."""
    if not api_key:
        return {
            "account": slot,
            "model": model_id,
            "status": "N/A",
            "latency": "0.00s",
            "error_type": "MISSING_KEY",
            "success": False,
            "detail": "API key not configured in environment",
        }

    http_opts = genai_types.HttpOptions(timeout=int(timeout_seconds * 1000))
    client = genai.Client(api_key=api_key, http_options=http_opts)
    prompt = "Reply with exactly: OK"

    start = time.perf_counter()
    try:
        response = await client.aio.models.generate_content(
            model=model_id,
            contents=prompt,
        )
        elapsed = time.perf_counter() - start
        preview = (response.text or "").strip()[:50]
        return {
            "account": slot,
            "model": model_id,
            "status": "200 OK",
            "latency": f"{elapsed:.2f}s",
            "error_type": "None",
            "success": True,
            "detail": preview or "OK",
        }
    except genai_errors.APIError as exc:
        elapsed = time.perf_counter() - start
        code = getattr(exc, "code", "Error")
        classified = classify_provider_error(exc)
        msg = getattr(exc, "message", str(exc))
        clean_msg = msg[:80].replace("\n", " ")
        return {
            "account": slot,
            "model": model_id,
            "status": str(code),
            "latency": f"{elapsed:.2f}s",
            "error_type": classified,
            "success": False,
            "detail": clean_msg,
        }
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return {
            "account": slot,
            "model": model_id,
            "status": "Error",
            "latency": f"{elapsed:.2f}s",
            "error_type": type(exc).__name__,
            "success": False,
            "detail": str(exc)[:80].replace("\n", " "),
        }


async def run_diagnostic_matrix(
    *,
    slots: tuple[str, ...] | list[str] | None = None,
    models: tuple[str, ...] | list[str] | None = None,
    config: Settings | None = None,
) -> list[dict[str, Any]]:
    """Execute matrix probe sequentially with 0.5s pause to prevent self-imposed spikes."""
    cfg = config or default_settings
    active_slots = list(slots or SLOTS)
    active_models = list(models or DEFAULT_GEMINI_FALLBACK_CHAIN)

    results: list[dict[str, Any]] = []

    for slot in active_slots:
        api_key = _get_api_key_for_slot(slot, cfg)
        for model_id in active_models:
            res = await probe_cell(slot=slot, model_id=model_id, api_key=api_key)
            results.append(res)
            await asyncio.sleep(0.5)

    return results


def format_diagnostic_table(results: list[dict[str, Any]]) -> str:
    """Format diagnostic probe results as an ASCII table."""
    headers = ("Account", "Model", "Status", "Latency", "Error Type")
    col_w = {
        "Account": max(len("Account"), *(len(r["account"]) for r in results)),
        "Model": max(len("Model"), *(len(r["model"]) for r in results)),
        "Status": max(len("Status"), *(len(str(r["status"])) for r in results)),
        "Latency": max(len("Latency"), *(len(str(r["latency"])) for r in results)),
        "Error Type": max(len("Error Type"), *(len(str(r["error_type"])) for r in results)),
    }

    sep = "+-" + "-+-".join("-" * col_w[h] for h in headers) + "-+"
    head_line = (
        "| "
        + " | ".join(h.ljust(col_w[h]) for h in headers)
        + " |"
    )

    lines = [sep, head_line, sep]
    for r in results:
        row = (
            "| "
            + f"{r['account'].ljust(col_w['Account'])} | "
            + f"{r['model'].ljust(col_w['Model'])} | "
            + f"{str(r['status']).ljust(col_w['Status'])} | "
            + f"{str(r['latency']).ljust(col_w['Latency'])} | "
            + f"{str(r['error_type']).ljust(col_w['Error Type'])} |"
        )
        lines.append(row)
    lines.append(sep)
    return "\n".join(lines)


if __name__ == "__main__":
    async def _cli() -> None:
        print("\nStarting live probe of Gemini Account x Model matrix...")
        res = await run_diagnostic_matrix()
        print("\n" + format_diagnostic_table(res) + "\n")

    asyncio.run(_cli())
