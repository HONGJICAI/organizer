"""Application lifespan management"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from tasks.cleanup import cleanup_missing_comics
from tasks.cache import process_comic_access_cache_loop
from tasks.backup import backup_database_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle"""
    print("=" * 50, flush=True)
    print("Application startup...", flush=True)
    print("=" * 50, flush=True)
    
    # Run startup tasks
    await cleanup_missing_comics()
    
    # Start background tasks and store them in app state
    tasks = []
    task1 = asyncio.create_task(process_comic_access_cache_loop())
    task2 = asyncio.create_task(backup_database_loop())
    # task3 = asyncio.create_task(process_view_history_loop())
    
    tasks.append(task1)
    tasks.append(task2)
    # tasks.append(task3)
    
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
