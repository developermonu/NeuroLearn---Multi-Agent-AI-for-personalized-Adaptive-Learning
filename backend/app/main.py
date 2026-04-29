import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.config import settings
from app.database import init_db
import logging

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NeuroLearn Platform...")
    await init_db()
    # Initialize vector store
    try:
        from app.services.vector_store import vector_store_service

        vector_store_service.initialize()
        logger.info("Vector store initialized")
    except Exception as e:
        logger.warning(f"Vector store not available: {e}")
    yield
    logger.info("Shutting down NeuroLearn Platform...")


app = FastAPI(
    title="NeuroLearn - Adaptive Learning Platform",
    description="Hyper-Personalized Adaptive Learning Ecosystem powered by Multi-Agent AI",
    version="1.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
from app.routers import (
    auth,
    courses,
    diagnostic,
    learning_path,
    quiz,
    qa,
    progress,
    certificates,
    llm_test,
    content_gen,
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(
    courses.router, prefix="/api/v1/courses", tags=["Courses & Exams"]
)
app.include_router(
    diagnostic.router, prefix="/api/v1/diagnostic", tags=["Diagnostic Engine"]
)
app.include_router(
    learning_path.router, prefix="/api/v1/learning-path", tags=["Learning Path"]
)
app.include_router(
    quiz.router, prefix="/api/v1/quiz", tags=["Quiz & Assessment"]
)
app.include_router(qa.router, prefix="/api/v1/qa", tags=["Q&A AI Tutor"])
app.include_router(
    progress.router, prefix="/api/v1/progress", tags=["Progress & Analytics"]
)
app.include_router(
    certificates.router, prefix="/api/v1/certificates", tags=["Certificates"]
)
app.include_router(
    llm_test.router, prefix="/api/v1/llm-test", tags=["LLM Test & Diagnostics"]
)
app.include_router(
    content_gen.router, prefix="/api/v1/generate", tags=["Content Generation (SSE)"]
)


from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )

# Global exception handler — ensures all errors return JSON, never plain text
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


@app.get("/api/health")
async def health_check():
    """Health check with DB connectivity verification."""
    db_ok = False
    try:
        from app.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    status = "healthy" if db_ok else "degraded"
    return {
        "status": status,
        "platform": "NeuroLearn",
        "version": "1.1.1",
        "database": "connected" if db_ok else "unavailable",
    }


# Serve frontend static files (mount is checked AFTER all API routes)
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
