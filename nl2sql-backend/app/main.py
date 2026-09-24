import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.models.meta_db import init_db
from app.routers import connect_db, query

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize metadata database tables on startup
    init_db()
    # Pre-warm demo schema cache for instant connection
    connect_db.preload_demo_cache()
    yield



app = FastAPI(
    title="NL2SQL Assistant Backend",
    description="Natural Language to SQL Assistant Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://project-final-nl-2-sql.vercel.app",
    "https://project-final-nl-2-sql.vercel.app/",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app/?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global fallback exception handler: logs stack trace server-side without leaking internals to clients."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again later."},
    )


# Register Phase 2 Routers
app.include_router(connect_db.router, prefix="/api", tags=["Database Connection"])
app.include_router(query.router, prefix="/api", tags=["Query"])


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
