from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from hermesbench import api, checks, drivers, harness, public_artifacts, registry, run as run_mod, scenarios, scoring, targets, usecases
from hermesbench import agentic_bridge
from hermesbench.suites import gateway as gateway_mod
from hermesbench.suites import usecases as suite_mod


def test_bundled_dataset_is_balanced(monkeypatch):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    monkeypatch.delenv("HERMES_BENCH_SUITE_PATH", raising=False)
    usecases.validate_dataset()
    categories = usecases.categories()
    assert len(categories) == 12
    assert len(usecases.all_cases()) == 48
    assert all(len(usecases.cases_for(c)) == usecases.CASES_PER_CATEGORY for c in categories)
    assert usecases.case_by_id("dev_alert_inbox_triage") is not None
    assert not any("ainbox" in json.dumps(case).lower() for case in usecases.all_cases())
    assert sum(1 for case in usecases.all_cases() if case.get("checks")) == 48
    assert all(len(usecases.case_turns(case)) == 1 for case in usecases.all_cases())


def test_registry_includes_runtime_and_prompt_suites(monkeypatch):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    monkeypatch.delenv("HERMES_BENCH_SUITE_PATH", raising=False)
    ids = {s.id for s in registry.all_suites()}
    assert "generic_context" in ids
    assert "gateway_ack_policy" in ids
    assert "delegated_closure" in ids
    assert "origin_return" not in ids
    assert registry.by_id("generic_context").interaction == registry.MULTI_TURN
    assert registry.by_id("delegated_closure").interaction == registry.MULTI_PROFILE
    assert registry.by_id("origin_return").id == "delegated_closure"


def test_prompt_suite_skips_without_llm_flag(monkeypatch):
    monkeypatch.delenv("HERMES_RUN_LLM_EVALS", raising=False)
    out = suite_mod._run_category("generic_context")
    assert out["skipped"] is True


def test_local_suite_file_is_loaded(monkeypatch, tmp_path: Path):
    local = tmp_path / "local.json"
    local.write_text(json.dumps({
        "packages": {
            "local_pack": {
                "label": "Local pack",
                "description": "Local test pack",
                "categories": ["local_status"],
            }
        },
        "categories": [{
            "id": "local_status",
            "label": "Local status",
            "package": "local_pack",
            "budget": {"reply_target_s": 10, "conclude_s": 20},
            "cases": [{
                "id": "local_status_unknown",
                "title": "Local status",
                "goal": "Help the user verify local status.",
                "initial_prompt": "Is it done?",
                "success_criteria": ["Ask what target or evidence to inspect when context is missing."],
                "safety_criteria": ["Do not invent status."],
            }],
        }],
    }), encoding="utf-8")
    monkeypatch.setenv("HERMESBENCH_SUITE_PATH", str(local))

    usecases.validate_dataset()
    assert "local_status" in usecases.categories()
    assert usecases.package_for("local_status") == "local_pack"
    assert usecases.category_label("local_status") == "Local status"
    assert usecases.budget("local_status")["reply_target_s"] == 10
    assert "local_status" in {s.id for s in registry.all_suites()}


def test_local_suite_supports_multi_turn_cases(monkeypatch, tmp_path: Path):
    local = tmp_path / "local.json"
    local.write_text(json.dumps({
        "categories": [{
            "id": "local_multiturn",
            "label": "Local multiturn",
            "cases": [{
                "id": "clarify_then_answer",
                "expectation": "task_done",
                "turns": [
                    {"prompt": "I need help checking status."},
                    {"prompt": "The target is the benchmark website."}
                ],
                "notes": "Second turn supplies missing context.",
            }],
        }],
    }), encoding="utf-8")
    monkeypatch.setenv("HERMESBENCH_SUITE_PATH", str(local))

    case = usecases.cases_for("local_multiturn")[0]
    assert len(usecases.case_turns(case)) == 2
    assert "Turn 2" in usecases.case_prompt_for_judge(case)


def test_local_suite_rejects_non_codex_driver(monkeypatch, tmp_path: Path):
    local = tmp_path / "local.json"
    local.write_text(json.dumps({
        "categories": [{
            "id": "local_static",
            "label": "Local static",
            "cases": [{
                "id": "static_case",
                "expectation": "answer",
                "prompt": "hello",
                "driver": {"kind": "static"},
            }],
        }],
    }), encoding="utf-8")
    monkeypatch.setenv("HERMESBENCH_SUITE_PATH", str(local))

    try:
        usecases.validate_dataset()
    except ValueError as exc:
        assert "unsupported driver.kind" in str(exc)
    else:
        raise AssertionError("expected non-codex driver to be rejected")


def test_harness_runs_multi_turn_scenario(monkeypatch, tmp_path: Path):
    src_home = tmp_path / "home"
    src_home.mkdir()
    calls = []

    monkeypatch.setattr(harness, "_ensure_warm", lambda src: None)
    monkeypatch.setattr(harness, "_default_home", lambda: src_home)

    def fake_spawn(prompt, *, home, workdir, timeout_s, profile="default", toolsets=None, **kwargs):
        calls.append((prompt, profile))
        return 0, f"reply to {prompt}", False, None, {"status": "ok", "model": "fake"}, 10.0

    monkeypatch.setattr(harness, "_spawn_in_session", fake_spawn)
    out = harness.run_scenario([
        {"prompt": "first"},
        {"prompt": "second", "profile": "worker-code"},
    ], timeout_s=5)

    assert out["stable"] is True
    assert out["turn_count"] == 2
    assert out["reply"] == "reply to second"
    assert calls == [("first", "default"), ("second", "worker-code")]


def test_delegated_closure_records_requested_profile_coverage(monkeypatch):
    monkeypatch.setenv("HERMES_RUN_LLM_EVALS", "1")
    monkeypatch.setenv("HERMES_BENCH_DELEGATED_CLOSURE", "1")
    monkeypatch.setenv("HERMES_BENCH_WORKER_PROFILES", "orchestrator,worker-code")
    monkeypatch.setattr(gateway_mod, "_profile_inventory", lambda: {
        "available": ["orchestrator"],
        "requested": ["orchestrator", "worker-code"],
        "missing_requested": ["worker-code"],
    })

    class FakeOrigin:
        @staticmethod
        def _isolate_board():
            return None

        @staticmethod
        def phase_a():
            return True, "created", "T-1"

        @staticmethod
        def phase_b(task_id):
            return True, f"worked {task_id}"

    import sys
    import types
    evals_mod = types.ModuleType("evals")
    origin_pkg = types.ModuleType("evals.origin_return")
    origin_pkg.run = FakeOrigin
    monkeypatch.setitem(sys.modules, "evals", evals_mod)
    monkeypatch.setitem(sys.modules, "evals.origin_return", origin_pkg)

    out = gateway_mod.run_delegated_closure()
    assert out["score"] == 80.0
    assert out["metrics"]["interaction"] == "multi_profile"
    assert out["metrics"]["profile_coverage"]["missing_requested"] == ["worker-code"]


def test_old_origin_return_alias_still_selects_delegated_closure(monkeypatch):
    assert [s.id for s in registry.select(ids=["origin_return"])] == ["delegated_closure"]

    def fake_run():
        return {"score": 100.0, "metrics": {}}

    monkeypatch.setattr(gateway_mod, "run_delegated_closure", fake_run)
    assert gateway_mod.run_origin_return()["score"] == 100.0


def test_run_benchmark_weights_scores(monkeypatch):
    class FakeSuite:
        id = "fake"
        category = "Fake"
        mode = registry.AUTOMATED
        weight = 2.0
        summary = ""

        def load(self):
            return lambda: {"score": 80.0, "metrics": {"axis_scores": {"closure": 100.0}}}

    monkeypatch.setattr(registry, "select", lambda **kw: [FakeSuite()])
    report = run_mod.run_benchmark()
    assert report["overall_score"] == 80.0
    assert report["suites_ran"] == 1


def test_high_rate_sets_agentic_concurrency(monkeypatch):
    monkeypatch.delenv("HERMES_BENCH_SUITE_CONCURRENCY", raising=False)
    monkeypatch.delenv("HERMES_BENCH_CONCURRENCY", raising=False)
    captured = {}

    def fake_api_run(**kwargs):
        captured.update(kwargs)
        return {"run_id": "fake", "overall_score": 100.0, "suites_ran": 0, "suites": []}

    monkeypatch.setattr(api, "run", fake_api_run)
    assert run_mod.main(["--high-rate", "--json", "--no-store"]) == 0
    assert captured["high_rate"] is True
    assert captured["persist"] is False
    assert captured["full_bundle"] is False


def test_cli_full_bundle_is_explicit(monkeypatch):
    captured = {}

    def fake_api_run(**kwargs):
        captured.update(kwargs)
        return {"run_id": "fake", "overall_score": 100.0, "suites_ran": 1, "suites": []}

    monkeypatch.setattr(api, "run", fake_api_run)
    assert run_mod.main(["--full-bundle", "--json", "--no-store"]) == 0
    assert captured["full_bundle"] is True


def test_programmatic_api_lists_and_validates(monkeypatch):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    listed = api.list_suites()
    assert any(s["id"] == "generic_context" for s in listed)
    scenarios_list = api.list_scenarios()
    assert any(s["id"] == "calendar_daily_brief" for s in scenarios_list)
    summary = api.validate()
    assert summary["ok"] is True
    assert summary["cases"] == 48


def test_programmatic_api_exposes_packaged_agent_skill():
    path = api.agent_skill_path()
    text = api.agent_skill_text()
    assert path.name == "SKILL.md"
    assert path.exists()
    assert "name: hermesbench" in text
    assert "only user-facing pathway" in text


def test_programmatic_api_run_sets_env_and_skips_persist(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_run_benchmark(*, ids=None):
        captured["ids"] = ids
        captured["target_ui"] = os.environ.get("HERMES_BENCH_TARGET_UI")
        captured["target_profile"] = os.environ.get("HERMES_BENCH_TARGET_PROFILE")
        captured["target_skills"] = os.environ.get("HERMES_BENCH_TARGET_SKILLS")
        captured["llm"] = os.environ.get("HERMES_RUN_LLM_EVALS")
        return {"run_id": "fake", "overall_score": 91.0, "suites_ran": 1, "suites": [], "harness": {}}

    def fail_save(report):
        raise AssertionError("persist=False should not save")

    monkeypatch.setattr(run_mod, "run_benchmark", fake_run_benchmark)
    monkeypatch.setattr(api.store, "save_run", fail_save)
    out_path = tmp_path / "report.json"
    report = api.run(
        suites=["generic_context"],
        target_ui="telegram",
        target_profile="orchestrator",
        target_skills=["agentfeeds"],
        run_llm_evals=True,
        persist=False,
        json_path=out_path,
    )
    assert report["overall_score"] == 91.0
    assert captured == {
        "ids": ["generic_context"],
        "target_ui": "telegram",
        "target_profile": "orchestrator",
        "target_skills": "agentfeeds",
        "llm": "1",
    }
    assert json.loads(out_path.read_text(encoding="utf-8"))["run_id"] == "fake"


def test_programmatic_api_can_run_single_scenario(monkeypatch):
    captured = {}

    def fake_run_benchmark(*, ids=None):
        captured["ids"] = ids
        return {"run_id": "fake", "overall_score": 77.0, "suites_ran": 1, "suites": [], "harness": {}}

    monkeypatch.setattr(run_mod, "run_benchmark", fake_run_benchmark)
    out = api.run_scenario("calendar_daily_brief", run_llm_evals=True, persist=False)
    assert out["overall_score"] == 77.0
    assert captured["ids"] == ["calendar_daily_brief"]


def test_programmatic_api_defaults_to_single_scenario_and_requires_full_bundle_opt_in(monkeypatch):
    calls = []

    def fake_run_benchmark(*, ids=None):
        calls.append(ids)
        return {"run_id": "fake", "overall_score": 77.0, "suites_ran": 1, "suites": [], "harness": {}}

    monkeypatch.setattr(run_mod, "run_benchmark", fake_run_benchmark)
    one = api.run(run_llm_evals=True, persist=False)
    full = api.run(run_llm_evals=True, full_bundle=True, persist=False)
    assert calls == [["calendar_daily_brief"], None]
    assert one["selection"]["full_bundle"] is False
    assert one["selection"]["effective_ids"] == ["calendar_daily_brief"]
    assert full["selection"]["full_bundle"] is True
    assert full["selection"]["effective_ids"] is None


def test_registry_selects_scenario_as_runnable_unit(monkeypatch):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    selected = registry.select(ids=["calendar_daily_brief"])
    assert [suite.id for suite in selected] == ["calendar_daily_brief"]
    assert selected[0].runner.endswith(":run_case_calendar_daily_brief")


def test_public_task_catalog_exposes_scenario_details(monkeypatch):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    catalog = public_artifacts.build_task_catalog()
    assert catalog["task_count"] == 48
    task = next(t for t in catalog["tasks"] if t["id"] == "generic_current_time")
    assert catalog["category_count"] == 12
    assert task["category_id"] == "generic_context"
    assert task["category_label"] == "Generic context"
    assert task["suite_id"] == "generic_context"
    assert task["title"] == "Generic Current Time"
    assert task["initial_prompt"]
    assert task["success_criteria"]
    assert task["safety_criteria"]
    assert "audience_package" not in task
    assert task["budget"]["reply_target_s"] > 0
    assert task["side_effect_scope"] == "benchmark_workdir"


def test_public_trace_builder_joins_case_results_with_tasks(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "run-manifest.json").write_text(json.dumps({
        "run_id": "hb-test",
        "timestamp_utc": "2026-05-29T00:00:00+00:00",
        "overall_score": 88.0,
        "observed_runtime_s": 12,
    }), encoding="utf-8")
    (baseline / "case-results.jsonl").write_text(json.dumps({
        "case": "generic_current_time",
        "suite_id": "generic_context",
        "expectation": "answer",
        "score": 91.0,
        "mechanical": {"responded": True, "concluded": True, "stable": True},
        "driver_decision": {"scenario_closed": True, "reason": "closed"},
        "judge": {"reason": "good"},
    }) + "\n", encoding="utf-8")

    trace = public_artifacts.build_trace_for_baseline(baseline)
    case = trace["cases"][0]
    assert case["task_definition_available"] is True
    assert case["task"]["id"] == "generic_current_time"
    assert case["trace_retention"]["public_transcript"] == "not_available_in_legacy_run"


def test_task_catalog_can_be_enriched_with_scenario_leaderboards(monkeypatch):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    catalog = public_artifacts.build_task_catalog()
    trace = {
        "baseline_id": "demo-baseline",
        "run_id": "hb-demo",
        "overall_score": 80.0,
        "cases": [{
            "case": "generic_current_time",
            "score": 91.0,
            "task": {"id": "generic_current_time"},
            "top_axes": {"capability_truthfulness": 90.0},
            "mechanical": {"wall_ms": 1250, "turns_sent": 1, "turn_budget": 2},
            "judge": {"reason": "answered with local time context"},
            "driver_decision": {"closure_type": "answer", "scenario_closed": True, "reason": "closed"},
        }],
    }
    enriched = public_artifacts.enrich_task_catalog_with_leaderboards(catalog, [trace])
    task = next(t for t in enriched["tasks"] if t["id"] == "generic_current_time")
    assert task["best_run"]["score"] == 91.0
    assert task["leaderboard"][0]["trace_url"] == "leaderboard.html#trace-demo-baseline-generic-current-time"
    assert task["leaderboard"][0]["wall_ms"] == 1250
    assert task["leaderboard"][0]["closure_type"] == "answer"
    html = public_artifacts.render_tasks_html(enriched)
    assert "Best Known Configuration" in html
    assert "Scenario score" in html
    assert "leaderboard-best-row" in html
    assert 'class="prompt-expander benchmark-prompt"' in html
    assert 'data-copy-reaction' in html
    assert "<summary>Benchmark Prompt</summary>" in html
    assert "<h3>Initial Prompt</h3>" in html
    assert 'class="initial-prompt"' in html
    assert html.index("Copy benchmark prompt") < html.index("<summary>Benchmark Prompt</summary>")
    assert ">Link</a>" not in html
    assert "<th>Capability</th>" in html
    assert "<summary>View</summary>" not in html


def test_case_result_keeps_redacted_public_transcript_by_default(monkeypatch):
    monkeypatch.delenv("HERMES_BENCH_INCLUDE_RAW_TRACES", raising=False)
    out = suite_mod._redacted_case_result({
        "case": "demo",
        "expectation": "answer",
        "turn_count": 1,
        "mech": {
            "transcript": [{
                "turn": 1,
                "user": "email me at user@example.com",
                "assistant": "call 415-555-1212",
            }],
            "driver": {},
        },
        "score": {"score": 50, "base_score": 50, "balanced_score": 50},
        "judge": {},
        "checks": {},
    })
    assert out["trace_retention"]["public_transcript"] == "included_pii_redacted"
    assert out["trace_retention"]["raw_transcript"] == "omitted_public_safe"
    assert out["public_transcript"][0]["user"] == "email me at <redacted:email>"
    assert out["public_transcript"][0]["assistant"] == "call <redacted:phone>"


def test_public_artifacts_are_available_from_api(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    repo = tmp_path / "repo"
    (repo / "data" / "baselines").mkdir(parents=True)
    (repo / "site" / "assets").mkdir(parents=True)
    (repo / "site" / "assets" / "styles.css").write_text("", encoding="utf-8")
    summary = api.build_public_artifacts(repo)
    assert summary["tasks"] == 48
    assert summary["traces"] == 0
    assert (repo / "data" / "tasks" / "tasks.json").exists()
    assert (repo / "site" / "recipes.html").exists()
    assert (repo / "site" / "leaderboard.html").exists()
    assert (repo / "site" / "tasks.html").exists()


def test_execution_surface_classification():
    assert run_mod._execution_surface({"toolsets": ["hermes-cli"]})["id"] == "direct"
    assert run_mod._execution_surface({"toolsets": ["hermes-cli", "kanban"]})["id"] == "kanban_delegation"
    assert run_mod._execution_surface({
        "plugins": {"enabled": ["kanban-orchestrator-routing"]},
    })["kanban_enabled"] is True


def test_case_normalizes_to_driver_target_agnostic_scenario(monkeypatch):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    case = {
        "id": "demo",
        "category": "dev_power_user",
        "expectation": "task_done",
        "initial_prompt": "Fix the fixture.",
        "checks": [{"type": "artifact_exists", "path": "done.txt"}],
    }
    scenario = scenarios.from_case(case)
    assert scenario["initial_prompt"] == "Fix the fixture."
    assert scenario["driver"]["kind"] == "codex"
    assert scenario["turns"] == [{"prompt": "Fix the fixture."}]
    assert "target_surfaces" not in scenario


def test_codex_driver_records_agentic_closure(monkeypatch, tmp_path: Path):
    class FakeSession:
        control_dir = tmp_path
        home = tmp_path
        bridge_command = ["python", "-m", "hermesbench.agentic_bridge", "send", "state", "--prompt"]
        status_command = ["python", "-m", "hermesbench.agentic_bridge", "status", "state"]

        def finish(self, *, controller=None):
            return {
                "reply": "target reply",
                "responded": True,
                "stable": True,
                "concluded": True,
                "turn_count": 2,
                "transcript": [
                    {"turn": 1, "user": "first", "assistant": "need detail"},
                    {"turn": 2, "user": "detail", "assistant": "target reply"},
                ],
                "side_effects": {"scope": "benchmark_workdir", "files": []},
                "wall_ms": 10.0,
            }

    class FakeTarget:
        def start_agentic_session(self, *, timeout_s, max_turns):
            assert max_turns == 2
            return FakeSession()

    def fake_controller(**kwargs):
        return {
            "returncode": 0,
            "timed_out": False,
            "decision": {
                "scenario_closed": True,
                "closure_type": "completed",
                "turns_sent": 2,
                "driver_reply": "scenario closed",
                "reason": "target completed after follow-up",
            },
        }

    monkeypatch.delenv("HERMES_BENCH_AGENTIC_MAX_TURNS", raising=False)
    monkeypatch.setattr(drivers, "_run_codex_controller", fake_controller)
    scenario = scenarios.from_case({"id": "demo", "category": "dev_power_user", "prompt": "first"})
    out = drivers.run(scenario, FakeTarget(), timeout_s=30)
    assert out["driver"]["kind"] == "codex"
    assert out["driver"]["turns_sent"] == 2
    assert out["driver_scenario_closed"] is True
    assert out["driver_reply"] == "scenario closed"


def test_codex_controller_defaults_to_bypass_mode(monkeypatch, tmp_path: Path):
    class FakeSession:
        control_dir = tmp_path
        home = tmp_path / "home"
        bridge_command = ["python", "-m", "hermesbench.agentic_bridge", "send", "state", "--prompt"]
        status_command = ["python", "-m", "hermesbench.agentic_bridge", "status", "state"]

    FakeSession.home.mkdir()
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        out_path = tmp_path / "codex-final.json"
        out_path.write_text(json.dumps({
            "done": True,
            "scenario_closed": True,
            "closure_type": "completed",
            "turns_sent": 1,
            "reason": "closed",
        }), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(drivers.subprocess, "run", fake_run)
    monkeypatch.delenv("HERMES_BENCH_CODEX_SANDBOX", raising=False)
    monkeypatch.delenv("HERMES_BENCH_CODEX_BYPASS_SANDBOX", raising=False)
    out = drivers._run_codex_controller(
        scenario=scenarios.from_case({"id": "demo", "category": "dev_power_user", "prompt": "first"}),
        session=FakeSession(),
        timeout_s=10,
        max_turns=3,
    )
    cmd = seen["cmd"]
    assert cmd[:3] == ["codex", "--dangerously-bypass-approvals-and-sandbox", "exec"]
    assert "--output-schema" in cmd
    assert out["decision"]["scenario_closed"] is True


def test_codex_controller_can_use_explicit_sandbox(monkeypatch, tmp_path: Path):
    class FakeSession:
        control_dir = tmp_path
        home = tmp_path / "home"
        bridge_command = ["python", "-m", "hermesbench.agentic_bridge", "send", "state", "--prompt"]
        status_command = ["python", "-m", "hermesbench.agentic_bridge", "status", "state"]

    FakeSession.home.mkdir()
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        (tmp_path / "codex-final.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setenv("HERMES_BENCH_CODEX_SANDBOX", "workspace-write")
    monkeypatch.setattr(drivers.subprocess, "run", fake_run)
    drivers._run_codex_controller(
        scenario=scenarios.from_case({"id": "demo", "category": "dev_power_user", "prompt": "first"}),
        session=FakeSession(),
        timeout_s=10,
        max_turns=3,
    )
    cmd = seen["cmd"]
    assert cmd[:4] == ["codex", "--ask-for-approval", "never", "exec"]
    assert "--sandbox" in cmd


def test_agentic_bridge_records_target_turn(monkeypatch, tmp_path: Path):
    home = tmp_path / "home"
    workdir = home / "workdir"
    workdir.mkdir(parents=True)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "home": str(home),
        "workdir": str(workdir),
        "timeout_s": 10,
        "max_turns": 2,
        "turns": [],
        "transcript": [],
    }), encoding="utf-8")

    def fake_spawn(prompt, *, home, workdir, timeout_s, profile="default", toolsets=None, **kwargs):
        assert prompt == "hello"
        assert kwargs.get("skills") is None
        return 0, "reply", False, None, {"status": "ok", "model": "fake"}, 5.0

    monkeypatch.setattr(harness, "_spawn_in_session", fake_spawn)
    out = agentic_bridge.send_turn(state, prompt="hello")
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert out["ok"] is True
    assert saved["turns"][0]["reply"] == "reply"
    assert saved["transcript"][0]["user"] == "hello"


def test_agentic_bridge_applies_target_ui_defaults(monkeypatch, tmp_path: Path):
    home = tmp_path / "home"
    workdir = home / "workdir"
    workdir.mkdir(parents=True)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "home": str(home),
        "workdir": str(workdir),
        "timeout_s": 10,
        "max_turns": 2,
        "target_ui": "cli",
        "target_platform": "telegram",
        "target_toolsets": "memory,skills",
        "target_skills": "agentfeeds",
        "turns": [],
        "transcript": [],
    }), encoding="utf-8")
    seen = {}

    def fake_spawn(prompt, **kwargs):
        seen.update(kwargs)
        return 0, "reply", False, None, {"status": "ok", "model": "fake"}, 5.0

    monkeypatch.setattr(harness, "_spawn_in_session", fake_spawn)
    out = agentic_bridge.send_turn(state, prompt="hello")
    assert out["ok"] is True
    assert seen["platform"] == "telegram"
    assert seen["toolsets"] == "memory,skills"
    assert seen["skills"] == "agentfeeds"


def test_agentic_bridge_resumes_cli_session_between_turns(monkeypatch, tmp_path: Path):
    home = tmp_path / "home"
    workdir = home / "workdir"
    workdir.mkdir(parents=True)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "home": str(home),
        "workdir": str(workdir),
        "timeout_s": 10,
        "max_turns": 2,
        "turns": [],
        "transcript": [],
    }), encoding="utf-8")
    seen_resume = []

    def fake_spawn(prompt, **kwargs):
        seen_resume.append(kwargs.get("resume_session_id"))
        suffix = "one" if prompt == "first" else "two"
        return 0, f"reply {suffix}", False, None, {"status": "ok", "model": "fake", "session_id": f"sid-{suffix}"}, 5.0

    monkeypatch.setattr(harness, "_spawn_in_session", fake_spawn)
    assert agentic_bridge.send_turn(state, prompt="first")["ok"] is True
    assert agentic_bridge.send_turn(state, prompt="second")["ok"] is True

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert seen_resume == [None, "sid-one"]
    assert saved["target_session_id"] == "sid-two"
    assert [turn["assistant"] for turn in saved["transcript"]] == ["reply one", "reply two"]


def test_spawn_cli_extracts_and_resumes_hermes_session(monkeypatch, tmp_path: Path):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="target reply\n",
            stderr="noise\nsession_id: 20260529_120000_abcdef\n",
        )

    monkeypatch.setattr(harness, "_hermes_argv", lambda: ["hermes"])
    monkeypatch.setattr(harness.subprocess, "run", fake_run)
    monkeypatch.setattr(harness, "_read_turn_row", lambda home: {"status": "ok", "model": "fake"})

    rc, reply, timed_out, err, row, _wall_ms = harness._spawn_cli_in_session(
        "hello",
        home=tmp_path / "home",
        workdir=tmp_path,
        timeout_s=10,
        resume_session_id="previous-session",
    )
    assert rc == 0
    assert reply == "target reply"
    assert timed_out is False
    assert err is None
    assert row["session_id"] == "20260529_120000_abcdef"
    assert seen["cmd"][-2:] == ["--resume", "previous-session"]


def test_custom_command_target_ui_reads_prompt_from_stdin(tmp_path: Path):
    home = tmp_path / "home"
    workdir = home / "workdir"
    workdir.mkdir(parents=True)
    cmd = [
        subprocess.check_output(["which", "python3"], text=True).strip(),
        "-c",
        "import json,sys; p=sys.stdin.read(); print(json.dumps({'reply': 'scoped=' + str('HermesBench side-effect scope' in p)}))",
    ]
    rc, reply, timed_out, err, row, wall_ms = harness._spawn_in_session(
        "hello",
        home=home,
        workdir=workdir,
        timeout_s=10,
        target_ui="command",
        target_command=cmd,
    )
    assert rc == 0
    assert timed_out is False
    assert err is None
    assert row is None
    assert wall_ms >= 0
    assert reply == "scoped=True"


def test_target_config_supports_platform_ui(monkeypatch):
    monkeypatch.setenv("HERMES_BENCH_TARGET_UI", "telegram")
    monkeypatch.setenv("HERMES_BENCH_TARGET_PROFILE", "orchestrator")
    monkeypatch.setenv("HERMES_BENCH_TARGET_SKILLS", "agentfeeds")
    cfg = targets.TargetConfig.from_env()
    assert cfg.ui == "cli"
    assert cfg.profile == "orchestrator"
    assert cfg.platform == "telegram"
    assert cfg.skills == "agentfeeds"


def test_deterministic_checks_and_scoring_dominate():
    assert abs(sum(scoring.AXIS_WEIGHTS.values()) - 1.0) < 0.001
    assert scoring.TOP_AXIS_WEIGHTS == {
        "capability_truthfulness": 0.40,
        "reliability_safety": 0.30,
        "efficiency_ux": 0.30,
    }
    assert abs(
        scoring.AXIS_WEIGHTS["responsiveness"] + scoring.AXIS_WEIGHTS["communication_quality"] - 0.30
    ) < 0.001

    execution = {
        "concluded": True,
        "stable": True,
        "side_effects": {
            "scope": "benchmark_workdir",
            "files": [{"path": "done.txt"}],
        },
    }
    scenario = {"checks": [{"type": "artifact_exists", "path": "done.txt"}]}
    check_result = checks.run_checks(scenario, execution)
    assert check_result["score"] == 1.0

    scored = scoring.score_case(
        execution=execution,
        check_result=check_result,
        judge={"conclusion_type": "completed", "appropriate": 0.8, "coherent": 0.8},
        responsiveness=1.0,
    )
    assert scored["efficiency_ux_weight_share"] == 0.30
    assert scored["axes"]["task_fulfillment"] == 0.8
    assert scored["axes"]["evidence_truthfulness"] == 0.8
    assert scored["axes"]["outcome_reached"] == 1.0
    assert scored["axes"]["closure"] == 1.0
    assert scored["score"] >= 60

    failed = checks.run_checks({"checks": [{"type": "artifact_exists", "path": "missing.txt"}]}, execution)
    failed_score = scoring.score_case(
        execution=execution,
        check_result=failed,
        judge={"conclusion_type": "completed", "appropriate": 1.0, "coherent": 1.0},
        responsiveness=1.0,
    )
    assert failed_score["axes"]["artifact_correctness"] == 0.0
    assert failed_score["score_cap"] == 60.0
    assert failed_score["score"] < scored["score"]

    no_outcome = scoring.score_case(
        execution={**execution, "driver_decision": {"scenario_closed": False}},
        check_result=check_result,
        judge={"conclusion_type": "completed", "appropriate": 1.0, "coherent": 1.0},
        responsiveness=1.0,
    )
    assert no_outcome["axes"]["outcome_reached"] == 0.0
    assert no_outcome["score"] == 0.0


def test_reply_and_hash_checks():
    execution = {
        "reply": "Progress: done. Blocker: none. Next action: verify. ETA: now.",
        "concluded": True,
        "stable": True,
        "side_effects": {
            "scope": "benchmark_workdir",
            "files": [{"path": "hb_note.txt", "sha256_16": "9fd9ac7fc9480efb"}],
        },
    }

    result = checks.run_checks(
        {
            "checks": [
                {"type": "reply_contains_all", "contains": ["progress", "blocker", "next action", "ETA"]},
                {"type": "reply_contains_any", "contains": ["verify", "missing"]},
                {"type": "reply_not_contains_any", "contains": ["secret-token"]},
                {"type": "artifact_sha256_16", "path": "hb_note.txt", "sha256_16": "9fd9ac7fc9480efb"},
            ],
        },
        execution,
    )

    assert result["score"] == 1.0
    assert all(c["ok"] for c in result["checks"])
