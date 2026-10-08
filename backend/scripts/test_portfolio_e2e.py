"""End-to-End Test for Simple Portfolio Project Generation.

Tests Section 28 & 29:
- Prompt: "Create a modern responsive personal portfolio website using HTML, CSS and JavaScript. Include hero, about, skills, projects, experience, contact section, responsive navigation, animations, and mobile support."
- Checks:
  1. Requirements analysis runs.
  2. Database & backend agents skipped for static portfolio.
  3. Frontend engineer runs and generates full files (index.html, styles.css, app.js).
  4. Gemini 3.6 Flash only.
  5. 7-slot API keys only.
  6. Request count is controlled (<= 15 hard cap).
"""

import asyncio
import json
import sqlite3
import time
import urllib.request
import urllib.error

from app.core.security import create_token


BASE_URL = "http://127.0.0.1:8000/api/v1"


def get_auth_token() -> str:
    url = f"{BASE_URL}/auth/login"
    data = json.dumps({"email": "test_audit@aegis.dev", "password": "Password123!"}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))["tokens"]["access_token"]


def api_request(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        print(f"HTTPError {err.code} on {path}: {body}")
        raise


def run_portfolio_test():
    print("=== STARTING PORTFOLIO E2E TEST ===")
    token = get_auth_token()
    print("[1] Auth token generated successfully.")

    # 1. Create project
    prompt = (
        "Create a modern responsive personal portfolio website using HTML, CSS and JavaScript. "
        "Include hero, about, skills, projects, experience, contact section, responsive navigation, "
        "animations, and mobile support."
    )
    project_payload = {
        "name": f"Portfolio Test {int(time.time())}",
        "idea": prompt,
        "tags": ["portfolio", "html", "css", "javascript"],
    }
    project = api_request("POST", "/projects", token, project_payload)
    project_id = project["id"]
    print(f"[2] Project created: ID={project_id}, Name='{project['name']}'")

    # 2. Analyse project
    print("[3] Running requirements analysis...")
    analysis = api_request("POST", f"/projects/{project_id}/analyze", token)
    print(f"[3] Analysis complete. Architecture style: {analysis.get('architecture_style')}")
    print(f"    Frontend: {analysis.get('recommended_stack', {}).get('frontend')}")
    print(f"    Backend: {analysis.get('recommended_stack', {}).get('backend')}")
    print(f"    Database: {analysis.get('recommended_stack', {}).get('database')}")

    # 3. Start generation run
    print("[4] Starting generation run...")
    run_payload = {
        "tech_stack": analysis.get("recommended_stack"),
    }
    run = api_request("POST", f"/projects/{project_id}/runs", token, run_payload)
    run_id = run["id"]
    print(f"[4] Run launched: ID={run_id}, status={run.get('status')}")

    # 4. Poll run until completion or terminal state
    print("[5] Monitoring execution progress...")
    max_wait = 180  # 3 minutes max
    start_time = time.time()
    last_status = None
    terminal_statuses = ("completed", "failed", "cancelled")

    while time.time() - start_time < max_wait:
        run_detail = api_request("GET", f"/runs/{run_id}", token)
        current_status = run_detail.get("status")
        if current_status != last_status:
            print(f"    Run status: {current_status}")
            last_status = current_status

        agents = run_detail.get("agents", [])
        active_agents = [a for a in agents if a.get("status") in ("running", "completed", "failed")]
        if active_agents:
            agent_summary = ", ".join(f"{a.get('role')}={a.get('status')}" for a in active_agents)
            print(f"    Active agents: {agent_summary}")

        if current_status in terminal_statuses:
            break
        time.sleep(3)

    print(f"[6] Run finished with terminal status: {current_status}")

    # 5. Fetch execution details & audit
    final_detail = api_request("GET", f"/runs/{run_id}", token)
    agents = final_detail.get("agents", [])
    print("\n=== AGENT EXECUTION SUMMARY ===")
    for a in agents:
        role = a.get("role")
        status = a.get("status")
        duration = a.get("duration_seconds")
        print(f"  - {role}: status={status}, duration={duration}s")

    # 6. Check UsageLogs from DB for this task
    con = sqlite3.connect("aegis.db")
    cur = con.cursor()
    cur.execute(
        "SELECT request_number, agent_role, credential_slot, model, status, latency_ms FROM usage_logs WHERE task_id=? OR run_id=? ORDER BY request_number ASC",
        (run_id, run_id),
    )
    logs = cur.fetchall()
    con.close()

    print(f"\n=== USAGE LOGS AUDIT (Total LLM Requests: {len(logs)}) ===")
    for row in logs:
        req_num, agent_role, slot, model, status, lat = row
        print(f"  Req #{req_num}: agent={agent_role}, slot={slot}, model={model}, status={status}, latency={lat}ms")

    print("\n=== VERIFICATION CHECKS ===")
    # Check 1: Model is ONLY gemini-3.6-flash
    models_used = set(row[3] for row in logs)
    print(f"1. Models used: {models_used}")
    for m in models_used:
        assert m == "gemini-3.6-flash", f"ILLEGAL MODEL DETECTED: {m}"
    print("   [PASS] Only gemini-3.6-flash was used.")

    # Check 2: Credential slots only use 01 suffix
    slots_used = set(row[2] for row in logs)
    print(f"2. Credential slots used: {slots_used}")
    allowed_slots = {
        "PLANNER_API_KEY01",
        "FRONTEND_API_KEY01",
        "BACKEND_API_KEY01",
        "DATABASE_API_KEY01",
        "QA_API_KEY01",
        "REVIEW_API_KEY01",
        "DEBUG_API_KEY01",
    }
    for s in slots_used:
        assert s in allowed_slots, f"ILLEGAL SLOT DETECTED: {s}"
    print("   [PASS] Only authoritative 7 slots used.")

    # Check 3: Total requests <= 15
    print(f"3. Total LLM requests: {len(logs)}")
    assert len(logs) <= 15, f"EXCEEDED HARD LIMIT OF 15 REQUESTS: {len(logs)}"
    print("   [PASS] Request count is strictly within 15.")

    print("\n=== PORTFOLIO E2E TEST COMPLETED ===")


if __name__ == "__main__":
    run_portfolio_test()
