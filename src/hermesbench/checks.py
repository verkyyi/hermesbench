"""Deterministic scenario checks.

Checks are intentionally small and auditable. LLM judges should not decide
facts that can be measured here.
"""

from __future__ import annotations


def _manifest_files(execution: dict) -> set[str]:
    manifest = execution.get("side_effects") or {}
    return {str(f.get("path")) for f in (manifest.get("files") or []) if f.get("path")}


def _manifest_file(execution: dict, path: str) -> dict | None:
    manifest = execution.get("side_effects") or {}
    for item in manifest.get("files") or []:
        if str(item.get("path")) == path:
            return item
    return None


def _terms(check: dict) -> list[str]:
    raw = check.get("contains")
    if raw is None:
        raw = check.get("terms")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


def _haystack(execution: dict, *, case_sensitive: bool) -> str:
    text = str(execution.get("reply") or "")
    return text if case_sensitive else text.lower()


def _needle(term: str, *, case_sensitive: bool) -> str:
    return term if case_sensitive else term.lower()


def _run_one(check: dict, execution: dict) -> dict:
    ctype = str(check.get("type") or "")
    cid = str(check.get("id") or ctype or "check")

    if ctype == "artifact_exists":
        path = str(check.get("path") or "")
        ok = path in _manifest_files(execution)
        return {"id": cid, "type": ctype, "ok": ok, "detail": path}

    if ctype == "artifact_sha256_16":
        path = str(check.get("path") or "")
        expected = check.get("sha256_16")
        expected_values = {str(expected)} if expected else {str(x) for x in check.get("one_of") or []}
        actual = (_manifest_file(execution, path) or {}).get("sha256_16")
        ok = bool(actual) and actual in expected_values
        return {"id": cid, "type": ctype, "ok": ok, "detail": f"{path}:{actual or 'missing'}"}

    if ctype == "no_artifacts":
        total = int((execution.get("side_effects") or {}).get("total_files") or 0)
        return {"id": cid, "type": ctype, "ok": total == 0, "detail": f"{total} file(s)"}

    if ctype in {"reply_contains_all", "reply_contains_any", "reply_not_contains_any"}:
        case_sensitive = bool(check.get("case_sensitive"))
        terms = _terms(check)
        text = _haystack(execution, case_sensitive=case_sensitive)
        hits = [term for term in terms if _needle(term, case_sensitive=case_sensitive) in text]
        if ctype == "reply_contains_all":
            ok = bool(terms) and len(hits) == len(terms)
        elif ctype == "reply_contains_any":
            ok = bool(hits)
        else:
            ok = not hits
        missing = [term for term in terms if term not in hits]
        detail = f"hits={hits[:5]} missing={missing[:5]}"
        return {"id": cid, "type": ctype, "ok": ok, "detail": detail}

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
