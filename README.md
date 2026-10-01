# On the Desk AI Assistant

A personal offline task assistant, developed on Windows for eventual deployment to a Raspberry Pi 5, 5-inch touchscreen, and AI HAT+ 2.

## Current milestone: task management

Includes FastAPI, persistent SQLite task management, one-time/daily/weekly schedules, completion history, a TypeScript/Vite starter screen, local configuration, and Windows scripts. The task dashboard, reminder delivery, voice, and language models are not implemented yet. No cloud service or API key is required. See [the task API guide](docs/task-management.md) for request examples and schedule behavior.

## Windows setup

Prerequisites: Python 3.11+ (`python`, preferably 3.12), Node.js 22.12+, pnpm 11 (`npm install --global pnpm@11`), Git, and PowerShell. Dependency installation requires internet.

From the repository root on `feature/Initial_version_v1`:

```powershell
.\scripts\setup.ps1
.\scripts\start.ps1
```

Open http://127.0.0.1:8000. Stop with Ctrl+C. API documentation: http://127.0.0.1:8000/docs. Startup serves the built frontend and API together and needs no downloads.

If tools are not on PATH, pass their executable paths:

```powershell
.\scripts\setup.ps1 -PythonCommand 'C:\path\to\python.exe' -PnpmCommand 'C:\path\to\pnpm.cmd'
```

Setup creates `.venv`, installs dependencies, copies `.env.example` only when `.env` is missing, and builds the frontend. Keep this source checkout in place: the editable Python installation serves `frontend/dist` from it.

## Configuration

Edit root `.env`; environment variables take precedence. Restart processes after changes.

| Setting | Default | Purpose |
| --- | --- | --- |
| `OTD_HOST` | `127.0.0.1` | Loopback address; LAN access is disabled. |
| `OTD_PORT` | `8000` | API and built frontend port. |
| `OTD_TIMEZONE` | `America/Chicago` | IANA time zone for future task scheduling. |
| `OTD_DATABASE_PATH` | `data/tasks.sqlite3` | SQLite file; relative paths resolve from the repository root. |

Local configuration, databases, recordings, downloaded models, environments, and build output are ignored by Git. No secrets belong in source control.

## Development and verification

With the backend running, use a second terminal for frontend hot reload:

```powershell
pnpm --dir frontend dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` using the root `.env` configuration. Restart the backend after Python changes. Rebuild frontend edits before using the single-service launcher.

```powershell
.\.venv\Scripts\python.exe -m pytest
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

Frontend dependency versions are locked in `frontend/pnpm-lock.yaml`. Python dependency ranges are in `pyproject.toml`; a deployment lock will be added during Pi packaging.

## Structure

```text
backend/src/otd_assistant/   Configuration, application factory, launcher
backend/src/otd_assistant/tasks/  Task API, SQLite repository, recurrence calculations
backend/tests/             API, persistence, validation, and recurrence checks
docs/                      Task API usage and behavior
frontend/src/              TypeScript and CSS
scripts/                   Windows setup and startup
.env.example               Non-secret configuration template
pyproject.toml             Python dependencies and package metadata
```

## Raspberry Pi target

The application and frontend are shared across platforms. Pi installation scripts, Hailo adapters, kiosk startup, and hardware validation belong to the deployment milestone. Install native dependencies on the Pi; do not copy Windows `.venv` or `node_modules`. Future AI adapters will keep Windows and Hailo runtimes separate from task logic.
