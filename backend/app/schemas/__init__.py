try:
    from backend.app.schemas.contracts import (
        AgentDecision,
        AgentRunRequest,
        AgentRunResponse,
    )
except ImportError:
    from app.schemas.contracts import (
        AgentDecision,
        AgentRunRequest,
        AgentRunResponse,
    )

__all__ = [
    "AgentDecision",
    "AgentRunRequest",
    "AgentRunResponse",
]
