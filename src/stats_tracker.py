"""
Stats tracking and display for Upwork Auto-Applier.

Usage:
    python -m src.stats_tracker          # print summary
    python stats.py                      # convenience alias (root level)
"""
import json
import os
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

STATS_FILE = "./files/stats.json"


def record_run(job_title: str, scraped: int, applied_jobs: list):
    """Append one run record to stats.json."""
    record = {
        "timestamp": datetime.now().isoformat(),
        "job_title": job_title,
        "scraped": scraped,
        "applied": len(applied_jobs),
        "jobs": [
            {
                "title": j.get("title", ""),
                "link": j.get("link", ""),
                "score": j.get("score", 0),
                "submitted": j.get("submitted", False),
            }
            for j in applied_jobs
        ],
    }

    try:
        with open(STATS_FILE, "r") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []

    history.append(record)

    with open(STATS_FILE, "w") as f:
        json.dump(history, f, indent=2)


def print_stats():
    """Print an overview of all recorded runs."""
    try:
        with open(STATS_FILE, "r") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("No stats yet — run main.py first.")
        return

    total_runs = len(history)
    total_scraped = sum(r["scraped"] for r in history)
    total_applied = sum(r["applied"] for r in history)
    total_submitted = sum(
        sum(1 for j in r["jobs"] if j.get("submitted")) for r in history
    )

    print(Fore.BLUE + "\n========== Upwork Auto-Applier Stats ==========\n" + Style.RESET_ALL)
    print(f"  Total runs       {total_runs}")
    print(f"  Total scraped    {total_scraped}")
    print(f"  Total applied    {total_applied}")
    print(f"  Total submitted  {total_submitted}")

    print(Fore.GREEN + "\n  Recent runs (last 10):\n" + Style.RESET_ALL)
    header = f"  {'Timestamp':<20} {'Search':<28} {'Scraped':>7} {'Applied':>7} {'Submitted':>9}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for run in history[-10:]:
        ts = run["timestamp"][:16].replace("T", " ")
        submitted = sum(1 for j in run["jobs"] if j.get("submitted"))
        print(
            f"  {ts:<20} {run['job_title']:<28} {run['scraped']:>7} "
            f"{run['applied']:>7} {submitted:>9}"
        )

    # Top scoring jobs across all runs
    all_jobs = [
        j for r in history for j in r["jobs"] if j.get("score", 0) >= 9
    ]
    if all_jobs:
        print(Fore.YELLOW + f"\n  Top matches (score 9-10) — {len(all_jobs)} total:\n" + Style.RESET_ALL)
        for j in all_jobs[-5:]:
            submitted = "submitted" if j.get("submitted") else "saved"
            print(f"  [{j['score']}/10] {j['title'][:55]}  ({submitted})")

    print()


if __name__ == "__main__":
    print_stats()
