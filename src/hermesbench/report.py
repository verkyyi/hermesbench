"""Render a HermesBench run as a score-only human report."""

from __future__ import annotations


def _fmt_delta(cur, prev) -> str:
    if cur is None or prev is None:
        return ""
    d = cur - prev
    if abs(d) < 0.005:
        return "  (=)"
    return f"  ({'+' if d >= 0 else ''}{d:.1f})"


_AXIS_LABELS = {
    "task_fulfillment": "ful",
    "evidence_truthfulness": "evd",
    "outcome_reached": "out",
    "runtime_scope_safety": "safe",
    "communication_quality": "com",
    "closure": "out",
    "artifact_correctness": "evd",
    "stability": "stb",
    "scope_discipline": "scp",
    "responsiveness": "rsp",
    "appropriateness": "ful",
    "coherence": "clr",
}


def _axis_items(axes: dict):
    seen = set()
    for key in (
        "task_fulfillment", "evidence_truthfulness", "outcome_reached",
        "runtime_scope_safety", "responsiveness", "communication_quality",
        "closure", "artifact_correctness", "stability", "scope_discipline",
        "appropriateness", "coherence",
    ):
        if key not in axes or not isinstance(axes[key], (int, float)):
            continue
        label = _AXIS_LABELS[key]
        if label in seen:
            continue
        seen.add(label)
        yield label, axes[key]


def render(report: dict, previous: dict | None = None) -> str:
    prev_suites = {s["id"]: s for s in (previous or {}).get("suites", [])}
    h = report["harness"]
    surface = ((h.get("profile_snapshot") or {}).get("execution_surface") or {})
    surface_label = surface.get("label") or "unknown"
    lines = [
        "=" * 64,
        "HERMESBENCH  " + report["run_id"],
        "=" * 64,
        f"ts={report['ts']}  suites_ran={report['suites_ran']}",
        f"harness: git={(h.get('git_sha') or '?')[:10]} "
        f"model={h.get('model_id') or '?'} "
        f"profile={(h.get('profile_hash') or '?')[:10]} "
        f"surface={surface_label}",
        "",
    ]

    overall = report.get("overall_score")
    prev_overall = (previous or {}).get("overall_score")
    overall_str = "n/a" if overall is None else f"{overall:.1f}"
    lines.append(f"OVERALL  {overall_str}{_fmt_delta(overall, prev_overall)}")
    lines.append("")
    lines.append(f"  {'suite':<22}{'mode':<10}{'score':>7}  axes")
    lines.append("  " + "-" * 64)

    for s in report["suites"]:
        prev = prev_suites.get(s["id"])
        score = s.get("score")
        score_str = "  -  " if score is None else f"{score:6.1f}"
        delta = _fmt_delta(score, (prev or {}).get("score")) if prev else ""
        axes = (s.get("metrics") or {}).get("axis_scores") or {}
        axis_str = " ".join(
            f"{name}={val:.0f}"
            for name, val in _axis_items(axes)
        )
        lines.append(
            f"  {s['id']:<22}{s.get('mode',''):<10}"
            f"{score_str:>7}{delta}  {axis_str}"
        )

    notes = []
    for s in report["suites"]:
        if s.get("skipped"):
            notes.append(f"  - {s['id']}: skipped ({s.get('skip_reason')})")
        elif s.get("error"):
            notes.append(f"  - {s['id']}: ERROR {s.get('error')}")
    if notes:
        lines.append("")
        lines.append("notes:")
        lines.extend(notes)

    return "\n".join(lines)
