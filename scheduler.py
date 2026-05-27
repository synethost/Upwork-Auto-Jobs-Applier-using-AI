#!/usr/bin/env python3
"""
Scheduled job runner — executes main.py on a repeating interval.

Usage:
    python scheduler.py

Configuration (in .env):
    SCHEDULE_INTERVAL_HOURS=2   # how often to run (default: 2)
"""
import logging
import os
import subprocess
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

INTERVAL_HOURS = int(os.getenv("SCHEDULE_INTERVAL_HOURS", "2"))


def run_job_search():
    logging.info("Starting job search run...")
    result = subprocess.run([sys.executable, "main.py"])
    if result.returncode == 0:
        logging.info("Job search run completed successfully.")
    else:
        logging.error(f"Job search run failed (exit code {result.returncode}).")


if __name__ == "__main__":
    logging.info(f"Scheduler started — running every {INTERVAL_HOURS} hour(s).")
    logging.info("Running immediately on startup...")
    run_job_search()

    scheduler = BlockingScheduler()
    scheduler.add_job(run_job_search, "interval", hours=INTERVAL_HOURS)
    logging.info(f"Next run in {INTERVAL_HOURS}h. Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logging.info("Scheduler stopped.")
