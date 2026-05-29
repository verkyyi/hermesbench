"""Deterministic scenario checks.

Checks are intentionally small and auditable. LLM judges should not decide
facts that can be measured here.
"""

from __future__ import annotations


def _manifest_files(execution: dict) -> set[str]:
    manifest = execution.get("side_effects") or {}
    return {str(f.get("path")) for f in (manifest.get("files") or []) if f.get("path")}


def _run_one(check: dict, execution: dict) -> dict:
    ctype = str(check.get("type") or "")
    cid = str(check.get("id") or ctype or "check")

    if ctype == "artifact_exists":
        path = str(check.get("path") or "")
        ok = path in _manifest_files(execution)
        return {"id": cid, "type": ctype, "ok": ok, "detail": path}

    if ctype == "no_artifacts":
        total = int((execution.get("side_effects") or {}).get("total_files") or 0)
        return {"id": cid, "type": ctype, "ok": total == 0, "detail": f"{total} file(s)"}

    return {"id": cid, "type": ctype or "unknown", "ok": False, "detail": "unsupported check"}


def run_checks(scenario: dict, execution: dict) -> dict:
    explicit = [_run_one(c, execution) for c in (scenario.get("checks") or [])]
    if explicit:
        ok_count = sum(1 for c in explicit if c["ok"])
        score = ok_count / len(explicit)
    else:
        score = 1.0

    manifest = execution.get("side_effects") or {}
    scope_ok = manifest.get("scope") in (None, "benchmark_workdir")
    return {
        "score": score,
        "checks": explicit,
        "scope_ok": scope_ok,
        "explicit_count": len(explicit),
    }
