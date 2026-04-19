"""Database backup tasks"""
import asyncio
import datetime
import os
import shutil

def _get_paths() -> tuple[str, str]:
    db_path = os.environ.get("DB_PATH", "prod.sqlite")
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
    return db_path, backup_dir


async def backup_database_loop():
    """Background task to backup database every 24 hours"""
    print("[Task] Database backup task started (runs every 24 hours)", flush=True)
    try:
        await asyncio.sleep(60)
        await backup_database()
        while True:
            await asyncio.sleep(86400)
            await backup_database()
    except asyncio.CancelledError:
        print("[Task] Database backup task stopped", flush=True)
        raise
    except Exception as e:
        print(f"[Task] Database backup task error: {e}", flush=True)
        raise


async def backup_database():
    """Backup the database to the backups subfolder only if it has been modified"""
    try:
        db_path, backup_dir = _get_paths()

        if not os.path.exists(db_path):
            print(f"[Task] Database file {db_path} not found", flush=True)
            return

        db_mtime = os.path.getmtime(db_path)
        db_modified_time = datetime.datetime.fromtimestamp(db_mtime)

        os.makedirs(backup_dir, exist_ok=True)

        db_stem = os.path.splitext(os.path.basename(db_path))[0]
        backup_ext = os.path.splitext(db_path)[1] or ".db"
        backup_files = sorted([
            f for f in os.listdir(backup_dir)
            if f.startswith(f"{db_stem}_") and f.endswith(backup_ext)
        ])

        if backup_files:
            latest_path = os.path.join(backup_dir, backup_files[-1])
            if abs(db_mtime - os.path.getmtime(latest_path)) < 1:
                print(
                    f"[Task] Backup skipped — no changes "
                    f"(DB: {db_modified_time.strftime('%Y-%m-%d %H:%M:%S')})",
                    flush=True,
                )
                return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"{db_stem}_{timestamp}{backup_ext}")
        shutil.copy2(db_path, backup_path)
        print(f"[Task] Backed up to {backup_path}", flush=True)

        # Keep last 7 backups
        backup_files = sorted([
            f for f in os.listdir(backup_dir)
            if f.startswith(f"{db_stem}_") and f.endswith(backup_ext)
        ])
        for old in backup_files[:-7]:
            os.remove(os.path.join(backup_dir, old))
            print(f"[Task] Removed old backup: {old}", flush=True)

    except Exception as e:
        print(f"[Task] Failed to backup database: {e}", flush=True)
