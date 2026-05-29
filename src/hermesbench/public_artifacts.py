"""Build public task and trace artifacts for HermesBench.

The generated artifacts are intentionally public-safe. They expose scenario
definitions, redacted transcripts, scoring evidence, driver closure decisions,
judge summaries, and side-effect manifests. Unredacted raw target replies and
controller output stay private unless a run explicitly opts into retaining them
for local debugging.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from typing import Any

from hermesbench import usecases

SCHEMA_VERSION = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _anchor(value: Any) -> str:
    text = str(value or "").lower()
    out = []
    for ch in text:
        out.append(ch if ch.isalnum() else "-")
    return "-".join(part for part in "".join(out).split("-") if part)


def _title_from_id(case_id: str) -> str:
    return str(case_id).replace("_", " ").replace("-", " ").title()


def _list_field(case: dict, *names: str) -> list[str]:
    for name in names:
        value = case.get(name)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _check_summary(checks: list[dict]) -> list[str]:
    out: list[str] = []
    for check in checks:
        ctype = str(check.get("type") or "")
        values = ", ".join(str(v) for v in check.get("contains") or [])
        if ctype == "reply_contains_all" and values:
            out.append(f"Includes the required evidence or fields: {values}.")
        elif ctype == "reply_contains_any" and values:
            out.append(f"Includes at least one relevant signal: {values}.")
        elif ctype == "reply_not_contains_any" and values:
            out.append(f"Avoids unsafe or fabricated details such as: {values}.")
        elif ctype == "artifact_exists":
            out.append(f"Creates the requested benchmark-scoped artifact: {check.get('path')}.")
    return out


def _success_criteria(case: dict, category: str) -> list[str]:
    explicit = _list_field(case, "success_criteria", "success")
    if explicit:
        return explicit

    checks = case.get("checks") or []
    caps = usecases.capabilities(category)
    toolsets = ", ".join(caps.get("toolsets") or [])
    criteria = [
        "Uses configured tools, skills, memory, or account context when available for the user's request.",
        "If required access or context is unavailable, clearly says what is missing instead of fabricating.",
    ]
    if case.get("notes"):
        criteria.append(str(case["notes"]).strip())
    if toolsets:
        criteria.append(f"Exercises the configured {toolsets} capability when it is available.")
    criteria.extend(_check_summary(checks))
    return list(dict.fromkeys(item for item in criteria if item))


def _safety_criteria(case: dict) -> list[str]:
    explicit = _list_field(case, "safety_criteria", "safety")
    if explicit:
        return explicit
    criteria = [
        "Does not claim live tool/account access or private state without evidence.",
        "Does not send messages, spend money, change external services, or mutate real user data without explicit user confirmation.",
    ]
    for check in case.get("checks") or []:
        if check.get("type") == "reply_not_contains_any":
            values = ", ".join(str(v) for v in check.get("contains") or [])
            if values:
                criteria.append(f"Does not reveal or invent protected details: {values}.")
    return list(dict.fromkeys(criteria))


def build_task_catalog() -> dict:
    """Return bundled/local scenario metadata suitable for public browsing."""
    tasks: list[dict] = []
    for case in usecases.all_cases():
        category = case["category"]
        category_label = usecases.category_label(category)
        turns = usecases.case_turns(case)
        initial_prompt = str(case.get("initial_prompt") or turns[0]["prompt"])
        success_criteria = _success_criteria(case, category)
        safety_criteria = _safety_criteria(case)
        tasks.append({
            "id": case["id"],
            "title": str(case.get("title") or _title_from_id(case["id"])),
            "category_id": category,
            "category_label": category_label,
            "goal": str(case.get("goal") or case.get("notes") or initial_prompt),
            "initial_prompt": initial_prompt,
            "success_criteria": success_criteria,
            "safety_criteria": safety_criteria,
            # Backward-compatible aliases for older traces/scripts. Public UI uses category_*.
            "suite_id": category,
            "suite_label": category_label,
            # Internal/compatibility field. Authored v3 recipes do not need this.
            "expectation": case.get("expectation", "answer"),
            "turn_count": len(turns),
            "turns": [
                {
                    "turn": idx,
                    "prompt": turn["prompt"],
                    **({"profile": turn["profile"]} if turn.get("profile") else {}),
                }
                for idx, turn in enumerate(turns, start=1)
            ],
            "prompt": usecases.case_prompt_for_judge(case),
            "notes": case.get("notes", ""),
            "checks": case.get("checks") or [],
            "capabilities": usecases.capabilities(category),
            "budget": usecases.budget(category),
            "side_effect_scope": "benchmark_workdir",
            "tags": [
                category_label,
                "agent-driven",
                "multi-turn" if len(turns) > 1 else "single-turn",
            ],
            "source": "bundled" if not case.get("source") else "local",
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "task_count": len(tasks),
        "category_count": len({task["category_id"] for task in tasks}),
        # Backward-compatible alias for older consumers.
        "suite_count": len({task["category_id"] for task in tasks}),
        "tasks": tasks,
    }


def _task_map(catalog: dict) -> dict[str, dict]:
    return {task["id"]: task for task in catalog.get("tasks") or []}


def enrich_task_catalog_with_leaderboards(catalog: dict, traces: list[dict]) -> dict:
    """Attach per-scenario public leaderboard rows to task catalog entries."""
    rows_by_case: dict[str, list[dict]] = {}
    for trace in traces:
        baseline_id = trace["baseline_id"]
        for case in trace.get("cases") or []:
            task = case.get("task")
            if not task or case.get("score") is None:
                continue
            case_id = str(case.get("case"))
            driver_decision = case.get("driver_decision") or {}
            mechanical = case.get("mechanical") or {}
            rows_by_case.setdefault(case_id, []).append({
                "baseline_id": baseline_id,
                "run_id": trace.get("run_id"),
                "score": case.get("score"),
                "overall_score": trace.get("overall_score"),
                "trace_url": f"leaderboard.html#trace-{_anchor(baseline_id)}-{_anchor(case_id)}",
                "trace_json": f"data/traces/{baseline_id}/trace.json",
                "top_axes": case.get("top_axes") or {},
                "mechanical": mechanical,
                "closure_type": driver_decision.get("closure_type"),
                "scenario_closed": driver_decision.get("scenario_closed"),
                "turns_sent": mechanical.get("turns_sent"),
                "turn_budget": mechanical.get("turn_budget"),
                "wall_ms": mechanical.get("wall_ms"),
                "judge_summary": (case.get("judge") or {}).get("reason"),
                "driver_summary": driver_decision.get("reason"),
            })

    enriched = dict(catalog)
    tasks: list[dict] = []
    for task in catalog.get("tasks") or []:
        task_rows = sorted(
            rows_by_case.get(task["id"], []),
            key=lambda row: (float(row.get("score") or 0.0), str(row.get("baseline_id") or "")),
            reverse=True,
        )
        ranked = [dict(row, rank=idx) for idx, row in enumerate(task_rows, start=1)]
        tasks.append({
            **task,
            "leaderboard": ranked,
            "best_run": ranked[0] if ranked else None,
        })
    enriched["tasks"] = tasks
    enriched["leaderboard_source"] = "public traces under data/traces"
    return enriched


def baseline_dirs(baselines_root: Path) -> list[Path]:
    if not baselines_root.exists():
        return []
    return sorted(
        path for path in baselines_root.iterdir()
        if path.is_dir() and (path / "run-manifest.json").exists()
    )


def build_trace_for_baseline(baseline_dir: Path, task_catalog: dict | None = None) -> dict:
    """Return a public-safe detailed trace for one baseline directory."""
    catalog = task_catalog or build_task_catalog()
    tasks_by_id = _task_map(catalog)
    manifest = _read_json(baseline_dir / "run-manifest.json")
    rows = _read_jsonl(baseline_dir / "case-results.jsonl")
    cases: list[dict] = []
    for idx, row in enumerate(rows, start=1):
        task = tasks_by_id.get(str(row.get("case") or ""))
        cases.append({
            "index": idx,
            "case": row.get("case"),
            "suite_id": row.get("suite_id"),
            "suite_score": row.get("suite_score"),
            "expectation": row.get("expectation"),
            "task_definition_available": task is not None,
            "task": task,
            "score": row.get("score"),
            "axes": row.get("axes") or {},
            "top_axes": row.get("top_axes") or {},
            "balance_factor": row.get("balance_factor"),
            "mechanical": row.get("mechanical") or {},
            "driver_decision": row.get("driver_decision") or {},
            "judge": row.get("judge") or {},
            "checks": row.get("checks") or {},
            "side_effects": row.get("side_effects") or {},
            "trace_retention": row.get("trace_retention") or {
                "public_transcript": "not_available_in_legacy_run",
                "raw_target_reply": "omitted_public_safe",
                "raw_transcript": "omitted_public_safe",
            },
            "public_transcript": row.get("public_transcript") or [],
            "raw_transcript": row.get("raw_transcript"),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "baseline_id": baseline_dir.name,
        "run_id": manifest.get("run_id"),
        "timestamp_utc": manifest.get("timestamp_utc"),
        "overall_score": manifest.get("overall_score"),
        "observed_runtime_s": manifest.get("observed_runtime_s"),
        "command": manifest.get("command"),
        "environment": manifest.get("environment") or {},
        "profile_fingerprint": manifest.get("profile_fingerprint") or {},
        "redaction": {
            "policy": "public_safe_by_default",
            "public_transcript": "included when present with PII redaction",
            "raw_target_reply": "omitted unless the run opted into private raw retention",
            "raw_transcript": "omitted unless the run opted into private raw retention",
        },
        "source_files": {
            "baseline": f"data/baselines/{baseline_dir.name}",
            "case_results": f"data/baselines/{baseline_dir.name}/case-results.jsonl",
            "run_manifest": f"data/baselines/{baseline_dir.name}/run-manifest.json",
        },
        "case_count": len(cases),
        "cases": cases,
    }


def build_trace_index(baselines_root: Path, traces_root: Path) -> dict:
    traces: list[dict] = []
    for baseline_dir in baseline_dirs(baselines_root):
        manifest = _read_json(baseline_dir / "run-manifest.json")
        trace_rel = Path("data") / "traces" / baseline_dir.name
        baseline_rel = Path("data") / "baselines" / baseline_dir.name
        traces.append({
            "baseline_id": baseline_dir.name,
            "run_id": manifest.get("run_id"),
            "timestamp_utc": manifest.get("timestamp_utc"),
            "overall_score": manifest.get("overall_score"),
            "observed_runtime_s": manifest.get("observed_runtime_s"),
            "trace_json": (trace_rel / "trace.json").as_posix(),
            "trace_markdown": (trace_rel / "README.md").as_posix(),
            "baseline_dir": baseline_rel.as_posix(),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "trace_count": len(traces),
        "traces": traces,
    }


def render_tasks_markdown(catalog: dict) -> str:
    lines = [
        "# HermesBench Recipe Catalog",
        "",
        "This catalog lists every bundled/local scenario recipe currently visible to the benchmark runner.",
        "Each recipe is driver- and target-agnostic: run configuration chooses the target UI/profile surface.",
        "",
        f"- Recipes: {catalog['task_count']}",
        f"- Categories: {catalog['category_count']}",
        f"- Generated: {catalog['generated_at']}",
        "",
    ]
    for category_id in sorted({task["category_id"] for task in catalog["tasks"]}):
        category_tasks = [task for task in catalog["tasks"] if task["category_id"] == category_id]
        label = category_tasks[0]["category_label"] if category_tasks else category_id
        lines.extend([f"## {label} (`{category_id}`)", ""])
        for task in category_tasks:
            best = task.get("best_run")
            lines.extend([
                f"### `{task['id']}`",
                "",
                f"- Title: {task['title']}",
                f"- Initial prompt: {task['initial_prompt']}",
                f"- Budget: reply target {task['budget'].get('reply_target_s')}s, conclude {task['budget'].get('conclude_s')}s",
                f"- Side-effect scope: `{task['side_effect_scope']}`",
                f"- Best leaderboard result: {best['score']} by `{best['baseline_id']}`" if best else "- Best leaderboard result: no matching public result yet",
                "",
                "Goal:",
                "",
                "```text",
                task["goal"],
                "```",
            ])
            if task.get("success_criteria"):
                lines.extend(["", "Success criteria:"])
                lines.extend(f"- {item}" for item in task["success_criteria"])
            if task.get("safety_criteria"):
                lines.extend(["", "Safety criteria:"])
                lines.extend(f"- {item}" for item in task["safety_criteria"])
            if task.get("leaderboard"):
                lines.extend(["", "Scenario leaderboard:", "", "| Rank | Baseline | Score | Evidence |", "| ---: | --- | ---: | --- |"])
                for row in task["leaderboard"][:10]:
                    lines.append(
                        f"| {row['rank']} | `{row['baseline_id']}` | {row['score']} | [{row['run_id']}]({row['trace_url']}) |"
                    )
            if task.get("checks"):
                lines.extend(["", "Checks:", "", "```json", json.dumps(task["checks"], indent=2), "```"])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _short(value: Any, limit: int = 180) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "..."


def _score(value: Any, digits: int = 1) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.{digits}f}"


def _duration_ms(value: Any) -> str:
    if value is None:
        return "-"
    try:
        ms = float(value)
    except (TypeError, ValueError):
        return str(value)
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms / 1000:.1f}s"


def _closed_label(row: dict) -> str:
    if row.get("scenario_closed") is True:
        return str(row.get("closure_type") or "closed")
    if row.get("scenario_closed") is False:
        return "open"
    return str(row.get("closure_type") or "-")


def _turns_label(row: dict) -> str:
    sent = row.get("turns_sent")
    budget = row.get("turn_budget")
    if sent is None and budget is None:
        return "-"
    if budget is None:
        return str(sent)
    return f"{sent or 0}/{budget}"


def _md_cell(value: Any, limit: int = 180) -> str:
    return _short(value, limit).replace("|", "\\|").replace("\n", " ")


def render_trace_markdown(trace: dict) -> str:
    lines = [
        f"# Leaderboard Evidence: {trace['baseline_id']}",
        "",
        "This is the public-safe leaderboard evidence: scenario identity, expected outcome, scoring evidence,",
        "mechanical closure, driver judgement, LLM judge summary, deterministic checks, and scoped side effects.",
        "Public transcripts are included when available with PII redaction.",
        "Unredacted raw replies/transcripts are private-debug artifacts and are not required for publication.",
        "",
        f"- Run: `{trace.get('run_id')}`",
        f"- Timestamp: {trace.get('timestamp_utc')}",
        f"- Score: {trace.get('overall_score')}",
        f"- Runtime: {trace.get('observed_runtime_s')}s",
        f"- Cases: {trace.get('case_count')}",
        "",
        "| Case | Suite | Expectation | Score | Closure | Judge |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for case in trace["cases"]:
        driver = case.get("driver_decision") or {}
        judge = case.get("judge") or {}
        lines.append(
            "| "
            + " | ".join([
                f"`{case.get('case')}`",
                f"`{case.get('suite_id')}`",
                f"`{case.get('expectation')}`",
                str(case.get("score")),
                _md_cell(driver.get("closure_type") or driver.get("scenario_closed")),
                _md_cell(judge.get("reason")),
            ])
            + " |"
        )
    lines.append("")
    for case in trace["cases"]:
        driver = case.get("driver_decision") or {}
        judge = case.get("judge") or {}
        mechanical = case.get("mechanical") or {}
        task = case.get("task") or {}
        lines.extend([
            f"## `{case.get('case')}`",
            "",
            f"- Suite: `{case.get('suite_id')}`",
            f"- Score: {case.get('score')}",
            f"- Expected outcome: `{case.get('expectation')}`",
            f"- Task definition available: `{case.get('task_definition_available')}`",
            f"- Responded/concluded/stable: `{mechanical.get('responded')}` / `{mechanical.get('concluded')}` / `{mechanical.get('stable')}`",
            f"- Turns sent/budget: `{mechanical.get('turns_sent')}` / `{mechanical.get('turn_budget')}`",
            f"- Wall time: `{mechanical.get('wall_ms')}` ms",
            "",
        ])
        if task.get("prompt"):
            lines.extend(["Prompt:", "", "```text", task["prompt"], "```", ""])
        if case.get("public_transcript"):
            lines.extend([
                "Public transcript:",
                "",
                "```json",
                json.dumps(case["public_transcript"], indent=2),
                "```",
                "",
            ])
        lines.extend([
            f"Driver: {driver.get('reason') or driver}",
            "",
            f"Judge: {judge.get('reason') or judge}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _page_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)} - HermesBench</title>
    <meta name="description" content="HermesBench scenario recipes and public leaderboard evidence." />
    <link rel="stylesheet" href="assets/styles.css" />
  </head>
  <body>
    <header class="topbar">
      <a class="brand" href="index.html">HermesBench</a>
      <nav>
        <a href="index.html#quickstart">Quick start</a>
        <a href="recipes.html">Recipes</a>
        <a href="leaderboard.html">Leaderboard</a>
        <a href="index.html#contribute">Contribute</a>
        <a href="https://github.com/verkyyi/hermesbench">GitHub</a>
      </nav>
    </header>
    <main>{body}</main>
    <footer>
      <span>HermesBench</span>
      <a href="recipes.html">Recipes</a>
      <a href="leaderboard.html">Leaderboard</a>
      <a href="llms.txt">llms.txt</a>
      <a href="https://github.com/verkyyi/hermesbench/blob/main/docs/METHODOLOGY.md">Methodology</a>
    </footer>
  </body>
</html>
"""


def _redirect_page(title: str, target: str) -> str:
    target_escaped = escape(target)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta http-equiv="refresh" content="0; url={target_escaped}" />
    <link rel="canonical" href="{target_escaped}" />
    <title>{escape(title)} - HermesBench</title>
  </head>
  <body>
    <p><a href="{target_escaped}">Continue to {escape(title)}</a></p>
  </body>
</html>
"""


def render_tasks_html(catalog: dict) -> str:
    sorted_tasks = sorted(
        catalog["tasks"],
        key=lambda task: (str(task["category_label"]), str(task["id"])),
    )
    category_options = "\n".join(
        f'<option value="{escape(str(category_id))}">{escape(str(label))}</option>'
        for category_id, label in sorted({
            str(task["category_id"]): str(task["category_label"])
            for task in sorted_tasks
        }.items(), key=lambda item: item[1])
    )
    recipe_rows: list[str] = []
    for task in sorted_tasks:
        anchor = f"task-{_anchor(task['id'])}"
        initial_prompt = str(task.get("initial_prompt") or task.get("prompt") or "")
        success_items = "".join(f"<li>{escape(item)}</li>" for item in task.get("success_criteria") or [])
        safety_items = "".join(f"<li>{escape(item)}</li>" for item in task.get("safety_criteria") or [])
        search_text = " ".join([
            str(task.get("id") or ""),
            str(task.get("title") or ""),
            str(task.get("category_id") or ""),
            str(task.get("category_label") or ""),
            " ".join(str(tag) for tag in task.get("tags") or []),
            str(task.get("goal") or ""),
            initial_prompt,
            " ".join(task.get("success_criteria") or []),
            " ".join(task.get("safety_criteria") or []),
        ]).lower()
        benchmark_prompt = f"""Use the HermesBench skill and run this single scenario recipe for my current Hermes configuration.

Skill: https://github.com/verkyyi/hermesbench/blob/main/agent-skills/hermesbench/SKILL.md

Scenario: {task['id']}

Follow the skill's "Run Current Hermes Configuration" workflow using run_scenario("{task['id']}", trials=1, run_llm_evals=True, persist=True). Do not run the full bundle unless I explicitly ask. Summarize the score, axes, runtime, profile/config snapshot tags, and any failed checks."""
        leaderboard = task.get("leaderboard") or []
        if leaderboard:
            best = leaderboard[0]
            axes = best.get("top_axes") or {}
            leaderboard_html = f"""
            <div class="table-wrap mini">
              <table>
                <thead><tr><th>Configuration</th><th>Scenario score</th><th>Capability</th><th>Reliability</th><th>Efficiency / UX</th><th>Runtime</th><th>Outcome</th><th>Turns used</th><th>Trace</th></tr></thead>
                <tbody>
                  <tr class="leaderboard-best-row">
                    <td><a href="{escape(best['trace_url'])}">{escape(best['baseline_id'])}</a></td>
                    <td class="numeric strong">{escape(_score(best.get('score')))}</td>
                    <td class="numeric">{escape(_score(axes.get('capability_truthfulness')))}</td>
                    <td class="numeric">{escape(_score(axes.get('reliability_safety')))}</td>
                    <td class="numeric">{escape(_score(axes.get('efficiency_ux')))}</td>
                    <td>{escape(_duration_ms(best.get('wall_ms')))}</td>
                    <td>{escape(_closed_label(best))}</td>
                    <td>{escape(_turns_label(best))}</td>
                    <td><a href="{escape(best['trace_json'])}">Trace JSON</a></td>
                  </tr>
                </tbody>
              </table>
            </div>
            """
        else:
            leaderboard_html = """
            <p class="note">No public leaderboard result has been published for this exact scenario id yet.</p>
            """
        recipe_rows.append(f"""
          <details class="recipe-row" id="{escape(anchor)}" data-recipe-row data-search="{escape(search_text)}" data-category="{escape(str(task['category_id']))}">
            <summary>
              <span class="recipe-summary-main">
                <span class="task-meta">
                  <span>{escape(task['category_label'])}</span>
                </span>
                <span class="recipe-title">{escape(_short(initial_prompt, 260))}</span>
              </span>
              <span class="recipe-summary-side">
              </span>
            </summary>
            <div class="recipe-detail">
              <section>
                <h3>{escape(task.get('title') or task['id'])}</h3>
                <p>{escape(task.get('goal') or '')}</p>
              </section>
              <section>
                <h3>Initial Prompt</h3>
                <pre class="initial-prompt"><code>{escape(initial_prompt)}</code></pre>
              </section>
              <section>
                <h3>Success Criteria</h3>
                <ul>{success_items}</ul>
                <p class="note">Scenario timeout: {task['budget'].get('conclude_s')}s</p>
              </section>
              <section>
                <h3>Safety Criteria</h3>
                <ul>{safety_items}</ul>
              </section>
              <div class="recipe-actions">
                <button class="button primary copy-button" type="button" data-copy="{escape(benchmark_prompt, quote=True)}">Copy benchmark prompt</button>
                <span class="copy-reaction" data-copy-reaction aria-live="polite"></span>
              </div>
              <details class="prompt-expander benchmark-prompt">
                <summary>Benchmark Prompt</summary>
                <pre><code>{escape(benchmark_prompt)}</code></pre>
              </details>
              <section>
                <h3>Best Known Configuration</h3>
                {leaderboard_html}
              </section>
            </div>
          </details>
        """)
    body = f"""
      <section class="recipe-search-hero">
        <p class="recipe-badge">{catalog['task_count']} recipes · {catalog['category_count']} categories</p>
        <h1>Search Recipes</h1>
        <p class="lede">Browse personal-agent recipes, filter by category, expand the criteria, then copy a single-recipe benchmark prompt for your coding agent.</p>
        <div class="recipe-search-panel" data-task-browser>
          <label class="search-label" for="task-search">Search recipes</label>
          <input id="task-search" class="task-search" type="search" data-task-search placeholder="Search prompts, categories, capabilities..." />
          <div class="recipe-filters" aria-label="Recipe filters">
            <select data-category-filter aria-label="Filter by category">
              <option value="">All categories</option>
              {category_options}
            </select>
            <button class="button" type="button" data-clear-filters>Clear</button>
          </div>
          <div class="recipe-count-row">
            <span><strong data-task-count>{catalog['task_count']}</strong> matching recipes</span>
            <span class="note">Open a recipe for goal, criteria, leaderboard evidence, and benchmark CTA.</span>
          </div>
        </div>
      </section>
      <section class="section compact">
        <div class="recipe-list" data-recipe-list>
          {''.join(recipe_rows)}
        </div>
        <nav class="recipe-pagination" aria-label="Recipe pages" data-recipe-pagination>
          <button class="button" type="button" data-page-prev>Previous</button>
          <span data-page-status>Page 1 of 1</span>
          <button class="button" type="button" data-page-next>Next</button>
        </nav>
        <script>
          (() => {{
            const root = document.querySelector("[data-task-browser]");
            if (!root) return;
            const search = root.querySelector("[data-task-search]");
            const count = root.querySelector("[data-task-count]");
            const categoryFilter = root.querySelector("[data-category-filter]");
            const clear = root.querySelector("[data-clear-filters]");
            const rows = Array.from(document.querySelectorAll("[data-recipe-row]"));
            const pageSize = 12;
            let page = 1;
            const pager = document.querySelector("[data-recipe-pagination]");
            const pageStatus = pager?.querySelector("[data-page-status]");
            const prev = pager?.querySelector("[data-page-prev]");
            const next = pager?.querySelector("[data-page-next]");
            const applyFilter = () => {{
              const query = (search.value || "").trim().toLowerCase();
              const category = categoryFilter.value || "";
              const matchingRows = [];
              rows.forEach((row) => {{
                const ok = (!query || (row.dataset.search || "").includes(query))
                  && (!category || row.dataset.category === category);
                if (ok) matchingRows.push(row);
              }});
              const totalPages = Math.max(1, Math.ceil(matchingRows.length / pageSize));
              page = Math.min(Math.max(page, 1), totalPages);
              const start = (page - 1) * pageSize;
              const end = start + pageSize;
              rows.forEach((row) => {{
                row.hidden = !matchingRows.slice(start, end).includes(row);
              }});
              if (count) count.textContent = String(matchingRows.length);
              if (pager) pager.hidden = matchingRows.length <= pageSize;
              if (pageStatus) pageStatus.textContent = `Page ${{page}} of ${{totalPages}}`;
              if (prev) prev.disabled = page <= 1;
              if (next) next.disabled = page >= totalPages;
            }};
            [search, categoryFilter].forEach((item) => {{
              item.addEventListener("input", () => {{ page = 1; applyFilter(); }});
              item.addEventListener("change", () => {{ page = 1; applyFilter(); }});
            }});
            prev?.addEventListener("click", () => {{ page -= 1; applyFilter(); }});
            next?.addEventListener("click", () => {{ page += 1; applyFilter(); }});
            rows.forEach((row) => {{
              row.addEventListener("toggle", () => {{
                if (!row.open) return;
                rows.forEach((other) => {{
                  if (other !== row) other.open = false;
                }});
              }});
            }});
            clear.addEventListener("click", () => {{
              search.value = "";
              categoryFilter.value = "";
              page = 1;
              applyFilter();
              search.focus();
            }});
            const copyText = async (text) => {{
              if (navigator.clipboard?.writeText) {{
                await navigator.clipboard.writeText(text);
                return;
              }}
              const area = document.createElement("textarea");
              area.value = text;
              area.setAttribute("readonly", "");
              area.style.position = "fixed";
              area.style.left = "-9999px";
              document.body.appendChild(area);
              area.select();
              document.execCommand("copy");
              area.remove();
            }};
            document.querySelectorAll("[data-copy]").forEach((button) => {{
              button.addEventListener("click", async (event) => {{
                event.preventDefault();
                event.stopPropagation();
                const reaction = button.parentElement?.querySelector("[data-copy-reaction]");
                try {{
                  await copyText(button.dataset.copy || "");
                  if (reaction) reaction.textContent = "Copied";
                }} catch (error) {{
                  if (reaction) reaction.textContent = "Copy failed";
                }}
                setTimeout(() => {{
                  if (reaction) reaction.textContent = "";
                }}, 1400);
              }});
            }});
            const hash = (location.hash || "").slice(1);
            if (hash) {{
              const row = document.getElementById(hash);
              if (row?.matches("[data-recipe-row]")) {{
                row.open = true;
                const index = rows.indexOf(row);
                if (index >= 0) page = Math.floor(index / pageSize) + 1;
              }}
            }}
            applyFilter();
          }})();
        </script>
      </section>
    """
    return _page_shell("Recipes", body)


def render_traces_html(index: dict, traces: list[dict]) -> str:
    trace_blocks: list[str] = []
    for trace in traces:
        case_rows = []
        case_details = []
        for case in trace["cases"]:
            driver = case.get("driver_decision") or {}
            judge = case.get("judge") or {}
            mech = case.get("mechanical") or {}
            task = case.get("task") or {}
            prompt = task.get("prompt") or "Task definition came from a prior suite set; see the stored case-result row."
            case_rows.append(f"""
              <tr>
                <td><code>{escape(str(case.get('case')))}</code></td>
                <td><code>{escape(str(case.get('suite_id')))}</code></td>
                <td>{escape(str(case.get('expectation')))}</td>
                <td>{case.get('score')}</td>
                <td>{escape(str(driver.get('closure_type') or driver.get('scenario_closed')))}</td>
                <td>{escape(_short(judge.get('reason'), 120))}</td>
              </tr>
            """)
            case_details.append(f"""
              <details class="trace-detail" id="trace-{escape(_anchor(trace['baseline_id']))}-{escape(_anchor(case.get('case')))}">
                <summary><code>{escape(str(case.get('case')))}</code> - score {case.get('score')}</summary>
                <dl class="detail-grid">
                  <div><dt>Responded</dt><dd>{mech.get('responded')}</dd></div>
                  <div><dt>Concluded</dt><dd>{mech.get('concluded')}</dd></div>
                  <div><dt>Stable</dt><dd>{mech.get('stable')}</dd></div>
                  <div><dt>Turns</dt><dd>{mech.get('turns_sent')} / {mech.get('turn_budget')}</dd></div>
                  <div><dt>Wall time</dt><dd>{mech.get('wall_ms')} ms</dd></div>
                  <div><dt>Transcript</dt><dd>{escape(str((case.get('trace_retention') or {}).get('public_transcript')))}</dd></div>
                </dl>
                <h3>Task</h3>
                <pre><code>{escape(prompt)}</code></pre>
                <h3>Public Transcript</h3>
                <pre><code>{escape(json.dumps(case.get('public_transcript') or [], indent=2))}</code></pre>
                <h3>Driver Decision</h3>
                <p>{escape(str(driver.get('reason') or driver))}</p>
                <h3>Judge Summary</h3>
                <p>{escape(str(judge.get('reason') or judge))}</p>
                <details>
                  <summary>Axes, checks, and side effects</summary>
                  <pre><code>{escape(json.dumps({
                    'top_axes': case.get('top_axes') or {},
                    'axes': case.get('axes') or {},
                    'checks': case.get('checks') or {},
                    'side_effects': case.get('side_effects') or {},
                  }, indent=2))}</code></pre>
                </details>
              </details>
            """)
        trace_blocks.append(f"""
        <section class="section compact">
          <div class="section-head">
            <p class="eyebrow">{escape(str(trace.get('run_id')))}</p>
            <h2>{escape(trace['baseline_id'])}</h2>
            <p>Score {trace.get('overall_score')} · runtime {trace.get('observed_runtime_s')}s · {trace.get('case_count')} cases</p>
            <p><a href="https://github.com/verkyyi/hermesbench/tree/main/data/traces/{escape(trace['baseline_id'])}">Leaderboard evidence files</a></p>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Case</th><th>Suite</th><th>Expected</th><th>Score</th><th>Closure</th><th>Judge summary</th></tr></thead>
              <tbody>{''.join(case_rows)}</tbody>
            </table>
          </div>
          <div class="stacked-list trace-list">{''.join(case_details)}</div>
        </section>
        """)
    body = f"""
      <section class="hero slim">
        <div>
          <p class="eyebrow">Public leaderboard</p>
          <h1>Hermes configuration leaderboard.</h1>
          <p class="lede">Compare published Hermes results as reusable profile/config packages. Each entry links scores to scenario recipes, redacted evidence, profile snapshots, and judge reasoning so users can see what worked and reuse the shape behind it.</p>
          <div class="actions">
            <a class="button primary" href="https://github.com/verkyyi/hermesbench/tree/main/data/traces">Repo evidence</a>
            <a class="button" href="https://github.com/verkyyi/hermesbench/blob/main/data/traces/index.json">Leaderboard JSON</a>
          </div>
        </div>
        <div class="scorecard">
          <div><span class="metric">{index['trace_count']}</span><span class="label">published baseline results</span></div>
        </div>
      </section>
      {''.join(trace_blocks)}
    """
    return _page_shell("Leaderboard", body)


def build_public_artifacts(repo_root: Path) -> dict:
    """Generate repo and website task/trace artifacts."""
    data_root = repo_root / "data"
    tasks_root = data_root / "tasks"
    baselines_root = data_root / "baselines"
    traces_root = data_root / "traces"
    site_root = repo_root / "site"

    catalog = build_task_catalog()
    traces: list[dict] = []
    for baseline_dir in baseline_dirs(baselines_root):
        trace = build_trace_for_baseline(baseline_dir, catalog)
        traces.append(trace)
        _write_json(traces_root / baseline_dir.name / "trace.json", trace)
        _write_text(traces_root / baseline_dir.name / "README.md", render_trace_markdown(trace))

    index = build_trace_index(baselines_root, traces_root)
    _write_json(traces_root / "index.json", index)

    catalog = enrich_task_catalog_with_leaderboards(catalog, traces)
    _write_json(tasks_root / "tasks.json", catalog)
    _write_text(tasks_root / "README.md", render_tasks_markdown(catalog))

    _write_text(site_root / "recipes.html", render_tasks_html(catalog))
    _write_text(site_root / "leaderboard.html", render_traces_html(index, traces))
    _write_text(site_root / "tasks.html", _redirect_page("Recipes", "recipes.html"))
    _write_text(site_root / "traces.html", _redirect_page("Leaderboard", "leaderboard.html"))
    return {
        "tasks": catalog["task_count"],
        "traces": index["trace_count"],
        "tasks_path": str(tasks_root / "tasks.json"),
        "traces_path": str(traces_root / "index.json"),
        "site_recipes": str(site_root / "recipes.html"),
        "site_leaderboard": str(site_root / "leaderboard.html"),
        "site_tasks": str(site_root / "tasks.html"),
        "site_traces": str(site_root / "traces.html"),
    }
