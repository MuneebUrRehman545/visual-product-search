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

EVAL_GOALS = [
    {
        "id": "eval_1",
        "category": "Narrow & Straightforward",
        "name": "Ethereum Current Price & All-Time High",
        "goal_text": "Find the current market price of Ethereum (ETH) and its historical all-time high price in USD, citing at least one financial source.",
    },
    {
        "id": "eval_2",
        "category": "Narrow & Straightforward",
        "name": "Tokyo Annual Rainfall (2000-2020)",
        "goal_text": "Find the average annual rainfall in Tokyo between 2000 and 2020, express the result in millimeters, and cite the meteorological source.",
    },
    {
        "id": "eval_3",
        "category": "Broad Multi-Subtopic",
        "name": "Peloponnesian War vs. Punic Wars Comparison",
        "goal_text": "Provide a comprehensive comparative analysis of the Peloponnesian War and the Punic Wars, examining military tactics, naval innovations, economic costs, and long-term societal fallout.",
    },
    {
        "id": "eval_4",
        "category": "Broad Multi-Subtopic",
        "name": "Li-ion vs. Solid-State Batteries (2024-2025)",
        "goal_text": "Compare the typical energy density (Wh/kg), manufacturing costs, charging speeds, and safety profiles of conventional lithium-ion batteries versus solid-state batteries as of 2024-2025.",
    },
    {
        "id": "eval_5",
        "category": "Mathematical & Calculator",
        "name": "Transatlantic Flight Carbon Footprint & Global %",
        "goal_text": "Calculate the estimated CO2 emissions for a single economy-class round-trip flight from London to New York (approx 11,140 km round-trip distance multiplied by 0.15 kg CO2/passenger-km), and compute what percentage of an average global person's annual 4.7-tonne CO2 footprint this single flight represents using the calculator tool.",
    },
    {
        "id": "eval_6",
        "category": "Mathematical & Calculator",
        "name": "GDP Comparison & Percentage Difference",
        "goal_text": "Find the approximate nominal GDP in trillions USD for Japan and Germany, and calculate the exact percentage difference (GDP_Japan - GDP_Germany) / GDP_Germany * 100 using the calculator tool.",
    },
    {
        "id": "eval_7",
        "category": "Deliberately Vague / Ambiguous",
        "name": "Future Clean Power Technologies",
        "goal_text": "Research future energy technologies and summarize how clean power will work.",
    },
    {
        "id": "eval_8",
        "category": "Deliberately Hard / Tool Failure",
        "name": "Obscure Fictitious Microprocessor Specs & Math",
        "goal_text": "Find the official 1979 technical datasheet, clock speed, and microarchitecture block diagram for the obscure prototype microprocessor 'Zylog-ZX998844-NonExistent-Silicon', and calculate its theoretical MIPS per Watt ratio.",
    },
]


async def evaluate_single_goal(goal_spec: Dict[str, Any]) -> Dict[str, Any]:
    goal_text = goal_spec["goal_text"]
    name = goal_spec["name"]
    category = goal_spec["category"]

    print("\n" + "=" * 80)
    print(f"RUNNING EVALUATION [{goal_spec['id']}]: {name} ({category})")
    print(f"Goal: {goal_text}")
    print("=" * 80)

    start_time = time.time()
    events_captured: List[Dict[str, Any]] = []
    replan_events: List[Dict[str, Any]] = []
    tool_failures: List[Dict[str, Any]] = []

    # 1. POST /runs
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{BASE_URL}/runs", json={"goal_text": goal_text})
        if resp.status_code != 201:
            raise RuntimeError(f"Run creation failed: {resp.status_code} {resp.text}")
        run_data = resp.json()
        run_id = run_data["id"]

    print(f"[*] Run ID: {run_id} | Initial status: {run_data.get('status')}")

    # 2. WebSocket streaming listener
    ws_url = f"{WS_BASE_URL}/runs/{run_id}/stream"
    print(f"[*] Listening on WebSocket: {ws_url} ...")

    async with websockets.connect(ws_url) as ws:
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
                        print(f"        {idx}. {s.get('description')} [{s.get('intended_tool')}]")

                elif event_type == "step_started":
                    print(f"      Step Started: {payload.get('description')}")

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
                    print(f"      Step Completed: status={payload.get('status')}")

                elif event_type == "report_ready":
                    print(f"      Report Ready: Length={len(payload.get('content_markdown', ''))} chars")

                elif event_type in ("run_completed", "run_failed"):
                    print(f"      🏁 Run Finished: status={payload.get('status')} | total_steps={payload.get('total_steps_executed')}")
                    break

            except Exception as e:
                print(f"Error parsing ws message: {e}")
                break

    duration = round(time.time() - start_time, 2)

    # 3. Fetch DB records
    async with httpx.AsyncClient(timeout=60.0) as client:
        run_resp = await client.get(f"{BASE_URL}/runs/{run_id}")
        db_run = run_resp.json()

        steps_resp = await client.get(f"{BASE_URL}/runs/{run_id}/steps")
        db_steps = steps_resp.json()

        db_report = None
        try:
            report_resp = await client.get(f"{BASE_URL}/runs/{run_id}/report")
            if report_resp.status_code == 200:
                db_report = report_resp.json()
        except Exception:
            pass

    limitations_present = False
    limitations_snippet = ""
    if db_report and db_report.get("content_markdown"):
        md = db_report["content_markdown"]
        if any(w in md.lower() for w in ("limitation", "caveat", "gap", "unresolved")):
            limitations_present = True
            for line in md.splitlines():
                if any(w in line.lower() for w in ("limitation", "caveat", "gap", "fail", "unresolved")):
                    limitations_snippet += line + " "

    eval_result = {
        "eval_id": goal_spec["id"],
        "category": category,
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
        "report_markdown": db_report.get("content_markdown") if db_report else None,
        "limitations_present": limitations_present,
        "limitations_snippet": limitations_snippet[:250].strip() if limitations_snippet else "None noted",
    }

    print("\n" + "-" * 40)
    print(f"EVAL [{goal_spec['id']}] FINISHED: {name}")
    print(f"Status: {eval_result['final_status']} | Steps: {eval_result['steps_count']} | Duration: {duration}s")
    print(f"Replans: {eval_result['replan_count']} | Tool Failures: {eval_result['tool_failures_count']}")
    print(f"Report: {eval_result['has_report']} ({eval_result['report_length']} chars) | Limitations: {limitations_present}")
    print("-" * 40 + "\n")

    return eval_result


async def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    results = []
    for g in EVAL_GOALS:
        res = await evaluate_single_goal(g)
        results.append(res)
        await asyncio.sleep(2)

    out_file = Path(__file__).resolve().parent / "phase18_evaluation_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n[✓] All 8 evaluations completed. Results saved to {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
