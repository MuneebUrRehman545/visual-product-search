"""FastAPI application entrypoint for Visual Product Search API."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env once at application startup
load_dotenv()

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.services.search_service_registry import get_search_service
from app.vision_router import router as vision_router, CATALOG_IMAGES_DIR
from app.rag_router import router as rag_router

logger = logging.getLogger(__name__)

# Allowed frontend origins for CORS (Localhost, LAN development, Next.js ports)
ALLOWED_ORIGINS = [
    "*",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:3000",
    "http://192.168.100.63:5173",
    "http://192.168.100.63:5174",
    "http://192.168.100.63:3000",
]
env_origins = os.getenv("ALLOWED_ORIGINS")
if env_origins:
    ALLOWED_ORIGINS = [origin.strip() for origin in env_origins.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager to load ML models and index into RAM on startup."""
    try:
        get_search_service()
    except Exception as e:
        logger.warning(f"Could not preload search service during lifespan: {e}")
    yield


app = FastAPI(
    title="Visual Product Search API",
    description="API for visual product search using OpenCLIP ViT-B-32 embeddings and FAISS index.",
    version="1.0.0",
    lifespan=lifespan,
)

# Global CORP and CORS Header Injection Middleware
# Guaranteed prevention of net::ERR_BLOCKED_BY_ORB on cross-origin image loads
@app.middleware("http")
async def add_corp_and_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


# Add CORS Middleware supporting local development, LAN IP, and production origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Vision & Catalog Router with all routes and aliases
app.include_router(vision_router)
app.include_router(rag_router)
