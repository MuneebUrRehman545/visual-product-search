import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import models
from agent.orchestrator import run_agent
from database import SessionLocal


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print('Usage: python cli.py "some research goal"')
        sys.exit(1)

    goal_text = sys.argv[1].strip()
    if not goal_text:
        print("Error: Research goal cannot be empty.")
        sys.exit(1)

    if SessionLocal is None:
        print("Error: DATABASE_URL is not configured in environment.")
        sys.exit(1)

    db = SessionLocal()
    try:
        run = models.Run(goal_text=goal_text, status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)

        print(f"Created run {run.id} with initial status: {run.status}")
        print("Running agent synchronously...")

        run = run_agent(run.id, db=db) or run
        db.expire_all()
        db.refresh(run)

        print("\n" + "=" * 60)
        print(f"Run ID: {run.id}")
        print(f"Goal: {run.goal_text}")
        print(f"Final Status: {run.status}")

        current_plan = None
        if run.plans:
            current_plan = next((p for p in run.plans if p.is_current), run.plans[-1])

        if current_plan and current_plan.steps:
            print("\nExecuted Plan Steps & Outcomes:")
            for idx, step in enumerate(current_plan.steps, start=1):
                obs_text = ""
                if step.observation:
                    obs_text = f" -> [{step.observation.classification.upper()}] {step.observation.reasoning}"
                print(f"  {idx}. [{step.status.upper()}] {step.description} [Tool: {step.intended_tool}]{obs_text}")

        if run.report:
            print("\n" + "-" * 40)
            print("Final Report Markdown:")
            print("-" * 40)
            print(run.report.content_markdown)
        else:
            print("\nNo report generated.")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    main()
