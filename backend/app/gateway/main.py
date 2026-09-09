import asyncio
import logging
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure both the backend root and the actual repo root are on sys.path.
# The repo root must come first so Muneeb's top-level app/ package
# (containing services/, db/, vision_router.py) resolves before
# backend/app/'s own namespace, which would otherwise shadow it.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(1, str(BACKEND_ROOT))

from backend.app.gateway.database import init_db
from backend.app.gateway.orchestrator_poller import poll_and_trigger
from backend.app.gateway.router import router as gateway_router
from backend.app.modules.agent.router import router as agent_router
from app.services.search_service_registry import get_search_service
from app.vision_router import router as vision_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway")
POLLER_INTERVAL_SECONDS = 3


async def _poll_forever() -> None:
    """Run the orchestration poll on a fixed interval until shutdown."""
    while True:
        try:
            await poll_and_trigger()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Gateway orchestration poll failed.")

        await asyncio.sleep(POLLER_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    logger.info("Initializing Gateway database tables...")
    try:
        init_db()
        logger.info("Gateway database initialized successfully.")
    except Exception as exc:
        logger.warning(f"Could not auto-initialize DB tables on startup (may be handled externally): {exc}")

    # Preload Vision's CLIP model and FAISS index for the mounted router.
    try:
        get_search_service()
        logger.info("Vision search service preloaded successfully.")
    except Exception as exc:
        logger.warning(f"Could not preload Vision search service during lifespan: {exc}")

    poller_task = asyncio.create_task(
        _poll_forever(),
        name="gateway-orchestrator-poller",
    )
    logger.info(
        "Gateway orchestration poller started; interval=%ss.",
        POLLER_INTERVAL_SECONDS,
    )

    try:
        yield
    finally:
        logger.info("Stopping Gateway orchestration poller.")
        poller_task.cancel()
        with suppress(asyncio.CancelledError):
            await poller_task


app = FastAPI(
    title="AI-Assistant Gateway BFF",
    description="Unified API Gateway and Backend-For-Frontend orchestrating Vision, RAG, and Agent pipeline lifecycles.",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(gateway_router)
app.include_router(agent_router)


@app.get("/health", tags=["Health"])
@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "service": "AI-Assistant Gateway",
        "version": "1.0.0",
    }


# Mount after the canonical Gateway health routes so Vision's duplicate
# /health and /api/v1/health aliases do not shadow them.
# Vision's image routes already attach their own ORB/CORP response headers;
# CORS remains centralized in this Gateway application.
app.include_router(vision_router)
