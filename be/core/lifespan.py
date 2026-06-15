"""Application lifespan management"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from tasks.backup import backup_database_loop
from tasks.scan import daily_scan_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle"""
    print("=" * 50, flush=True)
    print("Application startup...", flush=True)
    print("=" * 50, flush=True)
    
    # Kick off a one-shot background scan for media files (images + comics +
    # videos). The scan also reconciles the `missing` flag (loader.work) —
    # files gone from disk get flagged (and hidden from the list API) rather
    # than deleted, so an unmounted external drive never loses its records.
    # The image bootstrap runs here too — it stats every folder, so doing it
    # synchronously would block startup on large/remote libraries.
    # After this startup scan, the daily_scan_loop task re-runs it at 2:00 AM
    # local time so the in-memory image store and comic/video tables stay fresh.
    from api.system import start_scan
    start_scan("all")
    print("Background scan started", flush=True)

    # Start background tasks and store them in app state
    tasks = []
    tasks.append(asyncio.create_task(backup_database_loop()))
    tasks.append(asyncio.create_task(daily_scan_loop()))
    
    # Store tasks in app state to prevent garbage collection
    app.state.background_tasks = tasks
    
    print(f"Started {len(tasks)} background tasks", flush=True)
    print("=" * 50, flush=True)
    
    yield
    
    print("=" * 50, flush=True)
    print("Application shutdown...", flush=True)
    print("=" * 50, flush=True)
    
    # Cancel all background tasks
    for task in tasks:
        task.cancel()
    
    # Wait for all tasks to complete cancellation
    await asyncio.gather(*tasks, return_exceptions=True)
    
    print("All background tasks stopped", flush=True)
    print("=" * 50)
