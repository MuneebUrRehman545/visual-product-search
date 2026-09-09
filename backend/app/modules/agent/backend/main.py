import asyncio
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import schemas
from agent.events import (
    EVENT_CATCH_UP,
    EVENT_RUN_COMPLETED,
    EVENT_RUN_FAILED,
    event_emitter,
)
from agent.orchestrator import run_agent
from database import get_db

app = FastAPI(title="Autonomous Research Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://research-agent-five-delta.vercel.app",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/runs", response_model=schemas.RunResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: schemas.RunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    run = models.Run(
        goal_text=payload.goal_text,
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(run_agent, run.id)

    return run


@app.get("/runs", response_model=List[schemas.RunResponse])
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(models.Run).order_by(models.Run.created_at.desc()).all()
    return runs


@app.get("/runs/{run_id}", response_model=schemas.RunResponse)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with id {run_id} not found",
        )
    return run


@app.get("/runs/{run_id}/steps", response_model=List[schemas.StepResponse])
def get_run_steps(run_id: uuid.UUID, db: Session = Depends(get_db)):
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with id {run_id} not found",
        )
    steps = (
        db.query(models.Step)
        .join(models.Plan, models.Step.plan_id == models.Plan.id)
        .filter(models.Plan.run_id == run_id)
        .order_by(models.Step.created_at.asc())
        .all()
    )
    return steps


@app.get("/runs/{run_id}/report", response_model=schemas.ReportResponse)
def get_run_report(run_id: uuid.UUID, db: Session = Depends(get_db)):
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with id {run_id} not found",
        )
    if not run.report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report for run {run_id} not found",
        )
    return run.report


@app.websocket("/runs/{run_id}/stream")
async def websocket_run_stream(websocket: WebSocket, run_id: uuid.UUID):
    await websocket.accept()

    # 1. Provide Reconnect / Catch-Up Support
    db_provider = app.dependency_overrides.get(get_db, get_db)
    db_gen = db_provider()
    db = next(db_gen)
    try:
        run = db.query(models.Run).filter(models.Run.id == run_id).first()
        if not run:
            await websocket.send_json({
                "type": "error",
                "event": "error",
                "run_id": str(run_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"detail": f"Run with id {run_id} not found"},
            })
            await websocket.close(code=1008)
            return

        steps = (
            db.query(models.Step)
            .join(models.Plan, models.Step.plan_id == models.Plan.id)
            .filter(models.Plan.run_id == run_id)
            .order_by(models.Step.created_at.asc())
            .all()
        )
        steps_data = []
        for s in steps:
            s_dict = {
                "id": str(s.id),
                "plan_id": str(s.plan_id),
                "description": s.description,
                "intended_tool": s.intended_tool,
                "status": s.status,
                "result_ref": s.result_ref,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "tool_calls": [
                    {
                        "id": str(tc.id),
                        "tool_name": tc.tool_name,
                        "input_args": tc.input_args,
                        "output_data": tc.output_data,
                        "success": tc.success,
                        "error_message": tc.error_message,
                        "created_at": tc.created_at.isoformat() if tc.created_at else None,
                    }
                    for tc in s.tool_calls
                ],
                "observation": {
                    "id": str(s.observation.id),
                    "classification": s.observation.classification,
                    "recommendation": s.observation.recommendation,
                    "reasoning": s.observation.reasoning,
                    "created_at": s.observation.created_at.isoformat() if s.observation.created_at else None,
                } if s.observation else None,
            }
            steps_data.append(s_dict)

        catch_up_msg = {
            "type": EVENT_CATCH_UP,
            "event": EVENT_CATCH_UP,
            "run_id": str(run.id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "run": {
                    "id": str(run.id),
                    "goal_text": run.goal_text,
                    "status": run.status,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                },
                "steps": steps_data,
                "report": {
                    "id": str(run.report.id),
                    "content_markdown": run.report.content_markdown,
                    "created_at": run.report.created_at.isoformat() if run.report.created_at else None,
                } if run.report else None,
            },
        }
        await websocket.send_json(catch_up_msg)

        # If already completed or failed, close connection cleanly after catch up
        if run.status in ("complete", "failed"):
            terminal_event = EVENT_RUN_COMPLETED if run.status == "complete" else EVENT_RUN_FAILED
            await websocket.send_json({
                "type": terminal_event,
                "event": terminal_event,
                "run_id": str(run.id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "run_id": str(run.id),
                    "status": run.status,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                },
            })
            await websocket.close(code=1000)
            return

    finally:
        try:
            db_gen.close()
        except Exception:
            pass

    # 2. Register with EventEmitter for live events
    loop = asyncio.get_running_loop()
    event_emitter.subscribe(run_id, websocket, loop=loop)
    try:
        while True:
            # Keep stream open until closed by client or emitter
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        event_emitter.unsubscribe(run_id, websocket)



