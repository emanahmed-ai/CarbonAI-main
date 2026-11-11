"""Runtime configuration from environment (with .env support). Nothing here is a secret default:
the JWT secret is generated once and stored in the DB settings table if not provided."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:  # optional, only to pick up a local .env file
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

JWT_ALGORITHM = "HS256"
TOKEN_MINUTES = int(os.environ.get("CARBONAI_TOKEN_MINUTES", "720"))          # 12 h sessions
ADMIN_PASSWORD_ENV = "CARBONAI_ADMIN_PASSWORD"
FRONTEND_DIST = Path(os.environ.get("CARBONAI_FRONTEND_DIST", ROOT / "frontend" / "dist"))
CORS_ORIGINS = [o for o in os.environ.get(
    "CARBONAI_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o]


def db_file() -> Path:
    from db.connection import db_path
    return db_path()
