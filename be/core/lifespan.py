"""Application lifespan management"""
import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI

from tasks.backup import backup_database_loop


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
    from api.system import _run_scan
    threading.Thread(target=_run_scan, args=("all",), daemon=True).start()
    print("Background scan started", flush=True)
    
    # Start background tasks and store them in app state
    tasks = []
    task1 = asyncio.create_task(backup_database_loop())

    tasks.append(task1)
    
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
