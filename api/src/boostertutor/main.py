"""FastAPI application entry point for the BoosterTutor API."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .db import engine
from .routes import drafts

app = FastAPI(title="BoosterTutor API", version="0.1.0")

# Browsers refuse cross-origin requests unless the server explicitly allows them.
# Our frontend runs on a different origin (port 5173 in dev, boostertutor.dev in
# production), so the API has to opt in by name. Production origins get added
# when we deploy - never use a wildcard here, since this list is what stops
# arbitrary websites from calling your API with a logged-in user's credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(drafts.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Render pings this; so will you, constantly, while debugging."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db() -> dict[str, str]:
    """Confirms the database is reachable. Returns 503 if not."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        # Leaking the driver's error is a dev convenience, not production
        # behaviour - Phase 8 replaces this with a log line and a generic
        # message, since error text can disclose hostnames and usernames.
        raise HTTPException(
            status_code=503, detail=f"database unreachable: {exc}"
        ) from exc
    return {"status": "ok"}
