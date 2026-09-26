import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
META_DB_PATH = DATA_DIR / "meta.db"

# Frontend dist directory with Docker / production fallbacks
FRONTEND_DIST_ENV = os.getenv("FRONTEND_DIST_DIR")
if FRONTEND_DIST_ENV and Path(FRONTEND_DIST_ENV).exists():
    FRONTEND_DIST = Path(FRONTEND_DIST_ENV)
else:
    FRONTEND_DIST = WORKSPACE_DIR / "frontend" / "dist"
    if not FRONTEND_DIST.exists():
        for candidate in [BASE_DIR / "frontend" / "dist", BASE_DIR / "dist", Path("/app/frontend/dist")]:
            if candidate.exists():
                FRONTEND_DIST = candidate
                break

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load .env file (check local nl2sql-backend/.env first, then workspace root .env)
env_path = BASE_DIR / ".env"
if not env_path.exists() and (WORKSPACE_DIR / ".env").exists():
    env_path = WORKSPACE_DIR / ".env"

load_dotenv(dotenv_path=env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

if not GEMINI_API_KEY:
    import logging
    logging.getLogger(__name__).warning(
        "GEMINI_API_KEY is missing or empty. Queries requiring Gemini will fail unless GEMINI_API_KEY is provided."
    )

# SQLite Database URLs
DATABASE_URL = f"sqlite:///{META_DB_PATH.as_posix()}"
DEMO_HOSPITAL_DB_PATH = DATA_DIR / "demo_hospital.db"
DEMO_ECOMMERCE_DB_PATH = DATA_DIR / "demo_ecommerce.db"

# Environment: set APP_ENV=production in production deployments.
# Defaults to "development" so local dev stays permissive automatically.
APP_ENV: str = os.getenv("APP_ENV", "development").lower().strip()
IS_PRODUCTION: bool = APP_ENV == "production"
