import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import models
from agent.llm_client import LLMClient
from agent.orchestrator import run_agent
from database import SessionLocal


class DeliberateFailureLLMClient(LLMClient):
    """LLM client that injects an intentionally malformed calculator expression
    for calculation steps to demonstrate the hard failure & self-correction pipeline."""

    def decide_tool_call(
        self,
        step_description: str,
        tools_list: list,
        system_prompt: str = None,
        context_summary: str = None,
        reformulation_hint: str = None,
    ):
        desc_lower = step_description.lower()
        if "calculate" in desc_lower or "formula" in desc_lower or "math" in desc_lower:
            # Inject deliberately malformed mathematical expression (division by zero)
            return "calculator", {"expression": "100 / (5 - 5)"}

        return super().decide_tool_call(
            step_description=step_description,
            tools_list=tools_list,
            system_prompt=system_prompt,
            context_summary=context_summary,
            reformulation_hint=reformulation_hint,
        )


def run_deliberate_failure_demo():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 70)
    print("DEMO: Deliberate Malformed Calculator Failure & Self-Correction Pipeline")
    print("=" * 70)

    if SessionLocal is None:
        print("Error: DATABASE_URL is not configured in environment.")
        sys.exit(1)

    db = SessionLocal()
    try:
        # 1. Create a Run
        goal = "Research AI compute growth, calculate efficiency metric, and synthesize final report"
        run = models.Run(goal_text=goal, status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)

        print(f"\n[1] Created Run: {run.id}")
        print(f"    Objective: {run.goal_text}")

        # 2. Create Plan with a calculation step
        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)

        step1 = models.Step(
            plan_id=plan.id,
            description="Search recent trends in AI compute power and datacenter energy usage",
            intended_tool="web_search",
            status="pending",
        )
        step2 = models.Step(
            plan_id=plan.id,
            description="Calculate energy efficiency index using raw expression: 100 / (5 - 5)",
            intended_tool="calculator",
            status="pending",
        )
        step3 = models.Step(
            plan_id=plan.id,
            description="Search future projections and efficiency solutions for AI datacenters",
            intended_tool="web_search",
            status="pending",
        )
        db.add_all([step1, step2, step3])
        db.commit()

        print(f"\n[2] Initialized Plan with 3 Steps:")
        print(f"    1. {step1.description} [Tool: {step1.intended_tool}]")
        print(f"    2. {step2.description} [Tool: {step2.intended_tool}] (Injected with bad expression 100 / (5 - 5))")
        print(f"    3. {step3.description} [Tool: {step3.intended_tool}]")

        print("\n" + "-" * 70)
        print("Starting Autonomous Agent Execution Cycle...")
        print("-" * 70)

        demo_llm = DeliberateFailureLLMClient()

        # 3. Execute through the full orchestrator
        run = run_agent(run.id, db=db, llm_client=demo_llm) or run
        db.expire_all()
        db.refresh(run)

        # 4. Print Summary and Final Report
        print("\n" + "=" * 70)
        print("AGENT EXECUTION FINISHED")
        print("=" * 70)
        print(f"Run ID: {run.id}")
        print(f"Goal: {run.goal_text}")
        print(f"Final Run Status: {run.status}")
        print(f"Completed At: {run.completed_at}")

        current_plan = next((p for p in run.plans if p.is_current), run.plans[-1] if run.plans else None)
        if current_plan and current_plan.steps:
            print("\nStep Execution Summary & Observation Classifications:")
            for idx, step in enumerate(current_plan.steps, start=1):
                obs_info = "No observation"
                if step.observation:
                    obs_info = f"Classification: {step.observation.classification.upper()} | Recommendation: {step.observation.recommendation} | Reason: {step.observation.reasoning}"
                print(f"  {idx}. [{step.status.upper()}] {step.description}")
                print(f"     -> {obs_info}")
                if step.result_ref:
                    print(f"     -> Result Reference: {step.result_ref}")

        if run.report:
            print("\n" + "-" * 70)
            print("FINAL GENERATED RESEARCH REPORT:")
            print("-" * 70)
            print(run.report.content_markdown)
        else:
            print("\nNo report generated.")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    run_deliberate_failure_demo()
