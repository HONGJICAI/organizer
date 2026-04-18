"""Cleanup tasks for startup"""
import os
from sqlmodel import Session, select
from model import ComicEntity
import db


async def cleanup_missing_comics():
    """Startup task to check and remove comics with missing files"""
    print("Checking for missing comic files...")
    with Session(db.engine) as session:
        # Only check non-archived comics
        comics = session.exec(select(ComicEntity).where(not ComicEntity.archived)).all()
        removed_count = 0
        
        for comic in comics:
            if not os.path.exists(comic.path):
                print(f"Removing missing comic: {comic.id} - {comic.name} ({comic.path})")
                session.delete(comic)
                removed_count += 1
        
        if removed_count > 0:
            session.commit()
            print(f"Removed {removed_count} missing comic(s)")
        else:
            print("All comics have valid file paths")
