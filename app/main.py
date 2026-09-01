"""FastAPI application entrypoint for Visual Product Search API."""

from contextlib import asynccontextmanager
import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from dotenv import load_dotenv

# Load .env once at application startup
load_dotenv()

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image

from app.db.database import (
    create_db_user,
    get_catalog_count,
    get_catalog_items_by_category,
    get_db_user_by_email,
    get_db_user_by_id,
    get_top_catalog_categories,
    init_user_tables,
    is_postgres,
    update_user_last_login,
)
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest, UserResponse
from app.schemas.search import SearchResponse, SearchResultItem
from app.schemas.vision_pipeline import VisionProcessResponse
from app.modules.vision.adapter import process_vision_request
from app.services.auth_service import (
    create_access_token,
    hash_password,
    verify_access_token,
    verify_password,
)
from app.services.search_service_registry import (
    get_resnet_search_service,
    get_search_service,
)

# Dynamic root resolution for catalog images directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_img_dir = os.getenv("CATALOG_IMAGES_DIR")
if env_img_dir:
    CATALOG_IMAGES_DIR = (PROJECT_ROOT / env_img_dir).resolve() if not Path(env_img_dir).is_absolute() else Path(env_img_dir).resolve()
elif (PROJECT_ROOT / "data" / "images").exists():
    CATALOG_IMAGES_DIR = (PROJECT_ROOT / "data" / "images").resolve()
else:
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
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint to verify backend operational status and catalog readiness."""
    try:
        count = get_catalog_count()
        db_type = "postgresql" if is_postgres() else "sqlite"
        return {
            "status": "ok",
            "database": db_type,
            "catalog_count": count,
            "model": "OpenCLIP_ViT_B_32",
            "embedding_dimension": 512,
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
            "model": "OpenCLIP_ViT_B_32",
        }


# ============================================================================
# Authentication Dependency & Endpoints
# ============================================================================

def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Extract authenticated user payload if valid Bearer token provided."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer ") :].strip()
    return verify_access_token(token)


def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Require authenticated user from Bearer token."""
    user_payload = get_current_user_optional(authorization)
    if not user_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing, expired, or invalid.",
        )
    return user_payload


@app.post("/api/auth/signup", response_model=AuthResponse, tags=["Authentication"])
async def signup(payload: SignupRequest):
    """Register a new user account."""
    existing_user = get_db_user_by_email(payload.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    pwd_hash, salt = hash_password(payload.password)
    try:
        created = create_db_user(
            email=payload.email,
            username=payload.username,
            password_hash=pwd_hash,
            salt=salt,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user account: {str(e)}",
        )

    token = create_access_token(created["id"], created["email"], created["username"])
    return AuthResponse(
        token=token,
        user=UserResponse(
            id=created["id"],
            email=created["email"],
            username=created["username"],
            created_at=str(created.get("created_at", "")),
        ),
        message="Account created successfully!",
    )


@app.post("/api/auth/login", response_model=AuthResponse, tags=["Authentication"])
async def login(payload: LoginRequest):
    """Authenticate existing user and return access token."""
    user = get_db_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"], user["salt"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    update_user_last_login(user["id"])
    token = create_access_token(user["id"], user["email"], user["username"])
    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            username=user["username"],
            created_at=str(user.get("created_at", "")),
            last_login=str(user.get("last_login", "")),
        ),
        message="Logged in successfully!",
    )


@app.get("/api/auth/me", response_model=UserResponse, tags=["Authentication"])
async def get_my_profile(auth_user: Dict[str, Any] = Depends(get_current_user)):
    """Fetch profile of currently authenticated user."""
    user = get_db_user_by_id(auth_user["user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found.",
        )
    return UserResponse(
        id=user["id"],
        email=user["email"],
        username=user["username"],
        created_at=str(user.get("created_at", "")),
        last_login=str(user.get("last_login", "")),
    )


@app.get("/api/auth/demo", response_model=AuthResponse, tags=["Authentication"])
async def demo_login():
    """One-click instant demo login for guest evaluation."""
    demo_email = "demo.user@antigravity.ai"
    demo_user = get_db_user_by_email(demo_email)

    if not demo_user:
        pwd_hash, salt = hash_password("DemoPassword2026!")
        demo_user = create_db_user(
            email=demo_email,
            username="Demo Explorer",
            password_hash=pwd_hash,
            salt=salt,
        )

    token = create_access_token(demo_user["id"], demo_user["email"], demo_user["username"])
    return AuthResponse(
        token=token,
        user=UserResponse(
            id=demo_user["id"],
            email=demo_user["email"],
            username=demo_user["username"],
            created_at=str(demo_user.get("created_at", "")),
        ),
        message="Demo session activated!",
    )


# ============================================================================
# Catalog Category Presets Endpoints
# ============================================================================

@app.get("/api/catalog/categories", tags=["Catalog Categories"])
async def list_top_categories(limit: int = 8):
    """Retrieve top categories from catalog with item counts and sample images."""
    try:
        categories = get_top_catalog_categories(limit=limit)
        return {"total_categories": len(categories), "categories": categories}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch catalog categories: {str(e)}",
        )


@app.get("/api/catalog/category/{category_name}", response_model=SearchResponse, tags=["Catalog Categories"])
async def get_items_by_category_endpoint(
    category_name: str,
    limit: int = Query(20, ge=1, le=50, description="Max items to return"),
):
    """Retrieve products for a given category from the catalog database."""
    items = get_catalog_items_by_category(category_name=category_name, limit=limit)
    if not items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No products found for category '{category_name}'.",
        )

    formatted_results = []
    for rank, item in enumerate(items, start=1):
        cid = item["id"]
        fn = item.get("filename") or f"{item.get('image_id')}.jpg"
        img_url = item.get("image_url") or f"/catalog-images/{fn}"
        formatted_results.append(
            SearchResultItem(
                rank=rank,
                catalog_item_id=cid,
                product_id=int(item.get("product_id", cid)),
                external_id=str(item.get("external_id") or item.get("image_id") or cid),
                filename=fn,
                product_display_name=item.get("product_display_name"),
                category=item.get("category"),
                sub_category=item.get("sub_category"),
                article_type=item.get("article_type"),
                base_colour=item.get("base_colour"),
                gender=item.get("gender"),
                season=item.get("season"),
                usage=item.get("usage"),
                image_url=img_url,
                similarity_score=0.0,
            )
        )

    return SearchResponse(
        query_filename=f"Category: {category_name}",
        top_k=limit,
        total_results=len(formatted_results),
        model_used="Database_Catalog_Browse",
        results=formatted_results,
    )


@app.get("/catalog-images/{filename}", tags=["Catalog Images"])
async def get_catalog_image(filename: str):
    """Serve catalog images safely by filename."""
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


async def _execute_search(
    file: Optional[UploadFile] = None,
    catalog_filename: Optional[str] = None,
    catalog_item_id: Optional[int] = None,
    requested_top_k: int = 10,
    model_choice: Optional[str] = "clip",
) -> SearchResponse:
    """Core search execution pipeline supporting uploaded images and direct catalog items."""
    rgb_image: Optional[Image.Image] = None
    query_filename: str = "query.jpg"

    if catalog_filename:
        safe_fn = os.path.basename(catalog_filename)
        image_path = (CATALOG_IMAGES_DIR / safe_fn).resolve()
        if not image_path.exists() or not image_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Catalog image '{safe_fn}' not found.",
            )
        try:
            rgb_image = Image.open(image_path).convert("RGB")
            query_filename = safe_fn
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to read catalog image: {str(e)}",
            )
    elif file is not None:
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

        # Validate image decoding with PIL
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
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either an image file or a catalog_filename must be provided.",
        )

    # Resolve model service
    model_key = (model_choice or "clip").lower().strip()
    if model_key in ["resnet", "resnet50", "resnet-50", "resnet_50"]:
        service = get_resnet_search_service()
        model_used = "ResNet_50"
    else:
        service = get_search_service()
        model_used = "OpenCLIP_ViT_B_32"

    # Perform visual search
    try:
        raw_results = service.search(rgb_image, top_k=requested_top_k)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Visual search processing error ({model_used}): {str(e)}",
        )

    formatted_results = []
    for item in raw_results:
        fn = item.get("filename") or f"{item.get('image_id')}.jpg"
        img_url = item.get("image_url") or f"/catalog-images/{fn}"
        formatted_results.append(
            SearchResultItem(
                rank=item["rank"],
                catalog_item_id=int(item["catalog_item_id"]),
                product_id=int(item["product_id"]),
                external_id=str(item.get("external_id") or item["product_id"]),
                filename=fn,
                product_display_name=item.get("product_display_name"),
                category=item.get("category"),
                sub_category=item.get("sub_category"),
                article_type=item.get("article_type"),
                base_colour=item.get("base_colour"),
                gender=item.get("gender"),
                season=item.get("season"),
                usage=item.get("usage"),
                image_url=img_url,
                similarity_score=float(item["similarity_score"]),
            )
        )

    return SearchResponse(
        query_filename=query_filename,
        top_k=requested_top_k,
        total_results=len(formatted_results),
        model_used=model_used,
        results=formatted_results,
    )


@app.post(
    "/search",
    response_model=SearchResponse,
    tags=["Search"],
    summary="Search catalog for visually similar products",
)
async def search_endpoint(
    file: Optional[UploadFile] = File(None, description="Query image file (JPG, PNG, WebP)"),
    catalog_filename: Optional[str] = Form(None, description="Catalog image filename to search with directly"),
    catalog_filename_query: Optional[str] = Query(None, alias="catalog_filename", description="Catalog image filename (Query param)"),
    top_k: Optional[int] = Form(None, description="Number of top results to return (1-50)"),
    top_k_query: Optional[int] = Query(None, alias="top_k", description="Number of top results (Query param)"),
    model: Optional[str] = Form(None, description="Model choice: 'clip' (default) or 'resnet'"),
    model_query: Optional[str] = Query(None, alias="model", description="Model choice: 'clip' or 'resnet'"),
):
    """Primary visual search endpoint with CLIP / ResNet model selection."""
    requested_top_k = top_k if top_k is not None else top_k_query
    if requested_top_k is None:
        requested_top_k = 10

    selected_model = model if model is not None else model_query
    if not selected_model:
        selected_model = "clip"

    if not isinstance(requested_top_k, int) or requested_top_k < 1 or requested_top_k > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="top_k must be an integer between 1 and 50.",
        )

    resolved_catalog_fn = catalog_filename if catalog_filename is not None else catalog_filename_query

    return await _execute_search(
        file=file,
        catalog_filename=resolved_catalog_fn,
        requested_top_k=requested_top_k,
        model_choice=selected_model,
    )


@app.post(
    "/api/v1/search",
    response_model=SearchResponse,
    tags=["Search"],
    summary="Search catalog for visually similar products (v1 API)",
)
async def api_v1_search_endpoint(
    file: Optional[UploadFile] = File(None, description="Query image file (JPG, PNG, WebP)"),
    catalog_filename: Optional[str] = Form(None, description="Catalog image filename to search with directly"),
    catalog_filename_query: Optional[str] = Query(None, alias="catalog_filename", description="Catalog image filename (Query param)"),
    top_k: Optional[int] = Form(None, description="Number of top results to return (1-50)"),
    top_k_query: Optional[int] = Query(None, alias="top_k", description="Number of top results (Query param)"),
    model: Optional[str] = Form(None, description="Model choice: 'clip' (default) or 'resnet'"),
    model_query: Optional[str] = Query(None, alias="model", description="Model choice: 'clip' or 'resnet'"),
):
    """API v1 visual search endpoint with CLIP / ResNet model selection."""
    requested_top_k = top_k if top_k is not None else top_k_query
    if requested_top_k is None:
        requested_top_k = 10

    selected_model = model if model is not None else model_query
    if not selected_model:
        selected_model = "clip"

    if not isinstance(requested_top_k, int) or requested_top_k < 1 or requested_top_k > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="top_k must be an integer between 1 and 50.",
        )

    resolved_catalog_fn = catalog_filename if catalog_filename is not None else catalog_filename_query

    return await _execute_search(
        file=file,
        catalog_filename=resolved_catalog_fn,
        requested_top_k=requested_top_k,
        model_choice=selected_model,
    )


# ============================================================================
# Week 4 Vision -> RAG Integration Endpoint
# ============================================================================

@app.post(
    "/api/v1/vision/process",
    response_model=VisionProcessResponse,
    tags=["Integration"],
    summary="Process query image and persist visual matches for RAG module handoff",
)
async def vision_process_endpoint(
    image: UploadFile = File(..., description="Query image file (JPEG, PNG, WebP)"),
    pipeline_run_id: str = Form(..., description="Orchestrator-assigned Pipeline Run UUID"),
    top_k: Optional[int] = Form(10, description="Number of top results to return (1-50)"),
    model: Optional[str] = Form("clip", description="Model choice: 'clip' (default) or 'resnet'"),
):
    """Week 4 canonical integration endpoint for Vision -> RAG handoff."""
    # 1. Validate pipeline_run_id UUID format
    try:
        valid_run_uuid = uuid.UUID(pipeline_run_id.strip())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pipeline_run_id must be a valid UUID.",
        )

    # 2. Validate top_k
    resolved_top_k = top_k if top_k is not None else 10
    if not isinstance(resolved_top_k, int) or resolved_top_k < 1 or resolved_top_k > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="top_k must be an integer between 1 and 50.",
        )

    # 3. Validate canonical model choice
    clean_model = (model or "clip").lower().strip()
    if clean_model not in ["clip", "resnet"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported model. Allowed canonical values: 'clip', 'resnet'.",
        )

    # 4. Validate image file and decoding
    try:
        contents = await image.read()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded image file.",
        )

    if not contents or len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty.",
        )

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

    # 5. Delegate processing to Vision integration adapter
    return process_vision_request(
        query_image=rgb_image,
        pipeline_run_id=str(valid_run_uuid),
        filename=image.filename,
        mime_type=image.content_type,
        top_k=resolved_top_k,
        model=clean_model,
    )

