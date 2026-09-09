import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Enable JSONB compilation on SQLite for testing
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")

from database import Base, get_db
from main import app

# Create in-memory SQLite database for testing with StaticPool
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


@pytest.fixture(autouse=True)
def mock_llm_generate():
    import json
    mock_plan_json = json.dumps({
        "steps": [
            {"description": "Search web for background", "intended_tool": "web_search"},
            {"description": "Synthesize summary", "intended_tool": "none"},
        ]
    })
    with patch("agent.planning.LLMClient.generate_json") as mock_gen:
        mock_gen.return_value = mock_plan_json
        yield mock_gen


client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_run_success():
    payload = {"goal_text": "Research Tokyo rainfall from 2000 to 2020"}
    response = client.post("/runs", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["goal_text"] == "Research Tokyo rainfall from 2000 to 2020"
    assert data["status"] == "pending"
    assert "id" in data
    assert "created_at" in data
    assert data["plans"] == []
    assert data["report"] is None


def test_create_run_empty_goal():
    response = client.post("/runs", json={"goal_text": ""})
    assert response.status_code == 422

    response = client.post("/runs", json={"goal_text": "   "})
    assert response.status_code == 422


def test_create_run_missing_goal():
    response = client.post("/runs", json={})
    assert response.status_code == 422


def test_get_run_by_id_success():
    create_resp = client.post("/runs", json={"goal_text": "Analyze renewable energy trends"})
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]

    get_resp = client.get(f"/runs/{run_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == run_id
    assert data["goal_text"] == "Analyze renewable energy trends"
    assert data["status"] == "complete"
    assert len(data["plans"]) == 1
    assert len(data["plans"][0]["steps"]) == 2



def test_get_run_by_id_not_found():
    random_id = str(uuid.uuid4())
    response = client.get(f"/runs/{random_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Run with id {random_id} not found"


def test_get_runs_list():
    client.post("/runs", json={"goal_text": "First research task"})
    client.post("/runs", json={"goal_text": "Second research task"})

    response = client.get("/runs")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 2
    goal_texts = [r["goal_text"] for r in runs]
    assert "First research task" in goal_texts
    assert "Second research task" in goal_texts
