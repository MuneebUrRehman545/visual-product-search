import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import models
from agent.orchestrator import run_agent
from database import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RERUN_GOALS = [
    {
        "id": "eval_6",
        "category": "Mathematical & Calculator",
        "name": "GDP Comparison & Percentage Difference",
        "goal_text": "Find the approximate nominal GDP in trillions USD for Japan and Germany, and calculate the exact percentage difference (GDP_Japan - GDP_Germany) / GDP_Germany * 100 using the calculator tool.",
    },
    {
        "id": "eval_2",
        "category": "Narrow & Straightforward",
        "name": "Tokyo Annual Rainfall (2000-2020)",
        "goal_text": "Find the average annual rainfall in Tokyo between 2000 and 2020, express the result in millimeters, and cite the meteorological source.",
    },
]


def run_single(goal_spec):
    print("\n" + "=" * 80, flush=True)
    print(f"RE-RUNNING FIX VERIFICATION [{goal_spec['id']}]: {goal_spec['name']}", flush=True)
    print(f"Goal: {goal_spec['goal_text']}", flush=True)
    print("=" * 80, flush=True)

    db = SessionLocal()
    start_time = time.time()

    try:
        run = models.Run(goal_text=goal_spec["goal_text"], status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)

        run = run_agent(run.id, db=db) or run
        db.expire_all()
        db.refresh(run)

        duration = round(time.time() - start_time, 2)
        current_plan = next((p for p in run.plans if p.is_current), run.plans[-1]) if run.plans else None

        steps_info = []
        for s in (current_plan.steps if current_plan else []):
            tc_info = [{"tool": tc.tool_name, "args": tc.input_args, "success": tc.success, "output": str(tc.output_data)[:150]} for tc in s.tool_calls]
            steps_info.append({
                "description": s.description,
                "tool": s.intended_tool,
                "status": s.status,
                "tool_calls": tc_info,
                "obs": s.observation.reasoning if s.observation else None,
                "obs_class": s.observation.classification if s.observation else None,
            })

        res = {
            "eval_id": goal_spec["id"],
            "name": goal_spec["name"],
            "run_id": str(run.id),
            "status": run.status,
            "duration": duration,
            "steps_count": len(steps_info),
            "steps": steps_info,
            "report": run.report.content_markdown if run.report else None,
        }

        print("\n" + "-" * 40, flush=True)
        print(f"RE-RUN RESULT FOR [{goal_spec['id']}]: status={res['status']} | steps={res['steps_count']} | duration={duration}s", flush=True)
        for idx, st in enumerate(steps_info, 1):
            print(f"  {idx}. [{st['status']}] {st['description']} (tool: {st['tool']}) -> {st['obs_class']}", flush=True)
        print("-" * 40 + "\n", flush=True)

        return res
    finally:
        db.close()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    results = []
    for g in RERUN_GOALS:
        r = run_single(g)
        results.append(r)
        time.sleep(2)

    with open(backend_dir / "rerun_verification_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\n[OK] Re-run verification completed.")


if __name__ == "__main__":
    main()
