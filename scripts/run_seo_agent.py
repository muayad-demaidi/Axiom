#!/usr/bin/env python3
"""CLI entry point for the weekly SEO/GEO automation agent.

Configure as a Replit Scheduled Deployment:
    Command:  python scripts/run_seo_agent.py
    Schedule: 0 8 * * 1   (Mondays 08:00 UTC)

Manual flags:
    --dry-run      Generate + validate but do not write drafts or send email.
    --print-config Print the resolved config JSON and exit.
"""

import argparse
import json
import sys
from pathlib import Path

# Make the project root importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seo_agent.config import load_config, env_override
from seo_agent.runner import run_weekly_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the weekly SEO/GEO cycle.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not persist drafts or send email.")
    parser.add_argument("--print-config", action="store_true",
                        help="Print the resolved config and exit.")
    args = parser.parse_args()

    cfg = env_override(load_config())
    if args.print_config:
        print(json.dumps(cfg.to_dict(), indent=2))
        return 0

    summary = run_weekly_cycle(cfg=cfg, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
