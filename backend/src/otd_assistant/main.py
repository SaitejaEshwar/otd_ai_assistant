from pathlib import Path
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import PROJECT_ROOT, Settings
from .tasks.api import task_router
from .tasks.store import TaskStore
from .tasks.preview import router as schedule_router
from .reminders import ReminderScheduler, ReminderStore, reminder_router
from .ai.model import LanguageModel, LlamaCppModel
from .ai.service import Assistant, assistant_router


class HealthResponse(BaseModel):
    status: str
    version: str
    timezone: str


def create_app(settings: Settings | None = None, frontend_dir: Path | None = None, language_model: LanguageModel | None = None) -> FastAPI:
    settings = settings or Settings()
    store = TaskStore(settings.database_path, settings.timezone)
    reminders = ReminderStore(store)
    scheduler = ReminderScheduler(reminders)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.initialize()
        worker = asyncio.create_task(scheduler.run()) if settings.reminders_enabled else None
        try:
            yield
        finally:
            scheduler.stop_event.set()
            if worker:
                await worker

    app = FastAPI(title="On the Desk AI Assistant", version="0.1.0", lifespan=lifespan)
    app.include_router(task_router(store))
    app.include_router(schedule_router)
    app.include_router(reminder_router(reminders, scheduler))
    app.include_router(assistant_router(Assistant(store, settings, language_model or LlamaCppModel(settings))))

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=app.version, timezone=settings.timezone)

    # API routes must precede the root static mount.
    dist = frontend_dir if frontend_dir is not None else PROJECT_ROOT / "frontend" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app
