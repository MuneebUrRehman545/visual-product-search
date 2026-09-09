import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import models
from agent.orchestrator import run_agent
from database import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_suite")

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


def evaluate_single_goal(goal_spec: Dict[str, Any]) -> Dict[str, Any]:
    goal_text = goal_spec["goal_text"]
    name = goal_spec["name"]
    category = goal_spec["category"]

    print("\n" + "=" * 80, flush=True)
    print(f"RUNNING EVALUATION [{goal_spec['id']}]: {name} ({category})", flush=True)
    print(f"Goal: {goal_text}", flush=True)
    print("=" * 80, flush=True)

    db = SessionLocal()
    start_time = time.time()

    try:
        run = models.Run(goal_text=goal_text, status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)

        print(f"[*] Created run {run.id} | Initial status: {run.status}", flush=True)

        run = run_agent(run.id, db=db) or run
        db.expire_all()
        db.refresh(run)

        duration = round(time.time() - start_time, 2)

        # Collect steps
        current_plan = None
        if run.plans:
            current_plan = next((p for p in run.plans if p.is_current), run.plans[-1])

        steps_data = []
        replans = []
        tool_failures = []
        if current_plan and current_plan.steps:
            for s in current_plan.steps:
                tool_calls_info = []
                for tc in s.tool_calls:
                    tool_calls_info.append({
                        "tool_name": tc.tool_name,
                        "input_args": tc.input_args,
                        "success": tc.success,
                        "error_message": tc.error_message,
                        "output_preview": str(tc.output_data)[:200] if tc.output_data else None,
                    })
                    if not tc.success:
                        tool_failures.append({
                            "step": s.description,
                            "tool": tc.tool_name,
                            "error": tc.error_message,
                        })

                obs_info = None
                if s.observation:
                    obs_info = {
                        "classification": s.observation.classification,
                        "recommendation": s.observation.recommendation,
                        "reasoning": s.observation.reasoning,
                    }
                    if s.observation.classification in ("insufficient", "transient_failure", "hard_failure"):
                        replans.append({
                            "step": s.description,
                            "classification": s.observation.classification,
                            "recommendation": s.observation.recommendation,
                            "reasoning": s.observation.reasoning,
                        })

                steps_data.append({
                    "id": str(s.id),
                    "description": s.description,
                    "intended_tool": s.intended_tool,
                    "status": s.status,
                    "tool_calls": tool_calls_info,
                    "observation": obs_info,
                })

        report_markdown = run.report.content_markdown if run.report else None
        limitations_present = False
        limitations_snippet = ""
        if report_markdown:
            for line in report_markdown.splitlines():
                if any(w in line.lower() for w in ("limitation", "gap", "caveat", "skipped", "fail", "not found", "unresolved")):
                    limitations_present = True
                    limitations_snippet += line + " "

        eval_result = {
            "eval_id": goal_spec["id"],
            "category": category,
            "name": name,
            "goal_text": goal_text,
            "run_id": str(run.id),
            "final_status": run.status,
            "duration_seconds": duration,
            "steps_count": len(steps_data),
            "steps": steps_data,
            "replans_count": len(replans),
            "replans": replans,
            "tool_failures_count": len(tool_failures),
            "tool_failures": tool_failures,
            "has_report": run.report is not None,
            "report_length": len(report_markdown) if report_markdown else 0,
            "report_markdown": report_markdown,
            "limitations_present": limitations_present,
            "limitations_snippet": limitations_snippet[:300].strip() if limitations_snippet else "None",
        }

        print("\n" + "-" * 40, flush=True)
        print(f"EVAL [{goal_spec['id']}] FINISHED: {name}", flush=True)
        print(f"Status: {eval_result['final_status']} | Steps: {eval_result['steps_count']} | Duration: {duration}s", flush=True)
        print(f"Replans: {eval_result['replans_count']} | Tool Failures: {eval_result['tool_failures_count']}", flush=True)
        print(f"Report Generated: {eval_result['has_report']} ({eval_result['report_length']} chars) | Limitations Noted: {limitations_present}", flush=True)
        print("-" * 40 + "\n", flush=True)

        return eval_result

    finally:
        db.close()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    results = []
    for g in EVAL_GOALS:
        try:
            res = evaluate_single_goal(g)
            results.append(res)
        except Exception as e:
            logger.error(f"Failed evaluation for {g['id']}: {e}", exc_info=True)
            results.append({
                "eval_id": g["id"],
                "category": g["category"],
                "name": g["name"],
                "goal_text": g["goal_text"],
                "final_status": "error",
                "error": str(e),
            })
        time.sleep(1)

    out_file = Path(__file__).resolve().parent / "phase18_evaluation_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n[OK] All 8 evaluations completed. Saved to {out_file}", flush=True)


if __name__ == "__main__":
    main()
