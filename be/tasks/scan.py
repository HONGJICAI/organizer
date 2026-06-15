"""Scheduled media scan task"""
import asyncio
import datetime

# Local clock hour at which the daily scan runs (24h). Images live only in an
# in-memory store (api/images.py) and never refresh on their own, and comic /
# video scans are too heavy to run continuously — so we reconcile everything
# once a day in the small hours instead.
SCAN_HOUR = 2


def _seconds_until(hour: int, now: datetime.datetime | None = None) -> float:
    """Seconds from `now` until the next occurrence of `hour:00` local time."""
    now = now or datetime.datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds()


async def daily_scan_loop():
    """Background task: run a full media scan every day at local SCAN_HOUR."""
    print(f"[Task] Daily scan task started (runs at {SCAN_HOUR:02d}:00 local time)", flush=True)
    from api.system import start_scan
    try:
        while True:
            await asyncio.sleep(_seconds_until(SCAN_HOUR))
            if start_scan("all"):
                print("[Task] Daily scan started", flush=True)
            else:
                print("[Task] Daily scan skipped — a scan is already running", flush=True)
    except asyncio.CancelledError:
        print("[Task] Daily scan task stopped", flush=True)
        raise
