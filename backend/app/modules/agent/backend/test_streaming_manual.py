"""Manual test script to demonstrate live WebSocket event streaming.
Can run against a live running server (http://127.0.0.1:8000) or standalone in-process.
"""

import asyncio
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
import websockets


async def stream_live_run(base_url: str = "http://127.0.0.1:8000", goal: str = "Research the invention of penicillin and its impact on medicine", run_id: str = None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ws_base = base_url.replace("http://", "ws://").replace("https://", "wss://")
    
    print("=" * 70)
    print("MANUAL TEST: Live WebSocket Agent Event Stream (Live Backend)")
    print(f"Backend URL: {base_url}")
    print(f"Goal: {goal}")
    print("=" * 70)

    # 1. Create a run via HTTP POST /runs if run_id not provided
    if not run_id:
        print(f"\n[HTTP POST] Creating new run at {base_url}/runs ...")
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base_url}/runs", json={"goal_text": goal}, timeout=10.0)
            if resp.status_code != 201:
                print(f"Error creating run: {resp.status_code} {resp.text}")
                return
            data = resp.json()
            run_id = data["id"]
            print(f"[Created Run via POST] ID: {run_id} | Initial Status: {data.get('status')}\n")

    # 2. Connect to WebSocket stream endpoint
    ws_url = f"{ws_base}/runs/{run_id}/stream"
    print(f"Connecting to WebSocket: {ws_url} ...")
    
    async with websockets.connect(ws_url) as ws:
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Connected to {ws_url}")
        print("-" * 70)

        async for message_text in ws:
            try:
                data = json.loads(message_text)
                event_type = data.get("type") or data.get("event")
                timestamp = data.get("timestamp", datetime.now().isoformat())
                payload = data.get("payload", {})

                print(f"[{timestamp}] EVENT: {str(event_type).upper()}")
                if event_type == "plan_created":
                    print(f"    Total Steps: {payload.get('total_steps')}")
                    for idx, s in enumerate(payload.get("steps", []), start=1):
                        print(f"    {idx}. {s.get('description')} [Tool: {s.get('intended_tool')}]")
                elif event_type == "step_started":
                    print(f"    Step: {payload.get('description')} [Tool: {payload.get('intended_tool')}]")
                elif event_type == "tool_call_started":
                    print(f"    Tool: {payload.get('tool_name')} | Args: {payload.get('input_args')}")
                elif event_type == "tool_call_result":
                    out = payload.get("output_data")
                    preview = str(out)[:200] if out else "None"
                    print(f"    Success: {payload.get('success')} | Error: {payload.get('error_message')}")
                    print(f"    Data Preview: {preview}")
                elif event_type == "observation_made":
                    print(f"    Classification: {payload.get('classification')} | Recommendation: {payload.get('recommendation')}")
                    print(f"    Reasoning: {payload.get('reasoning')}")
                elif event_type == "replan_triggered":
                    print(f"    Action: {payload.get('action')} (Retry Count: {payload.get('retry_count')})")
                    print(f"    Reason: {payload.get('reasoning')}")
                elif event_type == "step_completed":
                    print(f"    Status: {payload.get('status')}")
                    if payload.get("result_ref"):
                        print(f"    Result Ref: {payload.get('result_ref')}")
                elif event_type == "report_ready":
                    print(f"    Report ID: {payload.get('report_id')} | Length: {len(payload.get('content_markdown', ''))} characters")
                elif event_type in ("run_completed", "run_failed"):
                    print(f"    Final Status: {payload.get('status')} | Total Steps Executed: {payload.get('total_steps_executed')}")
                    print(f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Stream closed by server.")
                    break
                elif event_type == "catch_up":
                    print(f"    Catch-Up Run ID: {payload.get('run', {}).get('id')} | Status: {payload.get('run', {}).get('status')}")
                    steps_list = payload.get("steps", [])
                    print(f"    Current Steps in State: {len(steps_list)}")
                    for idx, s in enumerate(steps_list, start=1):
                        status_str = s.get('status', 'unknown').upper()
                        obs = s.get('observation')
                        obs_str = f" [Observation: {obs.get('classification')}]" if obs else ""
                        print(f"      {idx}. [{status_str}] {s.get('description')} (Tool calls: {len(s.get('tool_calls', []))}){obs_str}")
                else:
                    print(f"    Payload: {json.dumps(payload, indent=2)[:200]}")
                print()
            except Exception as e:
                print(f"Error parsing message: {e}")
                break

    print("=" * 70)
    print("STREAMING COMPLETE")
    print("=" * 70)


def main():
    goal = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "Research the discovery of penicillin and its impact on medicine"
    run_id = None
    if len(sys.argv) > 2 and not sys.argv[2].startswith("-"):
        run_id = sys.argv[2]
    
    asyncio.run(stream_live_run(goal=goal, run_id=run_id))


if __name__ == "__main__":
    main()
