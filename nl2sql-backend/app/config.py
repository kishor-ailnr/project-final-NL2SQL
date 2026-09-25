import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
META_DB_PATH = DATA_DIR / "meta.db"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load .env file (check local nl2sql-backend/.env first, then workspace root .env)
env_path = BASE_DIR / ".env"
if not env_path.exists() and (WORKSPACE_DIR / ".env").exists():
    env_path = WORKSPACE_DIR / ".env"

load_dotenv(dotenv_path=env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY or not GEMINI_API_KEY.strip():
    raise ValueError(
        "GEMINI_API_KEY is missing or empty. Please set a valid GEMINI_API_KEY in your .env file."
    )

# SQLite Database URLs
DATABASE_URL = f"sqlite:///{META_DB_PATH.as_posix()}"
DEMO_HOSPITAL_DB_PATH = DATA_DIR / "demo_hospital.db"
DEMO_ECOMMERCE_DB_PATH = DATA_DIR / "demo_ecommerce.db"

# Environment: set APP_ENV=production in production deployments.
# Defaults to "development" so local dev stays permissive automatically.
APP_ENV: str = os.getenv("APP_ENV", "development").lower().strip()
IS_PRODUCTION: bool = APP_ENV == "production"
