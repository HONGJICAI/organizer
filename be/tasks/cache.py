"""Cache processing tasks"""
import asyncio
from sqlmodel import Session, select
from model import ComicEntity
import db


# Cache for comic page access records: {comic_id: (timestamp, page)}
comic_access_cache = {}


async def process_comic_access_cache_loop():
    """Background task to process cached comic page access records"""
    print("[Task] Comic access cache processor started", flush=True)
    loop_count = 0
    try:
        while True:
            await asyncio.sleep(30)  # Run every 30 seconds
            loop_count += 1
            print(f"[Task] Running comic access cache processing... (cycle {loop_count})", flush=True)
            await process_comic_access_cache()
    except asyncio.CancelledError:
        print(f"[Task] Comic access cache processor stopped after {loop_count} cycles", flush=True)
        raise
    except Exception as e:
        print(f"[Task] Comic access cache processor error: {e}", flush=True)
        raise


async def process_comic_access_cache():
    """Process cached comic page access records and write to database"""    
    # Make a copy of current cache and clear the original (atomic operation)
    # Use .copy() and .clear() instead of reassignment to maintain the reference
    cache_to_process = comic_access_cache.copy()
    comic_access_cache.clear()
    
    if len(cache_to_process) == 0:
        print("[Task] No comic access records to process", flush=True)
        return
    
    # Process cached records
    print(f"[Task] Processing {len(cache_to_process)} comic access records", flush=True)
    with Session(db.engine) as session:
        for comic_id, (access_time, page) in cache_to_process.items():
            comic = session.exec(
                select(ComicEntity).where(ComicEntity.id == comic_id)
            ).one_or_none()
            
            if comic is not None:
                comic.lastViewedTime = access_time
                comic.lastViewedPosition = page
                session.add(comic)
            else:
                print(f"[Task] Comic {comic_id} not found", flush=True)
        
        session.commit()
    print("[Task] Comic access cache processed successfully", flush=True)
