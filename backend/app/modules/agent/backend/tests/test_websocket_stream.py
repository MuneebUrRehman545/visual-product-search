import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Enable JSONB compilation on SQLite for testing
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")

import models
from agent.events import (
    EVENT_CATCH_UP,
    EVENT_OBSERVATION_MADE,
    EVENT_PLAN_CREATED,
    EVENT_REPORT_READY,
    EVENT_RUN_COMPLETED,
    EVENT_STEP_COMPLETED,
    EVENT_STEP_STARTED,
    EVENT_TOOL_CALL_RESULT,
    EVENT_TOOL_CALL_STARTED,
    event_emitter,
)
from database import Base, get_db
from main import app

# Setup in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_websocket_stream_catch_up_and_live_events():
    db = TestingSessionLocal()
    try:
        # 1. Create run and plan in DB
        run = models.Run(goal_text="Test WebSocket Live Streaming", status="in_progress")
        db.add(run)
        db.commit()
        db.refresh(run)

        plan = models.Plan(run_id=run.id, is_current=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)

        step = models.Step(
            plan_id=plan.id,
            description="Fetch initial data",
            intended_tool="web_search",
            status="completed",
        )
        db.add(step)
        db.commit()

        tc = models.ToolCall(
            step_id=step.id,
            tool_name="web_search",
            input_args={"query": "test"},
            output_data={"results": ["data1"]},
            success=True,
        )
        db.add(tc)
        db.commit()

        # Connect to websocket
        with client.websocket_connect(f"/runs/{run.id}/stream") as ws:
            # First message must be catch_up
            catch_up = ws.receive_json()
            assert catch_up["type"] == EVENT_CATCH_UP
            assert catch_up["run_id"] == str(run.id)
            assert len(catch_up["payload"]["steps"]) == 1
            assert catch_up["payload"]["steps"][0]["description"] == "Fetch initial data"

            # Emit a live event and assert client receives it
            event_emitter.emit(
                run_id=run.id,
                event_type=EVENT_STEP_STARTED,
                payload={"step_id": str(step.id), "description": "Next step started"},
            )

            msg = ws.receive_json()
            assert msg["type"] == EVENT_STEP_STARTED
            assert msg["run_id"] == str(run.id)
            assert msg["payload"]["description"] == "Next step started"

            # Emit run completed event -> should receive event and close
            event_emitter.emit(
                run_id=run.id,
                event_type=EVENT_RUN_COMPLETED,
                payload={"run_id": str(run.id), "status": "complete"},
            )

            msg_comp = ws.receive_json()
            assert msg_comp["type"] == EVENT_RUN_COMPLETED
            assert msg_comp["payload"]["status"] == "complete"

    finally:
        db.close()


def test_websocket_stream_nonexistent_run():
    random_id = uuid.uuid4()
    with client.websocket_connect(f"/runs/{random_id}/stream") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert f"Run with id {random_id} not found" in msg["payload"]["detail"]


def test_websocket_stream_already_completed_run():
    db = TestingSessionLocal()
    try:
        run = models.Run(goal_text="Finished Run", status="complete")
        db.add(run)
        db.commit()
        db.refresh(run)

        with client.websocket_connect(f"/runs/{run.id}/stream") as ws:
            # 1. Catch up message
            catch_up = ws.receive_json()
            assert catch_up["type"] == EVENT_CATCH_UP
            assert catch_up["payload"]["run"]["status"] == "complete"

            # 2. Terminal event followed by clean close
            term_msg = ws.receive_json()
            assert term_msg["type"] == EVENT_RUN_COMPLETED
            assert term_msg["payload"]["status"] == "complete"

    finally:
        db.close()
