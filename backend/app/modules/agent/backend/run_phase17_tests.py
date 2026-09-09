import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:8000"
WS_BASE_URL = "ws://127.0.0.1:8000"

TEST_GOALS = [
    {
        "id": "goal_1",
        "name": "Narrow & Specific Goal",
        "goal_text": "Find the current market price of Ethereum (ETH) and its historical all-time high price in USD.",
        "expected_tool_failure": None,
    },
    {
        "id": "goal_2",
        "name": "Broad Multi-Subtopic Goal",
        "goal_text": "Provide a comprehensive comparative analysis of the Peloponnesian War and the Punic Wars, examining military tactics, economic factors, and long-term societal fallout.",
        "expected_tool_failure": None,
    },
    {
        "id": "goal_3",
        "name": "Calculation Step with Real Calculator Tool Failure",
        "goal_text": "Find the approximate 2024 GDP of Japan and Germany in trillions USD, calculate the exact percentage difference (GDP_Japan - GDP_Germany) / 0 first to evaluate the formula, then calculate the valid percentage difference (GDP_Japan - GDP_Germany) / GDP_Germany * 100.",
        "expected_tool_failure": "calculator",
    },
    {
        "id": "goal_4",
        "name": "Vague Goal with Real File Operation Tool Failure",
        "goal_text": "Research future quantum computing encryption threats, and read existing notes from nonexistent file '../unauthorized_secrets.txt' before writing the final security advisory to 'quantum_threats.txt'.",
        "expected_tool_failure": "file_read_write",
    },
    {
        "id": "goal_5",
        "name": "Obscure Fictitious Topic with Real Web Search Failure",
        "goal_text": "Find the technical microarchitecture specifications and 1979 benchmark results for the obscure fictitious prototype microprocessor 'Zylog-ZX998844-NonExistent-Silicon'.",
        "expected_tool_failure": "web_search",
    },
]


async def run_single_test(goal_spec: Dict[str, Any]) -> Dict[str, Any]:
    goal_text = goal_spec["goal_text"]
    name = goal_spec["name"]
    expected_failure = goal_spec.get("expected_tool_failure")

    print("\n" + "=" * 80)
    print(f"STARTING TEST: {name}")
    print(f"Goal: {goal_text}")
    print(f"Expected Tool Failure Target: {expected_failure or 'None (Clean Run)'}")
    print("=" * 80)

    start_time = time.time()
    events_captured: List[Dict[str, Any]] = []

    # 1. Create Run via POST /runs
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/runs", json={"goal_text": goal_text}, timeout=15.0)
        if resp.status_code != 201:
            raise RuntimeError(f"Failed to create run: {resp.status_code} {resp.text}")
        run_data = resp.json()
        run_id = run_data["id"]

    print(f"[*] Run created with ID: {run_id} | Status: {run_data.get('status')}")

    # 2. Connect to WebSocket stream
    ws_url = f"{WS_BASE_URL}/runs/{run_id}/stream"
    print(f"[*] Connecting to WebSocket: {ws_url} ...")

    replan_events = []
    tool_failures = []
    terminal_event = None

    async with websockets.connect(ws_url) as ws:
        print(f"[*] WebSocket connected. Streaming events...")
        async for message_text in ws:
            try:
                msg = json.loads(message_text)
                event_type = msg.get("type") or msg.get("event")
                payload = msg.get("payload", {})
                timestamp = msg.get("timestamp", datetime.now(timezone.utc).isoformat())

                events_captured.append(msg)
                print(f"  [{timestamp[-12:]}] EVENT: {str(event_type).upper()}")

                if event_type == "plan_created":
                    print(f"      Total Steps: {payload.get('total_steps')}")
                    for idx, s in enumerate(payload.get("steps", []), 1):
                        print(f"        {idx}. {s.get('description')} [Tool: {s.get('intended_tool')}]")

                elif event_type == "step_started":
                    print(f"      Step: {payload.get('description')}")

                elif event_type == "tool_call_started":
                    print(f"      Tool Invoked: {payload.get('tool_name')} | Args: {payload.get('input_args')}")

                elif event_type == "tool_call_result":
                    success = payload.get("success")
                    err = payload.get("error_message")
                    print(f"      Tool Result: success={success} | err={err}")
                    if not success:
                        tool_failures.append({
                            "tool_name": payload.get("tool_name"),
                            "error": err,
                            "args": payload.get("input_args"),
                        })

                elif event_type == "observation_made":
                    print(f"      Observation: [{payload.get('classification')}] -> {payload.get('recommendation')}")
                    print(f"      Reasoning: {payload.get('reasoning')}")

                elif event_type == "replan_triggered":
                    print(f"      ⚠️ REPLAN TRIGGERED: action={payload.get('action')} (retry #{payload.get('retry_count')})")
                    print(f"      Reason: {payload.get('reasoning')}")
                    replan_events.append(payload)

                elif event_type == "step_completed":
                    print(f"      Step Completed: status={payload.get('status')} | ref={payload.get('result_ref')}")

                elif event_type == "report_ready":
                    print(f"      Report Ready: ID={payload.get('report_id')} | Length={len(payload.get('content_markdown', ''))}")

                elif event_type in ("run_completed", "run_failed"):
                    terminal_event = msg
                    print(f"      🏁 TERMINAL EVENT: {event_type} | Status: {payload.get('status')}")
                    break

            except Exception as e:
                print(f"Error parsing ws message: {e}")
                break

    duration = round(time.time() - start_time, 2)
    print(f"[*] Stream finished in {duration}s")

    # 3. Verify Database consistency via REST endpoints
    async with httpx.AsyncClient() as client:
        # Check run details
        run_resp = await client.get(f"{BASE_URL}/runs/{run_id}", timeout=10.0)
        db_run = run_resp.json()

        # Check steps
        steps_resp = await client.get(f"{BASE_URL}/runs/{run_id}/steps", timeout=10.0)
        db_steps = steps_resp.json()

        # Check report
        db_report = None
        try:
            report_resp = await client.get(f"{BASE_URL}/runs/{run_id}/report", timeout=10.0)
            if report_resp.status_code == 200:
                db_report = report_resp.json()
        except Exception:
            pass

    # Check limitations in report
    limitations_found = False
    limitations_text = ""
    if db_report and db_report.get("content_markdown"):
        md = db_report["content_markdown"]
        if "limitation" in md.lower() or "caveat" in md.lower() or "unresolved" in md.lower():
            limitations_found = True
            for line in md.split("\n"):
                if any(w in line.lower() for w in ("limitation", "caveat", "gap", "fail", "unresolved")):
                    limitations_text += line + " "

    result_summary = {
        "goal_id": goal_spec["id"],
        "name": name,
        "goal_text": goal_text,
        "run_id": run_id,
        "final_status": db_run.get("status"),
        "duration_seconds": duration,
        "steps_count": len(db_steps),
        "total_events_captured": len(events_captured),
        "replan_count": len(replan_events),
        "replan_details": replan_events,
        "tool_failures_count": len(tool_failures),
        "tool_failures": tool_failures,
        "has_report": db_report is not None,
        "report_length": len(db_report.get("content_markdown", "")) if db_report else 0,
        "limitations_present": limitations_found,
        "limitations_summary": limitations_text[:200] if limitations_text else "None noted",
        "db_consistency_verified": db_run.get("status") in ("complete", "failed"),
    }

    print("\n--- TEST SUMMARY ---")
    print(f"Run ID: {run_id}")
    print(f"Status: {result_summary['final_status']}")
    print(f"Duration: {duration}s")
    print(f"Steps: {result_summary['steps_count']}")
    print(f"Replans: {result_summary['replan_count']}")
    print(f"Tool Failures: {result_summary['tool_failures_count']}")
    print(f"Report Generated: {result_summary['has_report']} (Length: {result_summary['report_length']})")
    print(f"Limitations Detected: {limitations_found}")
    print("--------------------\n")

    return result_summary


async def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    all_results = []
    for goal_spec in TEST_GOALS:
        res = await run_single_test(goal_spec)
        all_results.append(res)
        await asyncio.sleep(2)

    print("\n" + "=" * 80)
    print("ALL 5 INTEGRATION TESTS FINISHED")
    print("=" * 80)
    print(json.dumps(all_results, indent=2))

    # Save raw results to JSON file for logging & analysis
    out_path = Path(__file__).resolve().parent / "phase17_test_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"Saved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
