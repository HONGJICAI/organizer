"""Database backup tasks"""
import asyncio
import datetime
import os
import shutil


async def backup_database_loop():
    """Background task to backup database every 24 hours"""
    print("[Task] Database backup task started (runs every 24 hours)", flush=True)
    try:
        # First backup on startup (after 60 seconds)
        print("[Task] Waiting 60 seconds before initial backup...", flush=True)
        await asyncio.sleep(60)
        print("[Task] Running initial database backup...", flush=True)
        await backup_database()
        
        while True:
            await asyncio.sleep(86400)  # Run every 24 hours (86400 seconds)
            print("[Task] Running scheduled database backup...", flush=True)
            await backup_database()
    except asyncio.CancelledError:
        print("[Task] Database backup task stopped", flush=True)
        raise
    except Exception as e:
        print(f"[Task] Database backup task error: {e}", flush=True)
        raise


async def backup_database():
    """Backup the database to dbbackup folder only if it has been modified"""
    try:
        db_path = "prod.sqlite"
        if not os.path.exists(db_path):
            print(f"[Task] Database file {db_path} not found", flush=True)
            return
        
        # Get database last modified time
        db_mtime = os.path.getmtime(db_path)
        db_modified_time = datetime.datetime.fromtimestamp(db_mtime)
        
        # Create backup directory if it doesn't exist
        backup_dir = "dbbackup"
        os.makedirs(backup_dir, exist_ok=True)
        
        # Check the most recent backup
        backup_files = sorted([
            f for f in os.listdir(backup_dir) 
            if f.startswith("prod_") and f.endswith(".sqlite")
        ])
        
        if backup_files:
            latest_backup = backup_files[-1]
            latest_backup_path = os.path.join(backup_dir, latest_backup)
            latest_backup_mtime = os.path.getmtime(latest_backup_path)
            latest_backup_time = datetime.datetime.fromtimestamp(latest_backup_mtime)
            
            # Compare modification times (with 1 second tolerance for filesystem differences)
            time_diff = abs((db_mtime - latest_backup_mtime))
            
            if time_diff < 1:
                print(
                    f"[Task] Database backup skipped - no changes detected "
                    f"(DB: {db_modified_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                    f"Latest backup: {latest_backup_time.strftime('%Y-%m-%d %H:%M:%S')})",
                    flush=True
                )
                return
        
        # Generate backup filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"prod_{timestamp}.sqlite")
        
        # Copy database file (preserves modification time)
        shutil.copy2(db_path, backup_path)
        print(
            f"[Task] Database backed up successfully to {backup_path} "
            f"(DB modified: {db_modified_time.strftime('%Y-%m-%d %H:%M:%S')})",
            flush=True
        )
        
        # Keep only the last 7 backups to save space
        backup_files = sorted([
            f for f in os.listdir(backup_dir) 
            if f.startswith("prod_") and f.endswith(".sqlite")
        ])
        if len(backup_files) > 7:
            for old_backup in backup_files[:-7]:
                old_backup_path = os.path.join(backup_dir, old_backup)
                os.remove(old_backup_path)
                print(f"[Task] Removed old backup: {old_backup}", flush=True)
                
    except Exception as e:
        print(f"[Task] Failed to backup database: {e}", flush=True)
