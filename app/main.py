"""FastAPI application entrypoint for Visual Product Search API."""

from contextlib import asynccontextmanager
import io
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image

from app.schemas.search import SearchResponse, SearchResultItem
from app.services.clip_search_service import CLIPSearchService

# Dynamic root resolution for catalog images directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CATALOG_IMAGES_DIR = (PROJECT_ROOT / "data" / "catalog" / "images").resolve()

# Allowed frontend origins for CORS (Localhost and LAN development)
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://192.168.100.63:5173",
    "http://192.168.100.63:5174",
]
env_origins = os.getenv("ALLOWED_ORIGINS")
if env_origins:
    ALLOWED_ORIGINS = [origin.strip() for origin in env_origins.split(",") if origin.strip()]

# Global search service instance (loaded once on demand / app startup)
_search_service: Optional[CLIPSearchService] = None


def get_search_service() -> CLIPSearchService:
    """Retrieve or initialize singleton CLIPSearchService instance."""
    global _search_service
    if _search_service is None:
        _search_service = CLIPSearchService()
    return _search_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager to load ML models and index into RAM on startup."""
    get_search_service()
    yield


app = FastAPI(
    title="Visual Product Search API",
    description="API for visual product search using OpenCLIP ViT-B-32 embeddings and FAISS index.",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS Middleware supporting local development and LAN IP access
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+):(5173|5174|3000)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint to verify backend operational status."""
    return {"status": "ok"}


@app.get("/catalog-images/{filename}", tags=["Catalog Images"])
async def get_catalog_image(filename: str):
    """Serve catalog images safely by filename.

    Args:
        filename: Name of the image file (e.g. '15025.jpg').

    Returns:
        FileResponse: Image file stream with appropriate Content-Type header.
    """
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image filename.",
        )

    image_path = (CATALOG_IMAGES_DIR / filename).resolve()

    try:
        if not image_path.is_relative_to(CATALOG_IMAGES_DIR):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Access denied.",
            )
    except AttributeError:
        if CATALOG_IMAGES_DIR not in image_path.parents and image_path != CATALOG_IMAGES_DIR:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Access denied.",
            )

    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog image '{filename}' not found.",
        )

    return FileResponse(image_path)


@app.post(
    "/api/v1/search",
    response_model=SearchResponse,
    tags=["Search"],
    summary="Search catalog for visually similar products",
)
async def search_products(
    file: UploadFile = File(..., description="Query image file (JPG, PNG, WebP)"),
    top_k: Optional[int] = Form(None, description="Number of top results to return (1-50)"),
    top_k_query: Optional[int] = Query(None, alias="top_k", description="Number of top results (Query param)"),
):
    """Search catalog by uploaded query image.

    Args:
        file: Uploaded image file.
        top_k: Optional top_k count passed in Form payload.
        top_k_query: Optional top_k count passed as Query parameter.

    Returns:
        SearchResponse: Ranked list of visual search matches with similarity scores.
    """
    # 1. Resolve and validate top_k
    requested_top_k = top_k if top_k is not None else top_k_query
    if requested_top_k is None:
        requested_top_k = 10

    if not isinstance(requested_top_k, int) or requested_top_k < 1 or requested_top_k > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="top_k must be an integer between 1 and 50.",
        )

    # 2. Validate uploaded file presence & size
    query_filename = file.filename if file.filename else "query.jpg"

    try:
        contents = await file.read()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file.",
        )

    if not contents or len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 3. Decode & validate image integrity with PIL
    try:
        image_stream = io.BytesIO(contents)
        img = Image.open(image_stream)
        img.verify()
        image_stream.seek(0)
        rgb_image = Image.open(image_stream).convert("RGB")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid or supported image.",
        )

    # 4. Perform visual search using CLIPSearchService
    try:
        service = get_search_service()
        raw_results = service.search(rgb_image, top_k=requested_top_k)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Visual search processing error: {str(e)}",
        )

    # 5. Format results with frontend HTTP URLs
    formatted_results = []
    for item in raw_results:
        filename = item["filename"]
        formatted_results.append(
            SearchResultItem(
                rank=item["rank"],
                product_id=item["product_id"],
                external_id=str(item["external_id"]),
                filename=filename,
                category=item.get("category"),
                image_url=f"/catalog-images/{filename}",
                similarity_score=item["similarity_score"],
            )
        )

    return SearchResponse(
        query_filename=query_filename,
        top_k=requested_top_k,
        total_results=len(formatted_results),
        results=formatted_results,
    )
