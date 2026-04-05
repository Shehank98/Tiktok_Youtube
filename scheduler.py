"""
APScheduler wrapper. Called by app.py to start/restart scheduled jobs.
"""
import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("scheduler")

_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def _get_or_create() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.start()
        logger.info("Scheduler started (UTC timezone)")
    return _scheduler


def reschedule(upload_times: str, pipeline_fn):
    """
    Replace all existing cron jobs with new ones based on upload_times.
    upload_times: comma-separated "HH:MM" strings, e.g. "08:00,14:00,20:00"
    pipeline_fn: callable with no arguments (the pipeline.run_pipeline function)
    """
    with _lock:
        sched = _get_or_create()
        sched.remove_all_jobs()

        times = [t.strip() for t in upload_times.split(",") if t.strip()]
        if not times:
            logger.warning("No upload times configured — no jobs scheduled")
            return

        for time_str in times:
            try:
                hour, minute = time_str.split(":")
                trigger = CronTrigger(hour=int(hour), minute=int(minute))
                sched.add_job(pipeline_fn, trigger, id=f"pipeline_{time_str}",
                              replace_existing=True, misfire_grace_time=300)
                logger.info("Scheduled pipeline at %s UTC", time_str)
            except Exception as e:
                logger.error("Bad time format '%s': %s", time_str, e)


def get_next_run_times() -> list:
    """Return list of next fire times as ISO strings."""
    with _lock:
        if _scheduler is None:
            return []
        result = []
        for job in _scheduler.get_jobs():
            nf = job.next_run_time
            if nf:
                result.append(nf.isoformat())
        return sorted(result)


def shutdown():
    with _lock:
        global _scheduler
        if _scheduler:
            _scheduler.shutdown(wait=False)
            _scheduler = None
