import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from app.config import IS_PRODUCTION
from app.models.meta_db import init_db
from app.routers import connect_db, query, conversations

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security response headers to every request.

    Headers added:
    - X-Content-Type-Options: nosniff          — prevents MIME-type sniffing
    - X-Frame-Options: DENY                    — blocks framing (clickjacking)
    - Content-Security-Policy                  — restricts resource origins for SPA
    - Referrer-Policy                          — limits referrer leakage
    - X-XSS-Protection                         — legacy XSS filter hint (belt+suspenders)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # CSP for a single-page application served from its own origin.
        # - default-src 'self'       → all resources must come from same origin
        # - script-src 'self'        → only same-origin JS (no inline, no CDN)
        # - style-src 'self' 'unsafe-inline' → allow component-scoped styles
        # - img-src 'self' data:     → allow base64-encoded images (chart blobs)
        # - font-src 'self'          → same-origin fonts
        # - connect-src 'self'       → XHR/fetch only to same origin
        # - frame-ancestors 'none'   → equivalent of X-Frame-Options: DENY for CSP3
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize metadata database tables on startup
    init_db()
    # Pre-warm demo schema cache for instant connection
    connect_db.preload_demo_cache()
    env_label = "production" if IS_PRODUCTION else "development"
    logger.info("NL2SQL backend starting in %s mode.", env_label)
    yield


app = FastAPI(
    title="NL2SQL Assistant Backend",
    description="Natural Language to SQL Assistant Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — environment-aware
# ---------------------------------------------------------------------------
# Production: frontend is served from FastAPI itself (same origin), so only
# the Vercel deployment URL is allowed as a cross-origin caller.
# Development: also allow the Vite dev server (localhost:5173 / :3000).
# ---------------------------------------------------------------------------
if IS_PRODUCTION:
    cors_origins = [
        "https://project-final-nl-2-sql.vercel.app",
        "https://project-final-nl-2-sql.vercel.app/",
    ]
    cors_origin_regex = r"https://.*\.vercel\.app/?"
    cors_allow_credentials = False  # no cookies needed; keeps surface area minimal
else:
    # Development: allow local Vite/React dev servers
    cors_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://project-final-nl-2-sql.vercel.app",
        "https://project-final-nl-2-sql.vercel.app/",
    ]
    cors_origin_regex = r"https://.*\.vercel\.app/?"
    cors_allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=cors_allow_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Security headers applied to every response (after CORS so CORS headers win)
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global fallback exception handler: logs stack trace server-side without leaking internals to clients."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again later."},
    )


# Register Routers
app.include_router(connect_db.router, prefix="/api", tags=["Database Connection"])
app.include_router(query.router, prefix="/api", tags=["Query"])
app.include_router(conversations.router, prefix="/api", tags=["Conversations"])


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

