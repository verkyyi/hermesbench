#!/usr/bin/env python3
"""Run one HermesBench scenario as a compact current-config baseline.

This script is intentionally thin: it uses the public hermesbench.api surface
so coding agents can reuse it without learning private runner internals.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hermesbench.api import run_scenario_baseline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one HermesBench scenario and print the compact baseline summary.",
    )
    parser.add_argument("scenario", help="Scenario id, for example followup_any_progress.")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--target-ui", default="cli")
    parser.add_argument("--target-profile", default="default")
    parser.add_argument("--target-platform")
    parser.add_argument("--target-toolsets")
    parser.add_argument("--target-skills")
    parser.add_argument("--target-command")
    parser.add_argument("--suite-path")
    parser.add_argument("--report-json", type=Path, help="Optional path for the full raw report JSON.")
    parser.add_argument("--summary-json", type=Path, help="Optional path for the compact summary JSON.")
    parser.add_argument("--no-llm-evals", action="store_true", help="Skip LLM-backed prompt evaluation.")
    parser.add_argument("--no-persist", action="store_true", help="Do not persist to the trend store.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_scenario_baseline(
        args.scenario,
        trials=args.trials,
        run_llm_evals=not args.no_llm_evals,
        persist=not args.no_persist,
        target_ui=args.target_ui,
        target_profile=args.target_profile,
        target_platform=args.target_platform,
        target_toolsets=args.target_toolsets,
        target_skills=args.target_skills,
        target_command=args.target_command,
        suite_path=args.suite_path,
        json_path=args.report_json,
    )
    summary = result["summary"]
    payload = json.dumps(summary, indent=2, sort_keys=True)
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
