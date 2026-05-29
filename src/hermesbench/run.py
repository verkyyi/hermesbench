"""HermesBench — single consolidated benchmark runner.

    HERMES_RUN_LLM_EVALS=1 venv/bin/python -m hermesbench.run   # default single recipe
    venv/bin/python -m hermesbench.run --suite generic_context,mail_assistant
    venv/bin/python -m hermesbench.run --scenario calendar_daily_brief
    venv/bin/python -m hermesbench.run --full-bundle              # all use cases
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

from hermesbench import registry, report as report_mod


def _git_sha() -> str | None:
    try:
        repo = Path(__file__).resolve().parents[2]
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True, text=True, timeout=10,
        )
        sha = out.stdout.strip()
        if not sha:
            return None
        dirty = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=str(repo),
            capture_output=True, text=True, timeout=10,
        )
        return f"{sha}+dirty" if dirty.returncode else sha
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


def _target_selection() -> dict:
    raw_ui = (
        os.environ.get("HERMES_BENCH_TARGET_UI")
        or os.environ.get("HERMES_BENCH_TARGET_INTERFACE")
        or "cli"
    ).strip() or "cli"
    platform = (os.environ.get("HERMES_BENCH_TARGET_PLATFORM") or "").strip()
    ui = raw_ui
    if ui.startswith("platform:"):
        platform = platform or ui.split(":", 1)[1].strip()
        ui = "cli"
    elif ui not in {"cli", "command"}:
        platform = platform or ui
        ui = "cli"
    platform = platform or "cli"
    return {
        "ui": ui,
        "requested_ui": raw_ui,
        "profile": os.environ.get("HERMES_BENCH_TARGET_PROFILE") or "default",
        "platform": platform,
        "toolsets_override": os.environ.get("HERMES_BENCH_TARGET_TOOLSETS"),
        "skills_override": os.environ.get("HERMES_BENCH_TARGET_SKILLS"),
        "command_configured": bool(os.environ.get("HERMES_BENCH_TARGET_COMMAND")),
    }


def _hash_list(values: list[str]) -> str | None:
    if not values:
        return None
    payload = "\n".join(sorted(values)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _skill_inventory(home: str) -> dict:
    root = Path(home) / "skills"
    names: list[str] = []
    if root.exists():
        for skill_md in sorted(root.rglob("SKILL.md")):
            try:
                rel = skill_md.parent.relative_to(root).as_posix()
            except ValueError:
                continue
            if not rel.startswith("."):
                names.append(rel)
    return {
        "count": len(names),
        "hash": _hash_list(names),
        "sample": names[:20],
        "truncated": len(names) > 20,
    }


def _capability_surface(config: dict, *, home: str) -> dict:
    target = _target_selection()
    platform = target["platform"]
    platform_toolsets = config.get("platform_toolsets") if isinstance(config.get("platform_toolsets"), dict) else {}
    selected_platform_toolsets = platform_toolsets.get(platform)
    if not isinstance(selected_platform_toolsets, list):
        selected_platform_toolsets = []
    skills_cfg = config.get("skills") if isinstance(config.get("skills"), dict) else {}
    platform_disabled = skills_cfg.get("platform_disabled") if isinstance(skills_cfg.get("platform_disabled"), dict) else {}
    platform_allowed = skills_cfg.get("platform_allowed") if isinstance(skills_cfg.get("platform_allowed"), dict) else {}
    return {
        "target": target,
        "tools": {
            "root_toolsets": config.get("toolsets") if isinstance(config.get("toolsets"), list) else [],
            "platform_toolsets": selected_platform_toolsets,
            "platform_toolset_hash": _hash_list([str(x) for x in selected_platform_toolsets]),
        },
        "agent_skills": {
            "inventory": _skill_inventory(home),
            "globally_disabled": skills_cfg.get("disabled") if isinstance(skills_cfg.get("disabled"), list) else [],
            "platform_disabled": platform_disabled.get(platform, []),
            "platform_allowed": platform_allowed.get(platform, []),
        },
    }


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


def _redact_env_value(key: str, value: str) -> str:
    lowered = key.lower()
    if any(part in lowered for part in _SECRET_KEY_PARTS):
        return "<redacted>"
    if key == "HERMES_BENCH_TARGET_COMMAND":
        return "<configured>"
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
            k: _redact_env_value(k, v) for k, v in sorted(os.environ.items())
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
            snap["capability_surface"] = _capability_surface(data, home=home)
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
    ap.add_argument("--scenario", help="comma-separated scenario ids to restrict to")
    ap.add_argument("--full-bundle", action="store_true", help="run all registered suites; opt-in because it is slow")
    ap.add_argument("--trials", type=int, help="trials per prompt case")
    ap.add_argument("--case-concurrency", type=int, help="parallel prompt cases within each suite")
    ap.add_argument("--suite-concurrency", type=int, help="parallel suites")
    ap.add_argument(
        "--target-ui",
        "--target-interface",
        dest="target_ui",
        help=(
            "target user interface: cli (default), command, or a platform name "
            "such as telegram/weixin to simulate platform toolsets"
        ),
    )
    ap.add_argument("--target-platform", help="platform name for platform-scoped toolsets/skills")
    ap.add_argument("--target-profile", help="Hermes profile name to run as the target")
    ap.add_argument("--target-toolsets", help="comma-separated target toolsets override")
    ap.add_argument("--target-skills", help="comma-separated AgentSkills to preload")
    ap.add_argument(
        "--target-command",
        help=(
            "custom target UI command for --target-ui command; receives prompt "
            "on stdin unless argv contains {prompt}"
        ),
    )
    ap.add_argument(
        "--high-rate",
        action="store_true",
        help="fast preset: suite concurrency 6 and case concurrency 6 unless explicitly set",
    )
    ap.add_argument(
        "--suite-path",
        action="append",
        help="local suite JSON/YAML file or directory; may be repeated",
    )
    ap.add_argument("--list-suites", action="store_true", help="list registered suites and exit")
    ap.add_argument("--list-scenarios", action="store_true", help="list scenario recipe ids and exit")
    ap.add_argument("--validate", action="store_true", help="validate bundled and local suites and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--no-store", action="store_true", help="do not persist to the trend store")
    args = ap.parse_args(argv)

    from hermesbench import api

    if args.validate:
        summary = api.validate(suite_path=args.suite_path)
        print(
            f"ok: {summary['cases']} cases, "
            f"{summary['prompt_suites']} prompt suites, "
            f"{len(summary['local_suite_files'])} local suite files"
        )
        return 0

    if args.list_suites:
        for suite in api.list_suites(suite_path=args.suite_path):
            print(f"{suite['id']}\t{suite['mode']}\t{suite['interaction']}\t{suite['category']}")
        return 0

    if args.list_scenarios:
        for scenario in api.list_scenarios(suite_path=args.suite_path):
            print(f"{scenario['id']}\t{scenario['expectation']}\t{scenario['turn_count']}\t{scenario['suite_label']}")
        return 0

    previous = None
    report = api.run(
        suites=args.suite,
        scenarios=args.scenario,
        full_bundle=args.full_bundle,
        suite_path=args.suite_path,
        trials=args.trials,
        case_concurrency=args.case_concurrency,
        suite_concurrency=args.suite_concurrency,
        high_rate=args.high_rate,
        target_ui=args.target_ui,
        target_profile=args.target_profile,
        target_platform=args.target_platform,
        target_toolsets=args.target_toolsets,
        target_skills=args.target_skills,
        target_command=args.target_command,
        persist=not args.no_store,
        ignore_persist_errors=True,
    )
    if report.get("persist_warning"):
        print(f"warning: could not persist run: {report['persist_warning']}", file=sys.stderr)
    elif not args.no_store:
        previous = api.previous_run(report["run_id"])

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(report_mod.render(report, previous))

    return 0 if report.get("overall_score") is not None else 1


if __name__ == "__main__":
    sys.exit(main())
