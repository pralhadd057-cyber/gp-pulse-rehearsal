"""
Command-line entry point.

    python3 -m gp_pulse seed --n-gps 200        # generate + detect + brief, save to SQLite
    python3 -m gp_pulse seed --csv data.csv     # same, but from a real export
    python3 -m gp_pulse serve                   # start the API + dashboard
    python3 -m gp_pulse seed --n-gps 50 && python3 -m gp_pulse serve   # typical hackathon-day flow
"""

from __future__ import annotations

import argparse
import json
import time

from .api import serve
from .config import load_config
from .pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="gp_pulse")
    sub = parser.add_subparsers(dest="command", required=True)

    seed_p = sub.add_parser("seed", help="Run ingestion + detection + brief generation, save to SQLite")
    seed_p.add_argument("--n-gps", type=int, default=16, help="Number of synthetic GPs to generate (ignored if --csv given)")
    seed_p.add_argument("--csv", type=str, default=None, help="Path to a real referral CSV instead of synthetic data")
    seed_p.add_argument("--time", action="store_true", help="Print wall-clock time for the pipeline run")

    sub.add_parser("serve", help="Start the API server + dashboard")

    args = parser.parse_args()
    cfg = load_config()

    if args.command == "seed":
        start = time.perf_counter()
        summary = run_pipeline(cfg, csv_path=args.csv, n_gps=args.n_gps)
        elapsed = time.perf_counter() - start
        if args.time:
            summary["elapsed_seconds"] = round(elapsed, 3)
        print(json.dumps(summary, indent=2))
    elif args.command == "serve":
        serve(cfg)


if __name__ == "__main__":
    main()
