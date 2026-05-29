"""HermesBench — single consolidated benchmark runner.

    HERMES_RUN_LLM_EVALS=1 venv/bin/python -m hermesbench.run   # all use cases
    venv/bin/python -m hermesbench.run --suite runtime_config,ambiguous_followup
    venv/bin/python -m hermesbench.run --json          # machine-readable
    venv/bin/python -m hermesbench.run --no-store      # don't persist

Runs every registered suite. Prompt suites drive a real agent and self-skip when
HERMES_RUN_LLM_EVALS is unset; deterministic runtime-policy suites can still
run without model credentials. The benchmark's product-facing verdict is the
score itself: reliability failures are folded into the score rather than
reported as a separate pass/fail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from hermesbench import registry, report as report_mod, store, usecases


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[2]),
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _model_id() -> str | None:
    # Best-effort, pinned for the trend; never fail the run over it.
    env = os.environ.get("HERMES_BENCH_MODEL_ID")
    if env:
        return env
    try:
        import yaml  # type: ignore

        home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
        cfg = Path(home) / "config.yaml"
        if cfg.exists():
            data = yaml.safe_load(cfg.read_text()) or {}
            model = data.get("model") or (data.get("models") or {}).get("main")
            if isinstance(model, dict):  # e.g. {default: ..., provider: ...}
                return model.get("default") or json.dumps(model, sort_keys=True)
            return str(model) if model is not None else None
    except Exception:
        pass
    return None


def _profile_hash() -> str | None:
    try:
        home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
        cfg = Path(home) / "config.yaml"
        if cfg.exists():
            return hashlib.sha256(cfg.read_bytes()).hexdigest()
    except Exception:
        pass
    return None


_SNAPSHOT_CONFIG_KEYS = {
    "api_mode",
    "disabled_toolsets",
    "enabled_toolsets",
    "gateway",
    "kanban",
    "memory",
    "model",
    "models",
    "orchestrator",
    "platforms",
    "plugins",
    "provider",
    "routing",
    "service_tier",
    "skills",
    "tools",
    "toolsets",
}
_SECRET_KEY_PARTS = (
    "api_key", "apikey", "auth", "bearer", "cookie", "credential", "key",
    "password", "secret", "session", "token",
)


def _redact(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key = str(k)
            if any(part in key.lower() for part in _SECRET_KEY_PARTS):
                out[key] = "<redacted>"
            else:
                out[key] = _redact(v)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _profile_snapshot() -> dict:
    """Best-effort redacted snapshot of benchmark-relevant profile settings."""
    home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    cfg = Path(home) / "config.yaml"
    include_paths = os.environ.get("HERMESBENCH_INCLUDE_PATHS") in {"1", "true", "yes", "on"}
    snap = {
        "version": 1,
        "hermes_home": home if include_paths else "<hermes_home>",
        "hermes_home_hash": hashlib.sha256(str(Path(home).expanduser()).encode()).hexdigest()[:16],
        "config_path": str(cfg) if include_paths else "<hermes_home>/config.yaml",
        "config_hash": _profile_hash(),
        "bench_env": {
            k: v for k, v in sorted(os.environ.items())
            if k.startswith("HERMES_BENCH_") or k == "HERMES_RUN_LLM_EVALS"
        },
    }
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(cfg.read_text()) if cfg.exists() else {}
        if isinstance(data, dict):
            selected = {
                k: data[k]
                for k in sorted(_SNAPSHOT_CONFIG_KEYS)
                if k in data
            }
            snap["config"] = _redact(selected)
            snap["execution_surface"] = _execution_surface(data)
    except Exception as exc:
        snap["config_error"] = f"{type(exc).__name__}: {exc}"[:200]
    return snap


def _execution_surface(config: dict) -> dict:
    """Classify the Hermes execution surface exposed to the benchmark."""
    toolsets = config.get("toolsets") if isinstance(config.get("toolsets"), list) else []
    plugins = config.get("plugins") if isinstance(config.get("plugins"), dict) else {}
    enabled_plugins = plugins.get("enabled") if isinstance(plugins.get("enabled"), list) else []
    kanban_enabled = (
        "kanban" in toolsets
        or isinstance(config.get("kanban"), dict)
        or "kanban-orchestrator-routing" in enabled_plugins
    )
    if kanban_enabled:
        surface_id = "kanban_delegation"
        label = "Kanban delegation"
        comparison_role = "Kanban-enabled baseline"
    else:
        surface_id = "direct"
        label = "Direct/no-kanban"
        comparison_role = "No-kanban baseline"
    return {
        "id": surface_id,
        "label": label,
        "comparison_role": comparison_role,
        "kanban_enabled": kanban_enabled,
        "prompt_case_contract": "framework_agnostic",
        "notes": (
            "Bundled prompt use cases are intended to run on either surface. "
            "Kanban-enabled configurations may perform better on delegation, "
            "progress, and long-work closure behavior; explicit multi-profile "
            "checks live in opt-in runtime suites."
        ),
    }


def _execute(suite: registry.Suite) -> dict:
    base = {
        "id": suite.id, "category": suite.category, "mode": suite.mode,
        "interaction": getattr(suite, "interaction", registry.SINGLE_TURN),
        "weight": suite.weight, "summary": suite.summary,
        "score": None, "skipped": False,
        "skip_reason": None, "error": None, "duration_s": 0.0, "metrics": {},
    }
    # Suites that need a model self-skip when HERMES_RUN_LLM_EVALS is unset
    # (see their run()), so there's no gating to do here.
    t0 = time.perf_counter()
    try:
        out = suite.load()()
    except Exception as exc:  # a broken suite must not sink the whole run
        base["error"] = f"{type(exc).__name__}: {exc}"[:400]
        base["score"] = 0.0
        base["metrics"] = {"axis_scores": {"stability": 0.0}}
        base["duration_s"] = round(time.perf_counter() - t0, 3)
        return base
    base["duration_s"] = round(time.perf_counter() - t0, 3)

    if out.get("skipped"):
        base.update(skipped=True, skip_reason=out.get("skip_reason"))
        return base
    base["score"] = out.get("score")
    base["metrics"] = out.get("metrics") or {}
    return base


def _suite_concurrency() -> int:
    try:
        return max(1, int(os.environ.get("HERMES_BENCH_SUITE_CONCURRENCY", "1")))
    except ValueError:
        return 1


def _execute_suites(suites: list[registry.Suite]) -> list[dict]:
    workers = min(len(suites) or 1, _suite_concurrency())
    if workers <= 1:
        return [_execute(s) for s in suites]

    results: list[dict | None] = [None] * len(suites)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_execute, suite): idx for idx, suite in enumerate(suites)}
        for fut in as_completed(futs):
            results[futs[fut]] = fut.result()
    return [r for r in results if r is not None]


def run_benchmark(*, ids: list[str] | None = None) -> dict:
    suites = registry.select(ids=ids)

    results = _execute_suites(suites)

    ran = [r for r in results if not r["skipped"] and r["score"] is not None]
    if ran:
        w = sum(r["weight"] for r in ran) or 1.0
        overall = round(sum(r["weight"] * r["score"] for r in ran) / w, 2)
    else:
        overall = None

    now = datetime.now(timezone.utc)
    return {
        "run_id": "hb-" + now.strftime("%Y%m%dT%H%M%SZ"),
        "ts": now.isoformat(),
        "overall_score": overall,
        "suites_ran": len(ran),
        "harness": {
            "git_sha": _git_sha(),
            "model_id": _model_id(),
            "profile_hash": _profile_hash(),
            "profile_snapshot": _profile_snapshot(),
        },
        "suites": results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hermesbench")
    ap.add_argument("--suite", help="comma-separated suite ids to restrict to")
    ap.add_argument("--trials", type=int, help="trials per prompt case")
    ap.add_argument("--case-concurrency", type=int, help="parallel prompt cases within each suite")
    ap.add_argument("--suite-concurrency", type=int, help="parallel suites")
    ap.add_argument(
        "--driver",
        choices=("codex", "static"),
        help="evaluator-side driver for prompt suites; default is codex",
    )
    ap.add_argument(
        "--high-rate",
        action="store_true",
        help="fast preset: suite concurrency 4 and case concurrency 8 unless explicitly set",
    )
    ap.add_argument(
        "--suite-path",
        action="append",
        help="local suite JSON/YAML file or directory; may be repeated",
    )
    ap.add_argument("--list-suites", action="store_true", help="list registered suites and exit")
    ap.add_argument("--validate", action="store_true", help="validate bundled and local suites and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--no-store", action="store_true", help="do not persist to the trend store")
    args = ap.parse_args(argv)

    if args.high_rate:
        os.environ.setdefault("HERMES_BENCH_SUITE_CONCURRENCY", "4")
        os.environ.setdefault("HERMES_BENCH_CONCURRENCY", "8")
        os.environ["HERMES_BENCH_HIGH_RATE"] = "1"
    if args.trials is not None:
        os.environ["HERMES_BENCH_TRIALS"] = str(max(1, args.trials))
    if args.driver:
        os.environ["HERMES_BENCH_DRIVER"] = args.driver
    if args.case_concurrency is not None:
        os.environ["HERMES_BENCH_CONCURRENCY"] = str(max(1, args.case_concurrency))
    if args.suite_concurrency is not None:
        os.environ["HERMES_BENCH_SUITE_CONCURRENCY"] = str(max(1, args.suite_concurrency))

    if args.suite_path:
        existing = os.environ.get("HERMESBENCH_SUITE_PATH")
        parts = [*(existing.split(os.pathsep) if existing else []), *args.suite_path]
        os.environ["HERMESBENCH_SUITE_PATH"] = os.pathsep.join(p for p in parts if p)

    if args.validate:
        usecases.validate_dataset()
        print(
            f"ok: {len(usecases.all_cases())} cases, "
            f"{len(usecases.categories())} prompt suites, "
            f"{len(usecases.local_suite_files())} local suite files"
        )
        return 0

    if args.list_suites:
        for suite in registry.all_suites():
            print(f"{suite.id}\t{suite.mode}\t{suite.interaction}\t{suite.category}")
        return 0

    ids = [s for s in (args.suite or "").split(",") if s] or None
    report = run_benchmark(ids=ids)

    previous = None
    if not args.no_store:
        try:
            store.save_run(report)
            previous = store.previous_run(report["run_id"])
        except Exception as exc:
            print(f"warning: could not persist run: {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(report_mod.render(report, previous))

    return 0 if report.get("overall_score") is not None else 1


if __name__ == "__main__":
    sys.exit(main())
