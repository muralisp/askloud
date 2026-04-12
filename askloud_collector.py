#!/usr/bin/env ./venv/bin/python3
"""
Askloud Data Collector — Generic Multi-Cloud Agent

Modes:
  interactive / one-shot   Describe what to collect in plain English.
  --schedule               Run all due collections from config/collection_schedule.json.
  --schedule --dry-run     Show what would be collected without running any CLI commands.

Usage:
  python3 askloud_collector.py                           # interactive mode
  python3 askloud_collector.py "get ebs data for production us-east-1"
  python3 askloud_collector.py --schedule                # collect all due resources
  python3 askloud_collector.py --schedule --dry-run      # preview what is due

Requirements:
  pip install anthropic
  AWS:   aws CLI installed and configured  (aws configure)
  Azure: az  CLI installed and logged in   (az login)
  GCP:   gcloud CLI installed and authed   (gcloud auth login)
  export ANTHROPIC_API_KEY=your_key_here   (not needed for --schedule --dry-run)
"""

import sys
import argparse
from pathlib import Path

from askloud import CollectorAgent
from askloud.collector import _SCHEDULE_CONFIG


def main():
    parser = argparse.ArgumentParser(
        description="Askloud Data Collector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run all due collections from config/collection_schedule.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --schedule: show what is due without running CLI commands",
    )
    parser.add_argument(
        "--config",
        default=str(_SCHEDULE_CONFIG),
        metavar="PATH",
        help=f"Schedule config path (default: {_SCHEDULE_CONFIG})",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Natural language collection request (non-schedule mode)",
    )
    args = parser.parse_args()

    agent = CollectorAgent()

    if args.schedule:
        agent.run_scheduled(config_path=Path(args.config), dry_run=args.dry_run)
        return

    if args.query:
        sys.argv[1:] = args.query
    else:
        sys.argv[1:] = []

    agent.run()


if __name__ == "__main__":
    main()
