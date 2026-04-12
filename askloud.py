#!/usr/bin/env ./venv/bin/python3
"""
Askloud — Cloud Inventory Chat Engine

Ask questions in plain English or search by name, ID, or IP address.

Modes:
  snapshot (default) — searches pre-fetched local inventory data (fast, no credentials needed)
  live               — runs real-time CLI queries against cloud providers

Usage:
  python3 askloud.py                          # interactive snapshot mode
  python3 askloud.py --live                   # interactive live mode
  python3 askloud.py web-01                   # direct search (no LLM)
  python3 askloud.py "list running instances" # natural language query
  python3 askloud.py --live "show dev ec2"    # live query

Requirements:
  pip install anthropic jmespath
  export ANTHROPIC_API_KEY=your_key_here   # needed for NL queries
  AWS credentials in ~/.aws/credentials    # needed for live mode
"""

import sys
import argparse

from askloud import CloudInventoryEngine
from askloud.engine import MODE_SNAPSHOT, MODE_LIVE


def main():
    parser = argparse.ArgumentParser(
        description="Askloud — Cloud Inventory Chat Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Start in live mode: fetch real-time data via CLI (requires cloud credentials)",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Optional query to run non-interactively",
    )
    args = parser.parse_args()

    mode  = MODE_LIVE if args.live else MODE_SNAPSHOT
    query = " ".join(args.query).strip() if args.query else ""

    # Inject query into sys.argv so engine.run() picks it up
    if query:
        sys.argv[1:] = [query]
    else:
        sys.argv[1:] = []

    CloudInventoryEngine(mode=mode).run()


if __name__ == "__main__":
    main()
