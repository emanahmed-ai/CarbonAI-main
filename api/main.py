"""CarbonAI API entry point.

    uvicorn api.main:app --host 0.0.0.0 --port 8000

On startup the DB is created/migrated (additive, idempotent) and seeded; the built React
frontend (frontend/dist) is served as the root SPA when it exists.
"""
from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.config import CORS_ORIGINS, FRONTEND_DIST
from api.routers import (auth, dashboard, factors, imports, invoices, ml, org, plans,
                         records, references, reports, settings, submissions, users)
from db.connection import connect
from db.schema import init_db
from db.seed import seed_all


def startup_init() -> dict:
    """Idempotent init + seed. Returns the seed report for the console."""
    con = connect()
    try:
        init_db(con)
        report = seed_all(con)
        con.commit()
        return report
    finally:
        con.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    report = startup_init()
    auth = report.get("auth", {})
    print(f"[CarbonAI] DB ready. seed: countries={report.get('countries')} categories={report.get('categories')} "
          f"sources={report.get('sources')} nz_factors={report.get('nz_factors')}")
    if auth.get("admin"):
        print("[CarbonAI] First run: created the default admin user 'admin'.")
        if auth.get("password_source") == "default":
            print("[CarbonAI] *** Initial password is 'admin123' - you MUST change it after first login. ***")
            print("[CarbonAI] Set CARBONAI_ADMIN_PASSWORD to choose it explicitly next time.")
    else:
        print("[CarbonAI] Existing user accounts found; nothing reseeded.")
    yield


app = FastAPI(title="CarbonAI API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(_req: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(LookupError)
async def lookup_error_handler(_req: Request, exc: LookupError):
    # KeyError is a programming bug, not a missing resource - never mask it as 404.
    if isinstance(exc, KeyError):
        return JSONResponse(status_code=500, content={"detail": f"internal error: missing key {exc}"})
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(PermissionError)
async def permission_error_handler(_req: Request, exc: PermissionError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error_handler(_req: Request, exc: sqlite3.IntegrityError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "CarbonAI", "version": "2.0.0"}


for r in (auth.router, users.router, org.router, records.router, factors.router,
          dashboard.router, reports.router, imports.router, invoices.router,
          submissions.router, ml.router, settings.router, plans.router,
          references.router):
    app.include_router(r)

# ---- built React frontend (production) ----
if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # Unknown API routes must be JSON 404s, never the SPA HTML shell.
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        candidate = (FRONTEND_DIST / full_path.lstrip("/")).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(FRONTEND_DIST.resolve())):
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
