from __future__ import annotations

import json
from pathlib import Path

from hermesbench import registry, run as run_mod, usecases
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
