from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import PROJECT_ROOT, Settings


class HealthResponse(BaseModel):
    status: str
    version: str
    timezone: str


def create_app(settings: Settings | None = None, frontend_dir: Path | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="On the Desk AI Assistant", version="0.1.0")

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=app.version, timezone=settings.timezone)

    # API routes must precede the root static mount.
    dist = frontend_dir if frontend_dir is not None else PROJECT_ROOT / "frontend" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app
