import logging
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, status

# Ensure paths are available for imports
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from backend.app.schemas.contracts import AgentRunRequest, AgentRunResponse
    from backend.app.modules.agent.adapter import run_agent
except ImportError:
    try:
        from app.schemas.contracts import AgentRunRequest, AgentRunResponse
        from app.modules.agent.adapter import run_agent
    except ImportError:
        from schemas.contracts import AgentRunRequest, AgentRunResponse
        from adapter import run_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])


@router.post("/run", response_model=AgentRunResponse, status_code=status.HTTP_200_OK)
async def run_agent_endpoint(request: AgentRunRequest) -> AgentRunResponse:
    """
    Execute the agent workflow for a given pipeline_run_id:
    Reads upstream Vision and RAG state, evaluates decision rules,
    and coordinates agent execution.
    """
    logger.info(f"Received Agent run request for pipeline_run_id={request.pipeline_run_id}")
    try:
        response = await run_agent(request.pipeline_run_id)
        return response
    except Exception as exc:
        logger.error(f"Error executing agent run for {request.pipeline_run_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {str(exc)}",
        ) from exc
