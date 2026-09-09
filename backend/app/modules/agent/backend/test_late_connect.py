import asyncio
import sys
import time
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
from test_streaming_manual import stream_live_run


async def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    base_url = "http://127.0.0.1:8000"
    goal = "Investigate CRISPR Cas9 gene editing breakthroughs in 2024 and 2025"

    print("=" * 70)
    print("STEP 1: Creating new run via HTTP POST /runs (Independent client)")
    print("=" * 70)
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{base_url}/runs", json={"goal_text": goal}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        run_id = data["id"]
        print(f"Created Run ID: {run_id} at {time.strftime('%H:%M:%S')}")
        print(f"Initial Status: {data.get('status')}")

    delay = 18
    print("\n" + "=" * 70)
    print(f"STEP 2: Allowing agent to execute in background for {delay} seconds before connecting...")
    print("=" * 70)
    for remaining in range(delay, 0, -3):
        print(f"  ... agent executing in background ({remaining}s remaining before connecting)")
        await asyncio.sleep(3)

    print("\n" + "=" * 70)
    print(f"STEP 3: Connecting WebSocket to /runs/{run_id}/stream partway through execution")
    print("=" * 70)
    await stream_live_run(base_url=base_url, goal=goal, run_id=run_id)


if __name__ == "__main__":
    asyncio.run(main())
