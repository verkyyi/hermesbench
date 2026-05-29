from __future__ import annotations

import json
from pathlib import Path

from hermesbench import harness, registry, run as run_mod, usecases
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
    assert "origin_return" in ids
    assert registry.by_id("runtime_config").interaction == registry.MULTI_TURN
    assert registry.by_id("origin_return").interaction == registry.MULTI_PROFILE


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


def test_origin_return_records_requested_profile_coverage(monkeypatch):
    monkeypatch.setenv("HERMES_RUN_LLM_EVALS", "1")
    monkeypatch.setenv("HERMES_BENCH_ORIGIN_RETURN", "1")
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

    out = gateway_mod.run_origin_return()
    assert out["score"] == 80.0
    assert out["metrics"]["interaction"] == "multi_profile"
    assert out["metrics"]["profile_coverage"]["missing_requested"] == ["worker-code"]


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
