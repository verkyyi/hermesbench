from __future__ import annotations

import json
import subprocess
from pathlib import Path

from hermesbench import checks, drivers, harness, registry, run as run_mod, scenarios, scoring, usecases
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


def test_registry_includes_runtime_and_prompt_suites(monkeypatch):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    monkeypatch.delenv("HERMES_BENCH_SUITE_PATH", raising=False)
    ids = {s.id for s in registry.all_suites()}
    assert "runtime_config" in ids
    assert "gateway_ack_policy" in ids
    assert "delegated_closure" in ids
    assert "origin_return" not in ids
    assert registry.by_id("runtime_config").interaction == registry.MULTI_TURN
    assert registry.by_id("delegated_closure").interaction == registry.MULTI_PROFILE
    assert registry.by_id("origin_return").id == "delegated_closure"


def test_prompt_suite_skips_without_llm_flag(monkeypatch):
    monkeypatch.delenv("HERMES_RUN_LLM_EVALS", raising=False)
    out = suite_mod._run_category("runtime_config")
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
                "expectation": "clarify",
                "prompt": "Is it done?",
                "notes": "Missing context.",
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


def test_harness_runs_multi_turn_scenario(monkeypatch, tmp_path: Path):
    src_home = tmp_path / "home"
    src_home.mkdir()
    calls = []

    monkeypatch.setattr(harness, "_ensure_warm", lambda src: None)
    monkeypatch.setattr(harness, "_default_home", lambda: src_home)

    def fake_spawn(prompt, *, home, workdir, timeout_s, profile="default", toolsets=None):
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


def test_execution_surface_classification():
    assert run_mod._execution_surface({"toolsets": ["hermes-cli"]})["id"] == "direct"
    assert run_mod._execution_surface({"toolsets": ["hermes-cli", "kanban"]})["id"] == "kanban_delegation"
    assert run_mod._execution_surface({
        "plugins": {"enabled": ["kanban-orchestrator-routing"]},
    })["kanban_enabled"] is True


def test_case_normalizes_to_driver_target_agnostic_scenario(monkeypatch):
    monkeypatch.delenv("HERMESBENCH_SUITE_PATH", raising=False)
    monkeypatch.delenv("HERMES_BENCH_DRIVER", raising=False)
    case = {
        "id": "demo",
        "category": "code_workflow",
        "expectation": "task_done",
        "initial_prompt": "Fix the fixture.",
        "checks": [{"type": "artifact_exists", "path": "done.txt"}],
    }
    scenario = scenarios.from_case(case)
    assert scenario["initial_prompt"] == "Fix the fixture."
    assert scenario["driver"]["kind"] == "codex"
    assert scenario["turns"] == [{"prompt": "Fix the fixture."}]
    assert "target_surfaces" not in scenario


def test_static_driver_can_be_selected_by_run_config(monkeypatch):
    monkeypatch.setenv("HERMES_BENCH_DRIVER", "static")
    scenario = scenarios.from_case({
        "id": "demo",
        "category": "code_workflow",
        "prompt": "Say hi.",
    })
    assert isinstance(drivers.build_driver(scenario), drivers.StaticDriver)


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
            assert max_turns == 3
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
    scenario = scenarios.from_case({"id": "demo", "category": "code_workflow", "prompt": "first"})
    out = drivers.run(scenario, FakeTarget(), timeout_s=30)
    assert out["driver"]["kind"] == "codex"
    assert out["driver"]["turns_sent"] == 2
    assert out["driver_scenario_closed"] is True
    assert out["driver_reply"] == "scenario closed"


def test_codex_controller_uses_top_level_approval_flag(monkeypatch, tmp_path: Path):
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
    out = drivers._run_codex_controller(
        scenario=scenarios.from_case({"id": "demo", "category": "code_workflow", "prompt": "first"}),
        session=FakeSession(),
        timeout_s=10,
        max_turns=3,
    )
    cmd = seen["cmd"]
    assert cmd[:4] == ["codex", "--ask-for-approval", "never", "exec"]
    assert out["decision"]["scenario_closed"] is True


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

    def fake_spawn(prompt, *, home, workdir, timeout_s, profile="default", toolsets=None):
        assert prompt == "hello"
        return 0, "reply", False, None, {"status": "ok", "model": "fake"}, 5.0

    monkeypatch.setattr(harness, "_spawn_in_session", fake_spawn)
    out = agentic_bridge.send_turn(state, prompt="hello")
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert out["ok"] is True
    assert saved["turns"][0]["reply"] == "reply"
    assert saved["transcript"][0]["user"] == "hello"


def test_deterministic_checks_and_scoring_dominate():
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
        judge={"conclusion_type": "completed", "appropriate": 0.5, "coherent": 0.5},
        responsiveness=1.0,
    )
    assert scored["deterministic_weight_share"] == 0.85
    assert scored["score"] > 80

    failed = checks.run_checks({"checks": [{"type": "artifact_exists", "path": "missing.txt"}]}, execution)
    failed_score = scoring.score_case(
        execution=execution,
        check_result=failed,
        judge={"conclusion_type": "completed", "appropriate": 1.0, "coherent": 1.0},
        responsiveness=1.0,
    )
    assert failed_score["axes"]["artifact_correctness"] == 0.0
    assert failed_score["score"] < scored["score"]
