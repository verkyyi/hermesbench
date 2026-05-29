#!/usr/bin/env python3
"""Generate public task catalog, traces, and static site pages."""

from __future__ import annotations

import json
from pathlib import Path

from hermesbench.public_artifacts import build_public_artifacts


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    summary = build_public_artifacts(repo_root)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
