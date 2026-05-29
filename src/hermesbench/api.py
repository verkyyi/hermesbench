"""Programmatic HermesBench API.

This module is the stable surface for coding agents and notebooks. It mirrors
the CLI without requiring a user to touch shell flags directly.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from importlib import resources
from pathlib import Path
from typing import Iterable, Iterator

from hermesbench import registry, run as run_mod, store, usecases

DEFAULT_SCENARIO_ID = "calendar_daily_brief"


def _csv(values: str | Iterable[str] | None) -> str | None:
    if values is None:
        return None
    if isinstance(values, str):
        return values
    return ",".join(str(v).strip() for v in values if str(v).strip())


def _suite_path_value(suite_path: str | Path | Iterable[str | Path] | None) -> str | None:
    if suite_path is None:
        return None
    if isinstance(suite_path, (str, Path)):
        return str(suite_path)
    return os.pathsep.join(str(p) for p in suite_path)


@contextmanager
def _patched_env(updates: dict[str, str | None]) -> Iterator[None]:
    old: dict[str, str | None] = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                continue
            os.environ[key] = str(value)
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _runtime_env(
    *,
    suite_path: str | Path | Iterable[str | Path] | None = None,
    trials: int | None = None,
    case_concurrency: int | None = None,
    suite_concurrency: int | None = None,
    high_rate: bool = False,
    run_llm_evals: bool | None = None,
    target_ui: str | None = None,
    target_profile: str | None = None,
    target_platform: str | None = None,
    target_toolsets: str | Iterable[str] | None = None,
    target_skills: str | Iterable[str] | None = None,
    target_command: str | None = None,
) -> dict[str, str | None]:
    env: dict[str, str | None] = {}
    suite_path_str = _suite_path_value(suite_path)
    if suite_path_str:
        existing = os.environ.get("HERMESBENCH_SUITE_PATH")
        parts = [*(existing.split(os.pathsep) if existing else []), suite_path_str]
        env["HERMESBENCH_SUITE_PATH"] = os.pathsep.join(p for p in parts if p)
    if run_llm_evals is not None:
        env["HERMES_RUN_LLM_EVALS"] = "1" if run_llm_evals else ""
    if high_rate:
        env["HERMES_BENCH_SUITE_CONCURRENCY"] = str(suite_concurrency or 6)
        env["HERMES_BENCH_CONCURRENCY"] = str(case_concurrency or 6)
        env["HERMES_BENCH_HIGH_RATE"] = "1"
    if trials is not None:
        env["HERMES_BENCH_TRIALS"] = str(max(1, int(trials)))
    if case_concurrency is not None:
        env["HERMES_BENCH_CONCURRENCY"] = str(max(1, int(case_concurrency)))
    if suite_concurrency is not None:
        env["HERMES_BENCH_SUITE_CONCURRENCY"] = str(max(1, int(suite_concurrency)))
    if target_ui:
        env["HERMES_BENCH_TARGET_UI"] = target_ui
    if target_profile:
        env["HERMES_BENCH_TARGET_PROFILE"] = target_profile
    if target_platform:
        env["HERMES_BENCH_TARGET_PLATFORM"] = target_platform
    if target_toolsets is not None:
        env["HERMES_BENCH_TARGET_TOOLSETS"] = _csv(target_toolsets)
    if target_skills is not None:
        env["HERMES_BENCH_TARGET_SKILLS"] = _csv(target_skills)
    if target_command:
        env["HERMES_BENCH_TARGET_COMMAND"] = target_command
    return env


def _refresh_loaded_suite_knobs() -> None:
    """Keep already-imported suite module globals in sync with env overrides."""
    try:
        from hermesbench.suites import usecases as suite_mod

        suite_mod.TRIALS = int(os.environ.get("HERMES_BENCH_TRIALS", str(suite_mod.TRIALS)))
        suite_mod.CONCURRENCY = int(os.environ.get("HERMES_BENCH_CONCURRENCY", str(suite_mod.CONCURRENCY)))
    except Exception:
        pass


def list_suites(
    *,
    suite_path: str | Path | Iterable[str | Path] | None = None,
) -> list[dict]:
    """Return registered suite metadata as JSON-serializable dictionaries."""
    with _patched_env(_runtime_env(suite_path=suite_path)):
        return [
            {
                "id": suite.id,
                "category": suite.category,
                "mode": suite.mode,
                "interaction": suite.interaction,
                "weight": suite.weight,
                "summary": suite.summary,
            }
            for suite in registry.all_suites()
        ]


def list_scenarios(
    *,
    suite_path: str | Path | Iterable[str | Path] | None = None,
) -> list[dict]:
    """Return scenario metadata for focused single-scenario benchmark runs."""
    with _patched_env(_runtime_env(suite_path=suite_path)):
        return [
            {
                "id": case["id"],
                "title": case.get("title") or case["id"].replace("_", " ").title(),
                "category_id": case["category"],
                "category_label": usecases.category_label(str(case["category"])),
                "goal": case.get("goal") or case.get("notes") or case.get("initial_prompt") or case.get("prompt") or "",
                "initial_prompt": (usecases.case_turns(case)[0] or {}).get("prompt", ""),
                "success_criteria": case.get("success_criteria") or case.get("success") or [],
                "safety_criteria": case.get("safety_criteria") or case.get("safety") or [],
                # Backward-compatible aliases.
                "suite_id": case["category"],
                "suite_label": usecases.category_label(str(case["category"])),
                "expectation": case.get("expectation"),
                "turn_count": len(usecases.case_turns(case)),
                "summary": case.get("notes") or case.get("prompt") or "",
            }
            for case in usecases.all_cases()
        ]


def validate(
    *,
    suite_path: str | Path | Iterable[str | Path] | None = None,
) -> dict:
    """Validate bundled/local suites and return a compact summary."""
    with _patched_env(_runtime_env(suite_path=suite_path)):
        usecases.validate_dataset()
        return {
            "ok": True,
            "cases": len(usecases.all_cases()),
            "prompt_suites": len(usecases.categories()),
            "local_suite_files": [str(p) for p in usecases.local_suite_files()],
        }


def run(
    *,
    suites: str | Iterable[str] | None = None,
    scenarios: str | Iterable[str] | None = None,
    suite_path: str | Path | Iterable[str | Path] | None = None,
    trials: int | None = None,
    case_concurrency: int | None = None,
    suite_concurrency: int | None = None,
    high_rate: bool = False,
    run_llm_evals: bool | None = None,
    target_ui: str | None = None,
    target_profile: str | None = None,
    target_platform: str | None = None,
    target_toolsets: str | Iterable[str] | None = None,
    target_skills: str | Iterable[str] | None = None,
    target_command: str | None = None,
    full_bundle: bool = False,
    persist: bool = True,
    ignore_persist_errors: bool = False,
    json_path: str | Path | None = None,
) -> dict:
    """Run HermesBench and return the report dictionary.

    This is the API coding agents should call instead of asking the user to run
    shell commands. By default it runs one representative scenario recipe to
    keep the user-facing path fast; set ``full_bundle=True`` or pass explicit
    ``suites`` to opt into broader runs. Set ``persist=False`` for exploratory
    runs.
    """
    suite_ids = [s for s in (_csv(suites) or "").split(",") if s]
    scenario_ids = [s for s in (_csv(scenarios) or "").split(",") if s]
    explicit_ids = [*suite_ids, *scenario_ids]
    selected_ids = explicit_ids or (None if full_bundle else [DEFAULT_SCENARIO_ID])
    env = _runtime_env(
        suite_path=suite_path,
        trials=trials,
        case_concurrency=case_concurrency,
        suite_concurrency=suite_concurrency,
        high_rate=high_rate,
        run_llm_evals=run_llm_evals,
        target_ui=target_ui,
        target_profile=target_profile,
        target_platform=target_platform,
        target_toolsets=target_toolsets,
        target_skills=target_skills,
        target_command=target_command,
    )
    with _patched_env(env):
        _refresh_loaded_suite_knobs()
        report = run_mod.run_benchmark(ids=selected_ids)
        report["selection"] = {
            "default_scenario_id": DEFAULT_SCENARIO_ID,
            "full_bundle": bool(full_bundle and not explicit_ids),
            "requested_suites": suite_ids,
            "requested_scenarios": scenario_ids,
            "effective_ids": selected_ids,
        }
        if persist:
            try:
                store.save_run(report)
            except Exception as exc:
                if not ignore_persist_errors:
                    raise
                report["persist_warning"] = f"{type(exc).__name__}: {exc}"[:400]
        if json_path:
            path = Path(json_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report


def run_scenario(
    scenario_id: str,
    **kwargs,
) -> dict:
    """Run one scenario id and return a normal HermesBench report."""
    return run(scenarios=[scenario_id], **kwargs)


def recent_runs(*, limit: int = 30, db_path: str | Path | None = None) -> list[dict]:
    """Return recent persisted runs from the HermesBench store."""
    return store.recent_runs(limit=limit, db_path=Path(db_path) if db_path else None)


def previous_run(run_id: str, *, db_path: str | Path | None = None) -> dict | None:
    """Return the persisted run immediately preceding ``run_id``."""
    return store.previous_run(run_id, db_path=Path(db_path) if db_path else None)


def agent_skill_path() -> Path:
    """Return the packaged HermesBench AgentSkill path.

    Coding agents should load this skill first, then use this API. The top-level
    ``agent-skills/hermesbench`` copy exists for repository browsing; this
    packaged copy is what ships with the Python package.
    """
    return Path(str(resources.files("hermesbench").joinpath("agent_skills/hermesbench/SKILL.md")))


def agent_skill_text() -> str:
    """Return the packaged HermesBench AgentSkill content."""
    return agent_skill_path().read_text(encoding="utf-8")


def build_public_artifacts(repo_root: str | Path | None = None) -> dict:
    """Generate recipe catalog, leaderboard evidence, and static website pages.

    Coding agents can call this after adding cases or baseline directories so
    the repo and website transparency surfaces stay in sync.
    """
    from hermesbench.public_artifacts import build_public_artifacts as _build

    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
    return _build(root)
