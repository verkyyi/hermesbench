"""Build public task and trace artifacts for HermesBench.

The generated artifacts are intentionally public-safe. They expose scenario
definitions, redacted transcripts, scoring evidence, driver closure decisions,
judge summaries, and side-effect manifests. Unredacted raw target replies and
controller output stay private unless a run explicitly opts into retaining them
for local debugging.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re
import shutil
from typing import Any

import yaml

from hermesbench import usecases

SCHEMA_VERSION = 4
TRACE_PAGE = "traces.html"
LEGACY_LEADERBOARD_PAGE = "leaderboard.html"
_PUBLIC_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PUBLIC_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)")
_PUBLIC_TOKEN_RE = re.compile(r"\b(?:sk|ghp|gho|xoxb|xoxp|AKIA)[A-Za-z0-9_\-]{12,}\b", re.IGNORECASE)
_PUBLIC_LOCAL_PATH_RE = re.compile(r"(?<![\w.-])(?:~/(?:\.hermes|\.config|\.ssh)[^,\s;:'\")]*|/Users/[^,\s;:'\")]+|/home/[^,\s;:'\")]+|/tmp/[^,\s;:'\")]+|/var/folders/[^,\s;:'\")]+|/private/var/folders/[^,\s;:'\")]+)")
_PUBLIC_ENV_FILE_RE = re.compile(r"(?<![\w.-])\.env(?![\w.-])")
_PUBLIC_SECRET_LABEL_RE = re.compile(r"(?i)\b(passcode|password|meeting id)\s*[:#]?\s*[A-Za-z0-9._-]+")
_PUBLIC_SENSITIVE_URL_RE = re.compile(r"https?://[^\s<>)\]}\"']+")
_PUBLIC_MONEY_RE = re.compile(
    r"(?i)(?<![\w])(?:US\$|HK\$|[$€£¥]|USD|HKD|CNY|RMB)\s*-?\d[\d,]*(?:\.\d+)?(?:\s*[kmb])?"
    r"|\b-?\d[\d,]*(?:\.\d+)?\s*(?:USD|HKD|CNY|RMB)\b"
)
_PUBLIC_PERCENT_RE = re.compile(r"(?<![\w.+-])[-+]?\d{1,3}(?:\.\d+)?%(?![\w])")
_PUBLIC_CALENDAR_EVENT_RE = re.compile(
    r"(?i)(?:24 helpful pre-seed meeting [^.;\n]+|Cambly lesson with [A-Z][A-Za-z .-]+|招商信用卡最后还款日|credit card payment deadline|Apply For Ca ID)"
)
_PUBLIC_BROKERAGE_RE = re.compile(r"(?i)\b(?:Futu(?: margin(?: account)?)?|risk status: LEVEL\d+|LEVEL\d+)\b")
_PUBLIC_RECEIPT_RE = re.compile(r"(?i)\b(?:OpenRouter(?:, Inc)?(?: receipt)?|receipt \[#?[A-Za-z0-9-]+\])\b")


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
    normalized = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def _mirror_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    if src.exists():
        shutil.copytree(src, dst)


def _anchor(value: Any) -> str:
    text = str(value or "").lower()
    out = []
    for ch in text:
        out.append(ch if ch.isalnum() else "-")
    return "-".join(part for part in "".join(out).split("-") if part)


def _title_from_id(case_id: str) -> str:
    return str(case_id).replace("_", " ").replace("-", " ").title()


def _short_text(value: Any, limit: int = 220) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    text = _PUBLIC_EMAIL_RE.sub("<redacted:email>", text)
    text = _PUBLIC_PHONE_RE.sub("<redacted:phone>", text)
    text = _PUBLIC_TOKEN_RE.sub("<redacted:token>", text)
    text = _PUBLIC_LOCAL_PATH_RE.sub("<redacted:path>", text)
    text = _PUBLIC_ENV_FILE_RE.sub("<redacted:env-file>", text)
    text = _PUBLIC_SECRET_LABEL_RE.sub(lambda match: f"{match.group(1)}: <redacted>", text)
    text = _PUBLIC_SENSITIVE_URL_RE.sub(
        lambda match: "<redacted:url>"
        if "?" in match.group(0) or "zoom.us/" in match.group(0) or "calendar/event" in match.group(0)
        else match.group(0),
        text,
    )
    text = _PUBLIC_MONEY_RE.sub("<redacted:amount>", text)
    text = _PUBLIC_PERCENT_RE.sub("<redacted:percentage>", text)
    text = _PUBLIC_CALENDAR_EVENT_RE.sub("<redacted:calendar-event>", text)
    text = _PUBLIC_BROKERAGE_RE.sub("<redacted:brokerage-signal>", text)
    text = _PUBLIC_RECEIPT_RE.sub("<redacted:receipt>", text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _public_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _public_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_public_safe_value(item) for item in value]
    if isinstance(value, str):
        return _short_text(value, max(len(value), 220))
    return value


def _summarize_public_value(value: Any, *, empty: str, limit: int = 220) -> str:
    if value in (None, "", [], {}):
        return empty
    if isinstance(value, dict):
        parts = []
        for key, item in list(value.items())[:6]:
            if isinstance(item, (dict, list)):
                item_text = f"{type(item).__name__} with {len(item)} item" + ("" if len(item) == 1 else "s")
            else:
                item_text = str(item)
            parts.append(f"{key}: {item_text}")
        suffix = f"; +{len(value) - 6} more" if len(value) > 6 else ""
        return _short_text("; ".join(parts) + suffix, limit)
    if isinstance(value, list):
        parts = [str(item) for item in value[:6]]
        suffix = f"; +{len(value) - 6} more" if len(value) > 6 else ""
        return _short_text("; ".join(parts) + suffix, limit)
    return _short_text(value, limit)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _relative_time_label(ms: Any) -> str:
    value = _float_or_none(ms)
    if value is None:
        return "time not captured"
    if value == 0:
        return "T+0s"
    if value < 1000:
        return f"T+{value:.0f}ms"
    seconds = value / 1000.0
    if seconds < 60:
        return f"T+{seconds:.1f}s"
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"T+{minutes}m {remainder:.1f}s"


def _timing(offset_ms: Any = None, *, duration_ms: Any = None, source: str, confidence: str) -> dict:
    offset = _float_or_none(offset_ms)
    duration = _float_or_none(duration_ms)
    return {
        "offset_ms": offset,
        "duration_ms": duration,
        "label": _relative_time_label(offset),
        "source": source,
        "confidence": confidence,
    }


def _event_time_from_source(event: dict, *, fallback: dict | None = None) -> dict:
    if isinstance(event.get("time"), dict):
        time = dict(event["time"])
        offset = _float_or_none(time.get("offset_ms"))
        duration = _float_or_none(time.get("duration_ms"))
        time["offset_ms"] = offset
        time["duration_ms"] = duration
        time["label"] = _short_text(time.get("label") or _relative_time_label(offset), 80)
        if time.get("timestamp_utc"):
            time["timestamp_utc"] = _short_text(time.get("timestamp_utc"), 80)
        time["source"] = _short_text(time.get("source") or "provided_public_event", 80)
        time["confidence"] = _short_text(time.get("confidence") or "provided", 40)
        return time
    for key in ("offset_ms", "elapsed_ms", "timestamp_ms", "start_ms"):
        if event.get(key) is not None:
            return _timing(
                event.get(key),
                duration_ms=event.get("duration_ms"),
                source=f"public_event.{key}",
                confidence="recorded",
            )
    if fallback:
        return fallback
    return _timing(None, source="not_captured", confidence="unavailable")


def _event_sort_key(event: dict, original_index: int = 0) -> tuple[int, float, int]:
    time = event.get("time") if isinstance(event.get("time"), dict) else {}
    offset = _float_or_none(time.get("offset_ms"))
    if offset is not None:
        return (0, offset, original_index)
    timestamp = _short_text(time.get("timestamp_utc"), 80) if time.get("timestamp_utc") else ""
    if timestamp:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return (1, parsed.timestamp() * 1000.0, original_index)
        except ValueError:
            return (1, float(original_index), original_index)
    return (2, float("inf"), original_index)


def _merge_tool_events(events: list[dict]) -> list[dict]:
    merged: list[dict] = []
    pending_by_id: dict[str, int] = {}
    pending_by_name: dict[str, list[int]] = {}

    def pending_add(event: dict) -> None:
        idx = len(merged)
        merged.append(event)
        call_id = str(event.get("tool_call_id") or "")
        name = str(event.get("tool_name") or "")
        if call_id:
            pending_by_id[call_id] = idx
        elif name:
            pending_by_name.setdefault(name, []).append(idx)

    def pending_take(event: dict) -> int | None:
        call_id = str(event.get("tool_call_id") or "")
        name = str(event.get("tool_name") or "")
        if call_id and call_id in pending_by_id:
            return pending_by_id.pop(call_id)
        if name and pending_by_name.get(name):
            return pending_by_name[name].pop(0)
        return None

    def merge_into(call: dict, result: dict) -> dict:
        call_time = call.get("time") if isinstance(call.get("time"), dict) else {}
        result_time = result.get("time") if isinstance(result.get("time"), dict) else {}
        duration_ms = call.get("duration_ms")
        call_offset = _float_or_none(call_time.get("offset_ms"))
        result_offset = _float_or_none(result_time.get("offset_ms"))
        if duration_ms is None and call_offset is not None and result_offset is not None and result_offset >= call_offset:
            duration_ms = round(result_offset - call_offset, 3)
        return {
            **call,
            "type": "tool_step",
            "label": "Tool",
            "status": "observed_result" if result.get("status") else call.get("status"),
            "source": call.get("source") or result.get("source"),
            "result_source": result.get("source"),
            "duration_ms": duration_ms,
            "output_summary": result.get("output_summary") or call.get("output_summary"),
            "result_time": result_time,
            "retention": {
                "args": (call.get("retention") or {}).get("args", "-"),
                "result": (result.get("retention") or {}).get("result", "-"),
            },
        }

    for event in events:
        event_type = str(event.get("type") or "")
        if event_type == "tool_call" and event.get("status") != "observed_name_only":
            pending_add(event)
            continue
        if event_type == "tool_result":
            idx = pending_take(event)
            if idx is not None:
                merged[idx] = merge_into(merged[idx], event)
            else:
                merged.append({
                    **event,
                    "type": "tool_step",
                    "label": "Tool",
                })
            continue
        if event_type == "tool_call":
            merged.append({
                **event,
                "type": "tool_step",
                "label": "Tool observed",
            })
            continue
        merged.append(event)
    return merged


def _assistant_message_time_fallbacks(row: dict, public_transcript: list[dict]) -> list[dict]:
    assistant_turn_count = sum(
        1
        for turn in public_transcript
        if isinstance(turn, dict) and (turn.get("assistant") or turn.get("error"))
    )
    if assistant_turn_count <= 0:
        return []
    observability = row.get("observability") if isinstance(row.get("observability"), dict) else {}
    messages = observability.get("messages") if isinstance(observability.get("messages"), dict) else {}
    samples = [item for item in (messages.get("sample") or []) if isinstance(item, dict)]
    assistant_messages = [
        item for item in samples
        if item.get("role") == "assistant" and isinstance(item.get("time"), dict)
    ]
    final_messages = [
        item for item in assistant_messages
        if str(item.get("finish_reason") or "") not in {"", "tool_calls"}
    ]
    if len(final_messages) < assistant_turn_count:
        return []
    candidates = final_messages
    return [
        _event_time_from_source({"time": item["time"]})
        for item in candidates[-assistant_turn_count:]
    ]


def _normalize_public_events(row: dict, public_transcript: list[dict]) -> list[dict]:
    """Return public-safe trace events for website rendering.

    Existing runs may only have a redacted transcript plus name-only tool
    summaries. Newer runs can provide observability tools with redacted args and
    results. This function keeps the website schema stable across both.
    """
    mechanical = row.get("mechanical") if isinstance(row.get("mechanical"), dict) else {}
    case_wall_ms = mechanical.get("wall_ms")
    if isinstance(row.get("public_events"), list):
        events = row["public_events"]
    else:
        events = []
        assistant_time_fallbacks = _assistant_message_time_fallbacks(row, public_transcript)
        assistant_event_index = 0
        for turn in public_transcript:
            turn_id = turn.get("turn")
            turn_offset = _float_or_none(turn.get("offset_ms"))
            turn_wall = _float_or_none(turn.get("wall_ms"))
            user_offset = None
            if turn_offset is not None and turn_wall is not None:
                user_offset = max(0.0, turn_offset - turn_wall)
            elif len(public_transcript) == 1:
                user_offset = 0
            if turn.get("user"):
                events.append({
                    "type": "user_message",
                    "turn": turn_id,
                    "label": f"Turn {turn_id} user",
                    "text": turn.get("user"),
                    "time": _timing(
                        user_offset,
                        source="transcript.turn_start" if user_offset is not None and (turn_offset is not None or turn_wall is not None) else "turn_start" if user_offset == 0 else "not_captured",
                        confidence="recorded" if turn_offset is not None and turn_wall is not None else "coarse" if user_offset == 0 else "unavailable",
                    ),
                })
            if turn.get("assistant") or turn.get("error"):
                assistant_fallback_time = (
                    assistant_time_fallbacks[assistant_event_index]
                    if assistant_event_index < len(assistant_time_fallbacks)
                    else None
                )
                assistant_event_index += 1
                assistant_offset = turn.get("offset_ms") if turn.get("offset_ms") is not None else turn.get("wall_ms")
                assistant_wall = assistant_offset if assistant_offset is not None else (
                    case_wall_ms if len(public_transcript) == 1 else None
                )
                if turn.get("offset_ms") is not None:
                    source = "transcript.offset_ms"
                elif turn.get("wall_ms") is not None:
                    source = "transcript.wall_ms"
                else:
                    source = "case.wall_ms" if assistant_wall is not None else "not_captured"
                event_time = (
                    _timing(
                        assistant_wall,
                        duration_ms=turn.get("wall_ms"),
                        source=source,
                        confidence="coarse" if source == "case.wall_ms" else "recorded" if source.startswith("transcript.") else "unavailable",
                    )
                    if assistant_wall is not None or turn.get("wall_ms") is not None
                    else assistant_fallback_time or _timing(None, source="not_captured", confidence="unavailable")
                )
                events.append({
                    "type": "assistant_message",
                    "turn": turn_id,
                    "label": f"Turn {turn_id} assistant",
                    "text": turn.get("assistant"),
                    "error": turn.get("error"),
                    "timed_out": turn.get("timed_out"),
                    "duration_ms": turn.get("wall_ms"),
                    "time": event_time,
                })

        observability = row.get("observability") if isinstance(row.get("observability"), dict) else {}
        tool_rows = [
            item for item in (observability.get("tools") or [])
            if isinstance(item, dict) and item.get("name")
        ]
        name_only_tools = sorted({str(item) for item in (row.get("used_tools") or []) if item} - {
            str(item.get("name")) for item in tool_rows if item.get("name")
        })
        for item in tool_rows:
            status = str(item.get("status") or "observed")
            event_type = "tool_result" if status == "observed_result" else "tool_call"
            events.append({
                "type": event_type,
                "label": "Tool result" if event_type == "tool_result" else "Tool call",
                "tool_name": item.get("name"),
                "tool_call_id": item.get("tool_call_id"),
                "status": status,
                "source": item.get("source"),
                "input_summary": _summarize_public_value(
                    item.get("args"),
                    empty=str(item.get("args_retention") or "arguments omitted public-safe"),
                ),
                "output_summary": _summarize_public_value(
                    item.get("result"),
                    empty=str(item.get("result_retention") or "result omitted public-safe"),
                ),
                "retention": {
                    "args": item.get("args_retention") or "omitted_public_safe",
                    "result": item.get("result_retention") or "omitted_public_safe",
                },
                "time": _event_time_from_source(item),
            })

        for name in name_only_tools:
            events.append({
                "type": "tool_call",
                "label": "Tool observed",
                "tool_name": name,
                "status": "observed_name_only",
                "input_summary": "Tool usage was recorded by the benchmark summary; call arguments were not captured in the public artifact.",
                "output_summary": "Tool output was not captured in the public artifact.",
                "retention": {
                    "args": "omitted_public_safe",
                    "result": "omitted_public_safe",
                },
                "time": _timing(None, source="not_captured_in_past_run", confidence="unavailable"),
            })

        judge = row.get("judge") if isinstance(row.get("judge"), dict) else {}
        if judge.get("reason"):
            events.append({
                "type": "judge_result",
                "label": "Judge result",
                "status": "recorded",
                "text": _short_text(judge.get("reason"), 240),
                "time": _timing(case_wall_ms, source="case.wall_ms", confidence="coarse") if case_wall_ms is not None else _timing(None, source="not_captured", confidence="unavailable"),
            })

    normalized = []
    for original_index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "system_note")
        normalized.append({
            "index": original_index,
            "type": event_type,
            "turn": event.get("turn"),
            "label": _short_text(event.get("label") or event_type.replace("_", " ").title(), 80),
            "tool_name": _short_text(event.get("tool_name"), 80) if event.get("tool_name") else None,
            "tool_call_id": _short_text(event.get("tool_call_id"), 80) if event.get("tool_call_id") else None,
            "status": _short_text(event.get("status"), 80) if event.get("status") else None,
            "source": _short_text(event.get("source"), 120) if event.get("source") else None,
            "duration_ms": event.get("duration_ms"),
            "time": _event_time_from_source(event),
            "text": _short_text(event.get("text"), 800) if event.get("text") else None,
            "error": _short_text(event.get("error"), 260) if event.get("error") else None,
            "timed_out": event.get("timed_out"),
            "input_summary": _short_text(event.get("input_summary"), 360) if event.get("input_summary") else None,
            "output_summary": _short_text(event.get("output_summary"), 360) if event.get("output_summary") else None,
            "retention": event.get("retention") if isinstance(event.get("retention"), dict) else {},
        })
    sorted_events = sorted(normalized, key=lambda event: _event_sort_key(event, int(event.get("index") or 0)))
    merged_events = _merge_tool_events(sorted_events)
    for idx, event in enumerate(merged_events, start=1):
        event["index"] = idx
    return merged_events


def _list_field(case: dict, *names: str) -> list[str]:
    for name in names:
        value = case.get(name)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _authored_success_criteria(case: dict) -> list[str]:
    return _list_field(case, "success_criteria", "success")


def _authored_safety_criteria(case: dict) -> list[str]:
    return _list_field(case, "safety_criteria", "safety")


def build_task_catalog() -> dict:
    """Return bundled/local scenario metadata suitable for public browsing."""
    tasks: list[dict] = []
    for case in usecases.all_cases():
        category = case["category"]
        category_label = usecases.category_label(category)
        turns = usecases.case_turns(case)
        initial_prompt = str(case.get("initial_prompt") or turns[0]["prompt"])
        success_criteria = _authored_success_criteria(case)
        safety_criteria = _authored_safety_criteria(case)
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
            "effect_level": str(case.get("effect_level") or "read_only"),
            "side_effect_scope": str(case.get("side_effect_scope") or "benchmark_workdir"),
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
                "trace_url": f"{TRACE_PAGE}#trace-{_anchor(baseline_id)}-{_anchor(case_id)}",
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
    score = _read_json(baseline_dir / "score.json") if (baseline_dir / "score.json").exists() else {}
    rows = _read_jsonl(baseline_dir / "case-results.jsonl")
    cases: list[dict] = []
    for idx, row in enumerate(rows, start=1):
        task = tasks_by_id.get(str(row.get("case") or ""))
        public_transcript = _public_safe_value(row.get("public_transcript") or [])
        observability = _public_safe_value(row.get("observability")) if isinstance(row.get("observability"), dict) else {}
        observed_tool_names = sorted({
            str(item)
            for item in [
                *(row.get("used_tools") or []),
                *(tool.get("name") for tool in (observability.get("tools") or []) if isinstance(tool, dict)),
            ]
            if item
        })
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
            "public_transcript": public_transcript,
            "public_events": _normalize_public_events(row, public_transcript),
            "observed_tools": observed_tool_names,
            "used_skills": row.get("used_skills") or [],
            "observability": observability,
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
        "score_breakdown": score.get("score_breakdown") or {},
        "suite_scores": score.get("suite_scores") or {},
        "skipped_suites": manifest.get("skipped_suites") or score.get("skipped_suites") or [],
        "profile": score.get("profile") or {},
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


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item).strip()]


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _sha16(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _safe_skill_config(skills: dict) -> dict:
    return {
        "allowed": _string_list(skills.get("allowed")),
        "disabled": _string_list(skills.get("disabled")),
        "platform_allowed": {
            str(key): _string_list(value)
            for key, value in (skills.get("platform_allowed") or {}).items()
            if isinstance(value, list)
        },
        "platform_disabled": {
            str(key): _string_list(value)
            for key, value in (skills.get("platform_disabled") or {}).items()
            if isinstance(value, list)
        },
        "external_dirs_count": len(_string_list(skills.get("external_dirs"))),
    }


def _safe_mcp_servers(config: dict) -> list[dict]:
    rows = []
    for name, server in (config.get("mcp_servers") or {}).items():
        if not isinstance(server, dict):
            continue
        rows.append({
            "name": str(name),
            "enabled": bool(server.get("enabled")),
            "auth": server.get("auth"),
        })
    return sorted(rows, key=lambda row: row["name"])


def _safe_profile_snapshot(*, name: str, role: str, root: Path) -> dict | None:
    profile_dir = root if name == "default" else root / "profiles" / name
    config_path = profile_dir / "config.yaml"
    profile_path = profile_dir / "profile.yaml"
    soul_path = profile_dir / "SOUL.md"
    if not config_path.exists():
        return None
    config = _read_yaml(config_path)
    profile_meta = _read_yaml(profile_path)
    soul_title = ""
    if soul_path.exists():
        for line in soul_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#"):
                soul_title = line.strip("# ").strip()
                break
    model = config.get("model") or {}
    memory = config.get("memory") or {}
    plugins = config.get("plugins") or {}
    skills = config.get("skills") or {}
    platform_toolsets = config.get("platform_toolsets") or {}
    safe = {
        "schema_version": 1,
        "profile": name,
        "role": role,
        "publication_state": "published_redacted",
        "distribution_form": "redacted_distribution_style",
        "description": profile_meta.get("description"),
        "soul_title": soul_title,
        "distribution_files": ["SOUL.md", "config.yaml"],
        "model": {
            "provider": model.get("provider"),
            "default": model.get("default"),
        },
        "memory": {
            "enabled": memory.get("memory_enabled"),
            "provider": memory.get("provider"),
        },
        "toolsets": _string_list(config.get("toolsets")),
        "plugins": {
            "enabled": _string_list(plugins.get("enabled")),
            "disabled": _string_list(plugins.get("disabled")),
        },
        "skills": _safe_skill_config(skills),
        "platform_toolsets": {
            "cli": _string_list(platform_toolsets.get("cli")),
            "telegram": _string_list(platform_toolsets.get("telegram")),
        },
        "kanban": {
            key: value
            for key, value in (config.get("kanban") or {}).items()
            if key in {
                "dispatch_in_gateway",
                "dispatch_interval_seconds",
                "orchestrator_profile",
                "default_assignee",
                "auto_decompose",
                "auto_decompose_per_tick",
                "dispatch_stale_timeout_seconds",
                "max_spawn",
                "synthesis_timeout_seconds",
                "failure_limit",
            }
        },
        "mcp_servers": _safe_mcp_servers(config),
        "hashes": {},
        "redactions": [
            "auth files",
            ".env files",
            "memories",
            "sessions",
            "state databases",
            "logs",
            "local filesystem paths",
            "raw private SOUL sections",
            "MCP URLs and credentials",
        ],
    }
    safe["hashes"] = {
        "config_summary_hash": _sha16({
            "model": safe["model"],
            "memory": safe["memory"],
            "toolsets": safe["toolsets"],
            "plugins": safe["plugins"],
            "skills": safe["skills"],
            "platform_toolsets": safe["platform_toolsets"],
            "kanban": safe["kanban"],
        }),
    }
    return safe


def sync_local_kanban_profile_snapshots(profiles_root: Path) -> list[dict]:
    """Write public-safe local kanban profile snapshots when local Hermes profiles exist."""
    local_root = Path.home() / ".hermes"
    if not (local_root / "config.yaml").exists():
        return []
    specs = [
        ("default", "front_desk"),
        ("orchestrator", "orchestrator"),
        ("worker", "worker"),
        ("worker-code", "worker"),
        ("worker-fast", "worker"),
        ("worker-ops", "worker"),
        ("worker-report", "worker"),
        ("worker-research", "worker"),
    ]
    out_dir = profiles_root / "kanban"
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshots = []
    for name, role in specs:
        snapshot = _safe_profile_snapshot(name=name, role=role, root=local_root)
        if not snapshot:
            continue
        rel_path = out_dir / f"{name}.redacted.yaml"
        snapshot["source_file"] = f"data/profiles/kanban/{rel_path.name}"
        _write_text(rel_path, yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=True))
        snapshots.append(snapshot)
    _write_text(
        out_dir / "README.md",
        "# Kanban Profile Snapshots\n\n"
        "Public-safe redacted distribution-style snapshots for the local Hermes kanban profile collaboration design.\n"
        "These files intentionally omit credentials, memories, sessions, logs, local paths, state databases, and raw private SOUL content.\n",
    )
    return snapshots


def _published_profile_snapshots(profiles_root: Path) -> list[dict]:
    snapshots = []
    for path in sorted((profiles_root / "kanban").glob("*.redacted.yaml")):
        snapshot = _read_yaml(path)
        if not snapshot:
            continue
        snapshot.setdefault("source_file", f"data/profiles/kanban/{path.name}")
        snapshots.append(snapshot)
    return snapshots


def _distribution_metadata(baseline_dir: Path) -> dict:
    score = _read_json(baseline_dir / "score.json") if (baseline_dir / "score.json").exists() else {}
    profile = score.get("profile") or {}
    snapshot_path = baseline_dir / "profile-snapshot.redacted.yaml"
    distribution = profile.get("distribution") or profile.get("profile_distribution") or {}
    if distribution:
        return {
            "form": "installable_distribution",
            "repo_url": distribution.get("repo_url") or distribution.get("url"),
            "version": distribution.get("version"),
            "commit": distribution.get("commit") or distribution.get("sha"),
            "snapshot": snapshot_path.as_posix() if snapshot_path.exists() else None,
        }
    return {
        "form": "redacted_distribution_style" if snapshot_path.exists() else "profile_fingerprint_only",
        "repo_url": None,
        "version": None,
        "commit": None,
        "snapshot": f"data/baselines/{baseline_dir.name}/profile-snapshot.redacted.yaml" if snapshot_path.exists() else None,
    }


def _suite_score_rows(suite_scores: dict) -> list[dict]:
    rows = [
        {"suite_id": str(suite_id), "score": score}
        for suite_id, score in (suite_scores or {}).items()
        if score is not None
    ]
    return sorted(rows, key=lambda row: (float(row.get("score") or 0.0), row["suite_id"]), reverse=True)


def _scenario_score_rows(trace: dict, *, reverse: bool) -> list[dict]:
    rows = []
    for case in trace.get("cases") or []:
        if case.get("score") is None:
            continue
        case_id = str(case.get("case") or "")
        baseline_id = str(trace.get("baseline_id") or "")
        rows.append({
            "case": case_id,
            "suite_id": case.get("suite_id"),
            "title": ((case.get("task") or {}).get("title")) or case_id,
            "score": case.get("score"),
            "trace_url": f"{TRACE_PAGE}#trace-{_anchor(baseline_id)}-{_anchor(case_id)}",
        })
    return sorted(rows, key=lambda row: (float(row.get("score") or 0.0), row["case"]), reverse=reverse)


def _suite_was_exercised(trace: dict, suite_id: str) -> bool:
    return any(case.get("suite_id") == suite_id for case in trace.get("cases") or [])


def _suite_was_skipped(trace: dict, suite_id: str) -> bool:
    return any(item.get("suite_id") == suite_id for item in trace.get("skipped_suites") or [])


def _profile_roles(profile: dict, snapshot: dict, trace: dict) -> list[dict]:
    surface = profile.get("execution_surface") or snapshot.get("execution_surface") or {}
    capability = snapshot.get("capability_surface") or {}
    target = capability.get("target") or {}
    config = snapshot.get("config") or {}
    kanban = config.get("kanban") or {}
    plugins = _string_list(profile.get("plugins_enabled") or ((config.get("plugins") or {}).get("enabled")))
    target_profile = str(target.get("profile") or profile.get("target_profile") or "default")
    delegated_exercised = _suite_was_exercised(trace, "delegated_closure")
    delegated_skipped = _suite_was_skipped(trace, "delegated_closure")

    roles = [{
        "role": "front_desk",
        "profile": target_profile,
        "status": "exercised" if trace.get("case_count") else "present_not_exercised",
        "evidence": "prompt benchmark cases route through this target profile",
    }]

    kanban_enabled = bool(surface.get("kanban_enabled")) or "kanban" in _string_list(profile.get("toolsets")) or "kanban-orchestrator-routing" in plugins
    if kanban_enabled:
        orchestrator = str(kanban.get("orchestrator_profile") or kanban.get("default_assignee") or "orchestrator")
        status = "exercised" if delegated_exercised else "present_not_exercised"
        roles.append({
            "role": "orchestrator",
            "profile": orchestrator,
            "status": status,
            "evidence": "delegated_closure suite exercised" if delegated_exercised else "kanban configured; delegated_closure not exercised",
        })
        roles.append({
            "role": "routing_delegation",
            "profile": "kanban-orchestrator-routing" if "kanban-orchestrator-routing" in plugins else orchestrator,
            "status": status,
            "evidence": "routing plugin/toolset present" + (" and exercised" if delegated_exercised else " but multi-profile suite skipped"),
        })

    requested_workers = _string_list(
        ((trace.get("score_breakdown") or {}).get("profile_coverage") or {}).get("requested")
    )
    worker_status = "exercised" if delegated_exercised else "present_not_exercised"
    for worker in requested_workers:
        roles.append({
            "role": "worker",
            "profile": worker,
            "status": worker_status,
            "evidence": "requested worker profile in delegated closure coverage",
        })

    if kanban_enabled and delegated_skipped and not requested_workers:
        roles.append({
            "role": "worker",
            "profile": "not_published",
            "status": "present_not_exercised",
            "evidence": "kanban enabled, but no worker profile list was published for this run",
        })

    return roles


def _snapshot_summary(snapshot: dict, profile: dict) -> dict:
    config = snapshot.get("config") or {}
    kanban = config.get("kanban") or {}
    capability = snapshot.get("capability_surface") or {}
    target = capability.get("target") or {}
    tools = capability.get("tools") or {}
    skills = capability.get("agent_skills") or {}
    inventory = skills.get("inventory") or profile.get("agent_skills") or {}
    return {
        "target": {
            "ui": target.get("ui"),
            "profile": target.get("profile"),
            "platform": target.get("platform"),
        },
        "model": (config.get("model") or {}).get("default") or profile.get("model"),
        "model_provider": (config.get("model") or {}).get("provider") or profile.get("model_provider"),
        "memory": {
            "provider": (config.get("memory") or {}).get("provider") or profile.get("memory_provider"),
            "enabled": (config.get("memory") or {}).get("memory_enabled") if config.get("memory") else profile.get("memory_enabled"),
        },
        "kanban": {
            "orchestrator_profile": kanban.get("orchestrator_profile"),
            "default_assignee": kanban.get("default_assignee"),
            "auto_decompose": kanban.get("auto_decompose"),
            "max_spawn": kanban.get("max_spawn"),
        },
        "tools": {
            "root_toolsets": _string_list(tools.get("root_toolsets") or profile.get("toolsets")),
            "platform_toolsets": _string_list(tools.get("platform_toolsets")),
            "platform_toolset_hash": tools.get("platform_toolset_hash"),
        },
        "agent_skills": {
            "count": inventory.get("count"),
            "hash": inventory.get("hash"),
            "sample": _string_list(inventory.get("sample"))[:12],
            "disabled": _string_list(skills.get("globally_disabled"))[:12],
            "platform_disabled": _string_list(skills.get("platform_disabled"))[:12],
            "platform_allowed": _string_list(skills.get("platform_allowed"))[:12],
        },
        "bench_env": {
            key: value
            for key, value in (snapshot.get("bench_env") or {}).items()
            if str(key).startswith("HERMES_BENCH") or str(key) == "HERMES_RUN_LLM_EVALS"
        },
    }


def _observed_usage(trace: dict) -> dict:
    tools: set[str] = set()
    skills: set[str] = set()
    cases: dict[str, dict[str, set[str]]] = {}
    for case in trace.get("cases") or []:
        case_id = str(case.get("case") or "")
        case_tools: set[str] = set()
        case_skills: set[str] = set()
        for name in _string_list(case.get("observed_tools")):
            tools.add(name)
            case_tools.add(name)
        for name in _string_list(case.get("used_skills")):
            skills.add(name)
            case_skills.add(name)
        observability = case.get("observability") if isinstance(case.get("observability"), dict) else {}
        for item in observability.get("tools") or []:
            if isinstance(item, dict) and item.get("name"):
                name = str(item["name"])
                tools.add(name)
                case_tools.add(name)
        for name in _string_list(observability.get("skills")):
            skills.add(name)
            case_skills.add(name)
        for event in case.get("public_events") or []:
            if isinstance(event, dict) and event.get("tool_name"):
                name = str(event["tool_name"])
                tools.add(name)
                case_tools.add(name)
        if case_id and (case_tools or case_skills):
            cases[case_id] = {"tools": case_tools, "skills": case_skills}
    return {
        "recorded": bool(tools or skills),
        "tools": sorted(tools),
        "skills": sorted(skills),
        "cases": [
            {"case": case_id, "tools": sorted(value["tools"]), "skills": sorted(value["skills"])}
            for case_id, value in sorted(cases.items())
        ],
        "default_display": "observed_only",
        "empty_note": "No public used-tool or used-skill telemetry was recorded for this baseline.",
    }


def _profile_units(roles: list[dict], distribution: dict, baseline_id: str, related: dict, snapshots: list[dict]) -> list[dict]:
    units: list[dict] = []
    seen: set[tuple[str, str]] = set()
    role_status: dict[tuple[str, str], dict] = {}
    for role in roles:
        role_name = str(role.get("role") or "")
        profile_name = str(role.get("profile") or "")
        if role_name and profile_name:
            role_status[(role_name, profile_name)] = role
    for snapshot in snapshots:
        role_name = str(snapshot.get("role") or "worker")
        profile_name = str(snapshot.get("profile") or "")
        key = (role_name, profile_name)
        if key in seen:
            continue
        seen.add(key)
        matched_role = role_status.get(key)
        if not matched_role and role_name == "worker":
            matched_role = role_status.get(("worker", "not_published"))
        status = (matched_role or {}).get("status") or ("exercised" if role_name == "front_desk" else "present_not_exercised")
        evidence = (matched_role or {}).get("evidence") or "uploaded local redacted kanban profile snapshot"
        installable = bool(distribution.get("repo_url"))
        install_command = (
            f"hermes profile install {distribution.get('repo_url')} --alias {profile_name}"
            if installable else None
        )
        implementation_prompt = f"""Use this public HermesBench profile evidence to recreate a local Hermes profile distribution.

Baseline: {baseline_id}
Profile role: {role_name}
Profile name: {profile_name}
Distribution form: {distribution.get('form') or 'unknown'}
Trace evidence: {related.get('trace_url') or related.get('leaderboard_url')}
Trace JSON: {related.get('trace_json')}

Goal:
Create or update a local Hermes profile distribution for this single profile. Preserve the profile-distribution model: distribution.yaml, SOUL.md, config.yaml, bundled skills, cron jobs, and MCP/tool connections as appropriate.

Use only public-safe evidence from data/profiles/index.json, the linked trace, and the redacted snapshot summary. Do not copy credentials, .env files, memories, sessions, local paths, logs, state databases, raw private chats, or unredacted config.

After this single profile is implemented, link it into the same configuration bundle role if needed rather than creating a separate benchmark pathway."""
        units.append({
            "role": role_name,
            "profile": profile_name,
            "status": status,
            "evidence": evidence,
            "description": snapshot.get("description"),
            "soul_title": snapshot.get("soul_title"),
            "source_file": snapshot.get("source_file"),
            "toolsets": _string_list(snapshot.get("toolsets")),
            "plugins_enabled": _string_list((snapshot.get("plugins") or {}).get("enabled")),
            "skills_allowed": _string_list((snapshot.get("skills") or {}).get("allowed")),
            "platform_toolsets_cli": _string_list((snapshot.get("platform_toolsets") or {}).get("cli")),
            "model": snapshot.get("model") or {},
            "memory": snapshot.get("memory") or {},
            "hashes": snapshot.get("hashes") or {},
            "distribution_form": snapshot.get("distribution_form") or distribution.get("form"),
            "publication_state": "installable_distribution" if installable else "published_redacted",
            "required_for_bundle": bool(role_name in {"front_desk", "orchestrator", "worker"}),
            "installable": installable,
            "install_command": install_command,
            "implementation_prompt": implementation_prompt,
            "cta_label": "Copy install command" if installable else "Copy local implementation prompt",
            "note": (
                "Install this profile distribution locally, then link it into the configuration bundle."
                if installable
                else "This profile is published as redacted evidence, so recreate it locally from the public shape."
            ),
        })
    for role in roles:
        role_name = str(role.get("role") or "")
        profile_name = str(role.get("profile") or "")
        if role_name == "routing_delegation" or (role_name, profile_name) in seen or profile_name in {"", "not_published"}:
            continue
        installable = bool(distribution.get("repo_url"))
        install_command = (
            f"hermes profile install {distribution.get('repo_url')} --alias {profile_name}"
            if installable else None
        )
        implementation_prompt = f"""Use this public HermesBench profile evidence to recreate a local Hermes profile distribution.

Baseline: {baseline_id}
Profile role: {role_name}
Profile name: {profile_name}
Distribution form: {distribution.get('form') or 'unknown'}
Trace evidence: {related.get('trace_url') or related.get('leaderboard_url')}
Trace JSON: {related.get('trace_json')}

Goal:
Create or update a local Hermes profile distribution for this single profile. Preserve the profile-distribution model: distribution.yaml, SOUL.md, config.yaml, bundled skills, cron jobs, and MCP/tool connections as appropriate.

Use only public-safe evidence from data/profiles/index.json, the linked trace, and the redacted snapshot summary. Do not copy credentials, .env files, memories, sessions, local paths, logs, state databases, raw private chats, or unredacted config.

After this single profile is implemented, link it into the same configuration bundle role if needed rather than creating a separate benchmark pathway."""
        units.append({
            "role": role_name,
            "profile": profile_name,
            "status": role.get("status"),
            "evidence": role.get("evidence"),
            "distribution_form": distribution.get("form"),
            "publication_state": "installable_distribution" if installable else "published_redacted",
            "required_for_bundle": True,
            "installable": installable,
            "install_command": install_command,
            "implementation_prompt": implementation_prompt,
            "cta_label": "Copy install command" if installable else "Copy local implementation prompt",
            "note": "Install this profile distribution locally, then link it into the configuration bundle." if installable else "This profile is published as redacted evidence, so recreate it locally from the public shape.",
        })
        seen.add((role_name, profile_name))
    for role in roles:
        role_name = str(role.get("role") or "")
        profile_name = str(role.get("profile") or "")
        if role_name == "routing_delegation" or (role_name, profile_name) in seen or profile_name not in {"", "not_published"}:
            continue
        if role_name == "worker" and any(unit.get("role") == "worker" for unit in units):
            continue
        publication_prompt = f"""Publish the missing HermesBench profile evidence for this kanban-related profile slot.

Baseline: {baseline_id}
Profile role: {role_name}
Current published profile name: {profile_name or 'not_published'}
Trace evidence: {related.get('trace_url') or related.get('leaderboard_url')}
Trace JSON: {related.get('trace_json')}

Required action:
Add an installable Hermes profile distribution link or a redacted distribution-style snapshot for this single profile. Keep it tied to the same configuration bundle role.

Do not publish credentials, .env files, memories, sessions, local paths, logs, state databases, raw private chats, or unredacted config."""
        units.append({
            "role": role_name,
            "profile": profile_name,
            "status": role.get("status"),
            "evidence": role.get("evidence"),
            "distribution_form": distribution.get("form"),
            "publication_state": "missing_required_profile",
            "required_for_bundle": True,
            "installable": False,
            "install_command": None,
            "implementation_prompt": publication_prompt,
            "cta_label": "Copy publication checklist",
            "note": "This kanban-related profile slot is required for a complete public baseline and still needs profile evidence uploaded.",
        })
    return units


def build_profile_architecture_index(baselines_root: Path, traces: list[dict], profiles_root: Path | None = None) -> dict:
    """Return public profile/distribution architecture metadata linked to scores."""
    trace_by_baseline = {trace.get("baseline_id"): trace for trace in traces}
    architectures: list[dict] = []
    published_snapshots = _published_profile_snapshots(profiles_root) if profiles_root else []
    for baseline_dir in baseline_dirs(baselines_root):
        trace = trace_by_baseline.get(baseline_dir.name)
        if not trace:
            continue
        manifest = _read_json(baseline_dir / "run-manifest.json")
        score = _read_json(baseline_dir / "score.json") if (baseline_dir / "score.json").exists() else {}
        profile = score.get("profile") or trace.get("profile") or {}
        snapshot = _read_yaml(baseline_dir / "profile-snapshot.redacted.yaml")
        surface = profile.get("execution_surface") or snapshot.get("execution_surface") or {}
        skills = profile.get("agent_skills") or (((snapshot.get("capability_surface") or {}).get("agent_skills") or {}).get("inventory")) or {}
        suite_scores = _suite_score_rows(score.get("suite_scores") or trace.get("suite_scores") or {})
        high = _scenario_score_rows(trace, reverse=True)[:5]
        low = _scenario_score_rows(trace, reverse=False)[:5]
        roles = _profile_roles(profile, snapshot, trace)
        distribution = _distribution_metadata(baseline_dir)
        related_scores = {
            "overall": manifest.get("overall_score") or trace.get("overall_score"),
            "score_breakdown": score.get("score_breakdown") or trace.get("score_breakdown") or {},
            "suite_scores": suite_scores,
            "top_suites": suite_scores[:5],
            "improvement_suites": sorted(suite_scores, key=lambda row: (float(row.get("score") or 0.0), row["suite_id"]))[:5],
            "top_scenarios": high,
            "improvement_scenarios": low,
            "leaderboard_url": f"{TRACE_PAGE}#trace-{_anchor(baseline_dir.name)}",
            "trace_url": f"{TRACE_PAGE}#trace-{_anchor(baseline_dir.name)}",
            "trace_json": f"data/traces/{baseline_dir.name}/trace.json",
        }
        architectures.append({
            "baseline_id": baseline_dir.name,
            "run_id": manifest.get("run_id") or trace.get("run_id"),
            "timestamp_utc": manifest.get("timestamp_utc") or trace.get("timestamp_utc"),
            "overall_score": manifest.get("overall_score") or trace.get("overall_score"),
            "execution_surface": {
                "id": surface.get("id") or "direct",
                "label": surface.get("label") or _label_text(surface.get("id") or "direct"),
                "kanban_enabled": bool(surface.get("kanban_enabled")),
                "prompt_case_contract": surface.get("prompt_case_contract") or "framework_agnostic",
            },
            "distribution": distribution,
            "profile_fingerprint": manifest.get("profile_fingerprint") or trace.get("profile_fingerprint") or {},
            "profile_hash": profile.get("profile_hash") or (manifest.get("profile_fingerprint") or {}).get("profile_hash"),
            "model_provider": profile.get("model_provider"),
            "model": profile.get("model"),
            "memory": {
                "provider": profile.get("memory_provider"),
                "enabled": profile.get("memory_enabled"),
            },
            "toolsets": _string_list(profile.get("toolsets")),
            "plugins_enabled": _string_list(profile.get("plugins_enabled")),
            "agent_skills": {
                "count": skills.get("count"),
                "hash": skills.get("hash"),
                "sample": _string_list(skills.get("sample"))[:12],
                "truncated": bool(skills.get("truncated")),
            },
            "roles": roles,
            "profile_units": _profile_units(roles, distribution, baseline_dir.name, related_scores, published_snapshots),
            "snapshot_summary": _snapshot_summary(snapshot, profile),
            "observed_usage": _observed_usage(trace),
            "related_scores": related_scores,
            "implementation_loop": {
                "learn": "Inspect the strong suites/scenarios to see where this profile shape worked.",
                "install_or_copy": "Install an installable profile distribution, or recreate a local profile from the redacted public shape.",
                "bundle": "Link single profiles into a shared configuration bundle through roles such as front desk, orchestrator, and worker.",
                "verify": "After local implementation, run HermesBench to verify behavior without changing the publication pathway.",
            },
            "source_files": {
                "baseline": f"data/baselines/{baseline_dir.name}",
                "trace_json": f"data/traces/{baseline_dir.name}/trace.json",
                "score_json": f"data/baselines/{baseline_dir.name}/score.json",
            },
        })

    architectures = sorted(
        architectures,
        key=lambda item: (float(item.get("overall_score") or 0.0), str(item.get("baseline_id") or "")),
        reverse=True,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "profile_count": len(architectures),
        "profile_unit_count": sum(len(item.get("profile_units") or []) for item in architectures),
        "source": "public HermesBench baselines plus profile distribution snapshots",
        "distribution_contract": "docs/profile-distribution-baselines.md",
        "profiles": architectures,
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
                f"- Best trace-backed result: {best['score']} by `{best['baseline_id']}`" if best else "- Best trace-backed result: no matching public result yet",
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
                lines.extend(["", "Scenario evidence:", "", "| Rank | Baseline | Score | Evidence |", "| ---: | --- | ---: | --- |"])
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


def _label_text(value: Any) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:] if text else "-"


def _fmt_bool(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "-"


def _render_metric_cards(items: list[tuple[str, Any, str | None]]) -> str:
    cards = []
    for label, value, note in items:
        cards.append(f"""
          <div>
            <span class="metric">{escape(_score(value))}</span>
            <span class="label">{escape(label)}</span>
            {f'<span class="metric-note">{escape(note)}</span>' if note else ''}
          </div>
        """)
    return "".join(cards)


def _render_score_breakdown(trace: dict) -> str:
    breakdown = trace.get("score_breakdown") or {}
    top_axes = breakdown.get("top_axes") or {}
    axes = breakdown.get("axes") or {}
    coverage = breakdown.get("coverage") or {}
    rows = []
    for label, value in [
        ("Capability / truthfulness", top_axes.get("capability_truthfulness")),
        ("Reliability / safety", top_axes.get("reliability_safety")),
        ("Efficiency / UX", top_axes.get("efficiency_ux")),
        ("Task fulfillment", axes.get("task_fulfillment")),
        ("Evidence / truthfulness", axes.get("evidence_truthfulness")),
        ("Outcome reached", axes.get("outcome_reached")),
        ("Runtime / scope safety", axes.get("runtime_scope_safety")),
        ("Responsiveness", axes.get("responsiveness")),
        ("Communication quality", axes.get("communication_quality")),
    ]:
        if value is not None:
            rows.append(f"<tr><th>{escape(label)}</th><td>{escape(_score(value))}</td></tr>")
    if coverage:
        rows.append(
            "<tr><th>Coverage</th><td>"
            + escape(str(coverage.get("label") or "-"))
            + (f", {escape(str(coverage.get('prompt_cases')))} cases" if coverage.get("prompt_cases") else "")
            + "</td></tr>"
        )
    return f"""
      <div class="score-summary">
        <div class="table-wrap mini">
          <table><tbody>{''.join(rows)}</tbody></table>
        </div>
      </div>
    """ if rows else ""


def _render_skipped_suites(trace: dict) -> str:
    skipped = trace.get("skipped_suites") or []
    if not skipped:
        return ""
    items = "".join(
        f"<li><code>{escape(str(item.get('suite_id')))}</code>: {escape(str(item.get('skip_reason') or 'skipped'))}</li>"
        for item in skipped
    )
    return f"""
      <div class="notice">
        <strong>Skipped runtime suites</strong>
        <ul>{items}</ul>
      </div>
    """


def _render_case_score_tiles(case: dict) -> str:
    top = case.get("top_axes") or {}
    axes = case.get("axes") or {}
    items = [
        ("Score", case.get("score")),
        ("Capability", top.get("capability_truthfulness")),
        ("Reliability", top.get("reliability_safety")),
        ("UX", top.get("efficiency_ux")),
        ("Outcome", axes.get("outcome_reached")),
        ("Response", axes.get("responsiveness")),
    ]
    return "".join(
        f"""
          <div>
            <dt>{escape(label)}</dt>
            <dd>{escape(_score(value))}</dd>
          </div>
        """
        for label, value in items
        if value is not None
    )


def _render_text_block(text: Any) -> str:
    return f'<div class="text-block">{escape(str(text or ""))}</div>'


def _render_inline_markdown(text: str) -> str:
    html = escape(text)
    html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
    html = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", html)
    return html


def _render_markdown_block(text: Any) -> str:
    source = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not source.strip():
        return '<div class="markdown-block"></div>'
    parts = re.split(r"(^```[^\n]*\n.*?^```[ \t]*$)", source, flags=re.MULTILINE | re.DOTALL)
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("```"):
            lines = part.split("\n")
            language = lines[0].strip().strip("`").strip()
            code = "\n".join(lines[1:-1])
            lang_class = f' class="language-{escape(_anchor(language))}"' if language else ""
            rendered.append(f"<pre><code{lang_class}>{escape(code)}</code></pre>")
            continue
        blocks: list[str] = []
        paragraph: list[str] = []
        list_items: list[str] = []
        list_type: str | None = None

        def flush_paragraph() -> None:
            nonlocal paragraph
            if paragraph:
                blocks.append(f"<p>{_render_inline_markdown(' '.join(item.strip() for item in paragraph))}</p>")
                paragraph = []

        def flush_list() -> None:
            nonlocal list_items, list_type
            if list_items and list_type:
                blocks.append(f"<{list_type}>{''.join(list_items)}</{list_type}>")
                list_items = []
                list_type = None

        for raw_line in part.split("\n"):
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                flush_paragraph()
                flush_list()
                continue
            heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
            unordered = re.match(r"^[-*]\s+(.+)$", stripped)
            ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
            quote = re.match(r"^>\s?(.+)$", stripped)
            if heading:
                flush_paragraph()
                flush_list()
                level = min(len(heading.group(1)) + 2, 6)
                blocks.append(f"<h{level}>{_render_inline_markdown(heading.group(2))}</h{level}>")
            elif unordered or ordered:
                flush_paragraph()
                next_type = "ul" if unordered else "ol"
                if list_type and list_type != next_type:
                    flush_list()
                list_type = next_type
                item = (unordered or ordered).group(1)
                list_items.append(f"<li>{_render_inline_markdown(item)}</li>")
            elif quote:
                flush_paragraph()
                flush_list()
                blocks.append(f"<blockquote>{_render_inline_markdown(quote.group(1))}</blockquote>")
            else:
                flush_list()
                paragraph.append(line)
        flush_paragraph()
        flush_list()
        rendered.extend(blocks)
    return f'<div class="markdown-block">{"".join(rendered)}</div>'


def _event_label(event_type: str) -> str:
    return {
        "user_message": "User",
        "assistant_message": "Assistant",
        "tool_call": "Tool call",
        "tool_result": "Tool result",
        "tool_step": "Tool",
        "judge_result": "Judge",
        "error": "Error",
        "timeout": "Timeout",
        "system_note": "Note",
    }.get(event_type, _label_text(event_type))


def _render_public_event(event: dict) -> str:
    event_type = str(event.get("type") or "system_note")
    event_class = _anchor(event_type)
    timing = event.get("time") if isinstance(event.get("time"), dict) else {}
    time_html = f'<time class="event-time">{escape(str(timing.get("label") or "time not captured"))}</time>'
    tool_name = event.get("tool_name")
    is_tool_event = event_type in {"tool_call", "tool_result", "tool_step"}
    title = str(event.get("label") or tool_name or _event_label(event_type))
    input_html = (
        f'<div class="event-summary"><span>Input</span>{_render_text_block(event.get("input_summary"))}</div>'
        if event.get("input_summary") else ""
    )
    output_html = (
        f'<div class="event-summary"><span>Output</span>{_render_text_block(event.get("output_summary"))}</div>'
        if event.get("output_summary") else ""
    )
    if event.get("text"):
        text_html = _render_markdown_block(event.get("text")) if event_type == "assistant_message" else _render_text_block(event.get("text"))
    else:
        text_html = ""
    error_html = f'<div class="message-error">Error: {escape(str(event.get("error")))}</div>' if event.get("error") else ""
    timeout_html = '<div class="message-error">Timed out</div>' if event.get("timed_out") else ""
    if is_tool_event:
        return f"""
          <details class="event-card event-tool-collapsed event-{escape(event_class)}">
            <summary>
              <span class="event-index">{escape(str(event.get('index') or ''))}</span>
              <span class="event-line">
                {time_html}
                <span class="event-type">Tool</span>
                <strong>{escape(str(tool_name or title))}</strong>
              </span>
            </summary>
            <div class="event-body">
              {input_html}
              {output_html}
              {error_html}
              {timeout_html}
            </div>
          </details>
        """
    return f"""
      <article class="event-card event-{escape(event_class)}">
        <div class="event-index">{escape(str(event.get('index') or ''))}</div>
        <div class="event-body">
          <header>
            {time_html}
            <span class="event-type">{escape(_event_label(event_type))}</span>
            <strong>{escape(title)}</strong>
          </header>
          {text_html}
          {input_html}
          {output_html}
          {error_html}
          {timeout_html}
        </div>
      </article>
    """


def _render_trace_timeline(case: dict) -> str:
    events = case.get("public_events") or []
    if not events:
        return f"""
          <div class="transcript-empty">
            No public trace events are available for this case.
          </div>
        """
    return f"""
      <div class="event-timeline">{''.join(_render_public_event(event) for event in events)}</div>
    """


def _render_transcript(case: dict) -> str:
    transcript = case.get("public_transcript") or []
    if not transcript:
        return f"""
          <div class="transcript-empty">
            No public transcript is available for this case.
          </div>
        """
    turns = []
    for idx, turn in enumerate(transcript, start=1):
        user = turn.get("user")
        assistant = turn.get("assistant")
        error = turn.get("error")
        turns.append(f"""
          <article class="conversation-turn">
            <div class="turn-label">Turn {idx}</div>
            <div class="message user-message">
              <div class="message-role">User</div>
              {_render_text_block(user)}
            </div>
            <div class="message assistant-message">
              <div class="message-role">Assistant</div>
              {_render_markdown_block(assistant)}
              {f'<div class="message-error">Error: {escape(str(error))}</div>' if error else ''}
            </div>
          </article>
        """)
    return f"""
      <div class="conversation">{''.join(turns)}</div>
    """


def _render_axis_table(case: dict) -> str:
    top = case.get("top_axes") or {}
    axes = case.get("axes") or {}
    rows = []
    for label, value in [
        ("Capability / truthfulness", top.get("capability_truthfulness")),
        ("Reliability / safety", top.get("reliability_safety")),
        ("Efficiency / UX", top.get("efficiency_ux")),
        ("Task fulfillment", axes.get("task_fulfillment")),
        ("Evidence / truthfulness", axes.get("evidence_truthfulness")),
        ("Runtime / scope safety", axes.get("runtime_scope_safety")),
        ("Communication quality", axes.get("communication_quality")),
    ]:
        if value is not None:
            rows.append(f"<tr><th>{escape(label)}</th><td>{escape(_score(value))}</td></tr>")
    return f'<div class="table-wrap mini"><table><tbody>{"".join(rows)}</tbody></table></div>' if rows else "<p>No axis scores recorded.</p>"


def _render_checks_and_effects(case: dict) -> str:
    checks = case.get("checks") or {}
    effects = case.get("side_effects") or {}
    failed = checks.get("failed") or []
    files = effects.get("files") or []
    failed_html = "".join(f"<li>{escape(str(item))}</li>" for item in failed) or "<li>None</li>"
    files_html = "".join(
        f"<li>{escape(str(item.get('path') or item))}</li>" if isinstance(item, dict) else f"<li>{escape(str(item))}</li>"
        for item in files
    ) or "<li>None</li>"
    return f"""
      <div class="evidence-grid">
        <div>
          <h4>Checks</h4>
          <dl class="mini-defs">
            <div><dt>Explicit checks</dt><dd>{escape(str(checks.get('explicit_count', 0)))}</dd></div>
            <div><dt>Scope OK</dt><dd>{escape(_fmt_bool(checks.get('scope_ok')))}</dd></div>
            <div><dt>Check score</dt><dd>{escape(_score(checks.get('score')))}</dd></div>
          </dl>
          <p class="mini-heading">Failed checks</p>
          <ul>{failed_html}</ul>
        </div>
        <div>
          <h4>Side Effects</h4>
          <dl class="mini-defs">
            <div><dt>Scope</dt><dd>{escape(str(effects.get('scope') or '-'))}</dd></div>
            <div><dt>Files</dt><dd>{escape(str(effects.get('total_files', 0)))}</dd></div>
            <div><dt>Bytes</dt><dd>{escape(str(effects.get('total_bytes', 0)))}</dd></div>
          </dl>
          <p class="mini-heading">Touched files</p>
          <ul>{files_html}</ul>
        </div>
      </div>
    """


def render_trace_markdown(trace: dict) -> str:
    lines = [
        f"# Trace Evidence: {trace['baseline_id']}",
        "",
        "This is the public-safe trace evidence: scenario identity, expected outcome, scoring evidence,",
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
            lines.extend(["Public transcript:", ""])
            for idx, turn in enumerate(case["public_transcript"], start=1):
                lines.extend([
                    f"- Turn {idx} user: {_md_cell(turn.get('user'))}",
                    f"- Turn {idx} assistant: {_md_cell(turn.get('assistant'))}",
                ])
                if turn.get("error"):
                    lines.append(f"- Turn {idx} error: {_md_cell(turn.get('error'))}")
            lines.append("")
        if case.get("public_events"):
            lines.extend(["Public trace events:", ""])
            for event in case["public_events"]:
                event_bits = [
                    f"{event.get('index')}. {_event_label(str(event.get('type') or 'system_note'))}",
                    str(event.get("tool_name") or event.get("label") or ""),
                ]
                if event.get("status"):
                    event_bits.append(f"status {event.get('status')}")
                if event.get("input_summary"):
                    event_bits.append(f"input {event.get('input_summary')}")
                if event.get("output_summary"):
                    event_bits.append(f"output {event.get('output_summary')}")
                lines.append("- " + _md_cell(" — ".join(bit for bit in event_bits if bit)))
            lines.append("")
        lines.extend([
            f"Driver: {driver.get('reason') or driver}",
            "",
            f"Judge: {judge.get('reason') or judge}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


SITE_URL = "https://verkyyi.github.io/hermesbench/"
SITE_DESCRIPTION = (
    "HermesBench benchmarks full Hermes personal-agent configurations with "
    "public recipes, redacted trace evidence, and reproducibility metadata."
)


def _head_meta(title: str, *, path: str = "", description: str = SITE_DESCRIPTION) -> str:
    page_title = "HermesBench" if title == "HermesBench" else f"{title} - HermesBench"
    canonical = SITE_URL + path
    image = SITE_URL + "assets/social-card.svg"
    return f"""    <title>{escape(page_title)}</title>
    <meta name="description" content="{escape(description)}" />
    <link rel="canonical" href="{escape(canonical)}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="HermesBench" />
    <meta property="og:title" content="{escape(page_title)}" />
    <meta property="og:description" content="{escape(description)}" />
    <meta property="og:url" content="{escape(canonical)}" />
    <meta property="og:image" content="{escape(image)}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{escape(page_title)}" />
    <meta name="twitter:description" content="{escape(description)}" />
    <meta name="twitter:image" content="{escape(image)}" />"""


def _page_shell(title: str, body: str) -> str:
    path = "" if title == "HermesBench" else f"{_anchor(title)}.html"
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
{_head_meta(title, path=path)}
    <link rel="stylesheet" href="assets/styles.css" />
  </head>
  <body>
    <header class="topbar">
      <a class="brand" href="index.html">HermesBench</a>
      <nav>
        <a href="index.html#quickstart">Quick start</a>
        <a href="recipes.html">Recipes</a>
        <a href="profiles.html">Profiles</a>
        <a href="traces.html">Traces</a>
        <a href="index.html#feedback">Feedback</a>
        <a href="index.html#contribute">Contribute</a>
        <a href="https://github.com/verkyyi/hermesbench">GitHub</a>
      </nav>
    </header>
    <main>{body}</main>
    <footer>
      <span>HermesBench</span>
      <a href="recipes.html">Recipes</a>
      <a href="profiles.html">Profiles</a>
      <a href="traces.html">Traces</a>
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
{_head_meta(title, path=target)}
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
        criteria_sections = []
        if success_items:
            criteria_sections.append(f"""              <section>
                <h3>Success Criteria</h3>
                <ul>{success_items}</ul>
              </section>""")
        if safety_items:
            criteria_sections.append(f"""              <section>
                <h3>Safety Criteria</h3>
                <ul>{safety_items}</ul>
              </section>""")
        criteria_html = "\n".join(criteria_sections)
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

Follow the skill's "Run Current Hermes Configuration" workflow using run_scenario_baseline("{task['id']}", trials=1, run_llm_evals=True, persist=True). Do not run the full bundle unless I explicitly ask. Summarize the score, axes, runtime, profile/config snapshot tags, configured and observed tools/skills, and any failed checks."""
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
            <p class="note">No public trace-backed result has been published for this exact scenario id yet.</p>
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
{criteria_html}
              <p class="note">Scenario timeout: {task['budget'].get('conclude_s')}s</p>
              <div class="recipe-actions">
                <button class="button primary copy-button" type="button" data-copy="{escape(benchmark_prompt, quote=True)}">Copy benchmark prompt</button>
                <span class="copy-reaction" data-copy-reaction aria-live="polite"></span>
              </div>
              <details class="prompt-expander benchmark-prompt">
                <summary>Benchmark Prompt</summary>
                <pre><code>{escape(benchmark_prompt)}</code></pre>
              </details>
              <section>
                <h3>Trace Evidence</h3>
                {leaderboard_html}
              </section>
            </div>
          </details>
        """)
    body = f"""
      <section class="recipe-search-hero">
        <p class="recipe-badge">{catalog['task_count']} recipes · {catalog['category_count']} categories</p>
        <h1>Search Recipes</h1>
        <p class="lede">Browse personal-agent recipes, filter by category, expand the criteria, then open the trace evidence behind the current baseline.</p>
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
            <span class="note">Open a recipe for goal, criteria, trace evidence, and benchmark CTA.</span>
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


def _render_tag_spans(items: list[str], *, limit: int = 8) -> str:
    shown = items[:limit]
    extra = len(items) - len(shown)
    html = "".join(f"<span>{escape(item)}</span>" for item in shown)
    if extra > 0:
        html += f"<span>+{extra} more</span>"
    return html or "<span>None published</span>"


def _render_role_cards(profile: dict) -> str:
    cards = []
    for role in profile.get("roles") or []:
        cards.append(f"""
          <article class="role-card">
            <div>
              <span class="mini-heading">Role</span>
              <strong><code>{escape(str(role.get('role') or '-'))}</code></strong>
            </div>
            <div>
              <span class="mini-heading">Profile</span>
              <span>{escape(str(role.get('profile') or '-'))}</span>
            </div>
            <div>
              <span class="mini-heading">Status</span>
              <span>{escape(_label_text(role.get('status')))}</span>
            </div>
            <p>{escape(str(role.get('evidence') or '-'))}</p>
          </article>
        """)
    return "".join(cards) or '<p class="note">No public profile roles were published.</p>'


def _render_score_cards(rows: list[dict], *, link_cases: bool = False) -> str:
    rendered = []
    for row in rows:
        label = row.get("case") if link_cases else row.get("suite_id")
        title = row.get("title") or label
        if link_cases:
            label_html = f'<a class="score-title" href="{escape(str(row.get("trace_url")))}">{escape(str(title))}</a>'
        else:
            label_html = f'<span class="score-title">{escape(_label_text(label))}</span>'
        rendered.append(f"""
          <article class="score-insight">
            <div>
              {label_html}
            </div>
            <strong>{escape(_score(row.get('score')))}</strong>
          </article>
        """)
    return "".join(rendered) or '<p class="note">No score rows available.</p>'


def _score_row_title(row: dict | None, *, link_case: bool = False) -> str:
    if not row:
        return "No data"
    label = row.get("case") if link_case else row.get("suite_id")
    title = row.get("title") or label
    if link_case and row.get("trace_url"):
        return f'<a href="{escape(str(row.get("trace_url")))}">{escape(str(title))}</a>'
    return escape(_label_text(title))


def _score_row_meta(row: dict | None, *, link_case: bool = False) -> str:
    if not row:
        return "-"
    label = row.get("case") if link_case else row.get("suite_id")
    return escape(str(label or "-"))


def _render_profile_readout(profile: dict, related: dict) -> str:
    top_suite = (related.get("top_suites") or [None])[0]
    low_suite = (related.get("improvement_suites") or [None])[0]
    return f"""
      <section class="profile-readout">
        <div class="readout-head">
          <div>
            <p class="eyebrow">Profile readout</p>
            <h3>Score and Recipe Fit</h3>
            <p class="note">Start here: what this profile bundle scored and where the profile shape currently works or fails.</p>
          </div>
          <a class="button primary" href="{escape(str(related.get('trace_url') or related.get('leaderboard_url')))}">Open traces</a>
        </div>
        <div class="profile-scoreboard">
          <article class="score-kpi primary">
            <span>Overall recipe score</span>
            <strong>{escape(_score(profile.get('overall_score')))}</strong>
            <small>Across published HermesBench recipes</small>
          </article>
          <article class="score-kpi">
            <span>Best suite</span>
            <strong>{escape(_score((top_suite or {}).get('score')))}</strong>
            <small>{_score_row_title(top_suite)}</small>
          </article>
          <article class="score-kpi warn">
            <span>Needs work</span>
            <strong>{escape(_score((low_suite or {}).get('score')))}</strong>
            <small>{_score_row_title(low_suite)}</small>
          </article>
        </div>
      </section>
    """


def _render_profile_setup(profile: dict, surface: dict, distribution: dict, memory: dict, role_statuses: str, related: dict) -> str:
    return f"""
      <section class="profile-layer setup-layer">
        <div class="layer-head">
          <p class="eyebrow">Setup</p>
          <h3>What Was Tested</h3>
          <p class="note">Only benchmark-relevant setup is shown by default. Full configured inventory stays collapsed below because configured tools are not proof of recipe behavior.</p>
        </div>
        <div class="profile-overview-grid">
          <dl class="detail-grid profile-metrics">
            <div><dt>Surface</dt><dd>{escape(str(surface.get('label') or '-'))}</dd></div>
            <div><dt>Model</dt><dd>{escape(str(profile.get('model_provider') or '-'))} / {escape(str(profile.get('model') or '-'))}</dd></div>
            <div><dt>Memory</dt><dd>{escape(str(memory.get('provider') or '-'))}, {escape('enabled' if memory.get('enabled') else 'disabled')}</dd></div>
            <div><dt>Distribution</dt><dd>{escape(str(distribution.get('form') or '-'))}</dd></div>
            <div><dt>Profile units</dt><dd>{escape(str(len(profile.get('profile_units') or [])))}</dd></div>
            <div><dt>Role status</dt><dd>{escape(role_statuses)}</dd></div>
            <div><dt>Profile hash</dt><dd><code>{escape(_short(profile.get('profile_hash'), 18))}</code></dd></div>
            <div><dt>Trace</dt><dd><a href="{escape(str(related.get('trace_json')))}">Trace JSON</a></dd></div>
          </dl>
          <div class="profile-link-panel">
            <a class="button primary" href="{escape(str(related.get('trace_url') or related.get('leaderboard_url')))}">Trace evidence</a>
            <a class="button" href="{escape(str(related.get('trace_json')))}">Trace JSON</a>
          </div>
        </div>
        <div class="profile-columns">
          <section>
            <h4>Distribution Shape</h4>
            <dl class="mini-defs">
              <div><dt>Form</dt><dd>{escape(str(distribution.get('form') or '-'))}</dd></div>
              <div><dt>Repo</dt><dd>{escape(str(distribution.get('repo_url') or 'not published'))}</dd></div>
              <div><dt>Version</dt><dd>{escape(str(distribution.get('version') or distribution.get('commit') or 'not published'))}</dd></div>
              <div><dt>Contract</dt><dd><a href="https://github.com/verkyyi/hermesbench/blob/main/docs/profile-distribution-baselines.md">profile distribution baselines</a></dd></div>
            </dl>
          </section>
          <section>
            <h4>Bundle Roles</h4>
            <dl class="mini-defs">
              <div><dt>Surface</dt><dd>{escape(str(surface.get('label') or '-'))}</dd></div>
              <div><dt>Contract</dt><dd>{escape(str(surface.get('prompt_case_contract') or '-'))}</dd></div>
              <div><dt>Roles</dt><dd>{escape(role_statuses)}</dd></div>
              <div><dt>Unit count</dt><dd>{escape(str(len(profile.get('profile_units') or [])))}</dd></div>
            </dl>
          </section>
        </div>
        <div class="role-card-list">{_render_bundle_roles(profile)}</div>
      </section>
    """


def _render_recipe_performance(related: dict) -> str:
    return f"""
      <section class="profile-layer performance-layer">
        <div class="layer-head">
          <p class="eyebrow">Recipes</p>
          <h3>Where It Performs</h3>
          <p class="note">Suites show broad profile fit. Individual recipes point to concrete evidence for wins and regressions.</p>
        </div>
        <div class="profile-columns performance-columns">
          <section>
            <h3>Strong Suites</h3>
            <div class="score-insight-list">{_render_score_cards(related.get('top_suites') or [])}</div>
          </section>
          <section>
            <h3>Improvement Suites</h3>
            <div class="score-insight-list">{_render_score_cards(related.get('improvement_suites') or [])}</div>
          </section>
          <section>
            <h3>Strong Recipes</h3>
            <div class="score-insight-list">{_render_score_cards(related.get('top_scenarios') or [], link_cases=True)}</div>
          </section>
          <section>
            <h3>Improvement Recipes</h3>
            <div class="score-insight-list">{_render_score_cards(related.get('improvement_scenarios') or [], link_cases=True)}</div>
          </section>
        </div>
      </section>
    """


def _render_snapshot_summary(summary: dict, distribution: dict, *, open_inventory: bool = False) -> str:
    target = summary.get("target") or {}
    memory = summary.get("memory") or {}
    kanban = summary.get("kanban") or {}
    tools = summary.get("tools") or {}
    skills = summary.get("agent_skills") or {}
    bench_env = summary.get("bench_env") or {}
    bench_env_tags = [f"{key}={value}" for key, value in bench_env.items()]
    snapshot_path = distribution.get("snapshot")
    source_note = f"Source: {snapshot_path}" if snapshot_path else "Source: profile fingerprint only"
    return f"""
      <section class="profile-snapshot">
        <h3>Snapshot Summary</h3>
        <p class="note">{escape(source_note)}. Private credentials, memories, sessions, local paths, logs, and raw state are omitted.</p>
        <dl class="detail-grid profile-metrics">
          <div><dt>Target</dt><dd>{escape(str(target.get('ui') or '-'))} / {escape(str(target.get('profile') or '-'))}</dd></div>
          <div><dt>Platform</dt><dd>{escape(str(target.get('platform') or '-'))}</dd></div>
          <div><dt>Model</dt><dd>{escape(str(summary.get('model_provider') or '-'))} / {escape(str(summary.get('model') or '-'))}</dd></div>
          <div><dt>Memory</dt><dd>{escape(str(memory.get('provider') or '-'))}, {escape('enabled' if memory.get('enabled') else 'disabled')}</dd></div>
          <div><dt>Orchestrator</dt><dd>{escape(str(kanban.get('orchestrator_profile') or '-'))}</dd></div>
          <div><dt>Max spawn</dt><dd>{escape(str(kanban.get('max_spawn') or '-'))}</dd></div>
        </dl>
        <details class="configured-inventory"{" open" if open_inventory else ""}>
          <summary>Configured inventory</summary>
          <p class="note">This is configuration inventory, not proof of use. The default usage view only shows tools and skills observed in public traces.</p>
          <dl class="detail-grid profile-metrics">
            <div><dt>Tool hash</dt><dd><code>{escape(str(tools.get('platform_toolset_hash') or '-'))}</code></dd></div>
            <div><dt>Skill hash</dt><dd><code>{escape(str(skills.get('hash') or '-'))}</code></dd></div>
          </dl>
          <div class="profile-columns">
            <section>
              <h4>Platform Toolsets</h4>
              <div class="tag-list">{_render_tag_spans(tools.get('platform_toolsets') or [], limit=14)}</div>
            </section>
            <section>
              <h4>AgentSkill Sample</h4>
              <div class="tag-list">{_render_tag_spans(skills.get('sample') or [], limit=14)}</div>
            </section>
            <section>
              <h4>Disabled Skills</h4>
              <div class="tag-list">{_render_tag_spans((skills.get('disabled') or []) + (skills.get('platform_disabled') or []), limit=14)}</div>
            </section>
            <section>
              <h4>Benchmark Env</h4>
              <div class="tag-list">{_render_tag_spans(bench_env_tags, limit=14)}</div>
            </section>
          </div>
        </details>
      </section>
    """


def _render_observed_usage(usage: dict) -> str:
    if not usage.get("recorded"):
        return f"""
          <section class="profile-snapshot">
            <h3>Used Tools and Skills</h3>
            <p class="note">{escape(str(usage.get('empty_note') or 'No public used-tool or used-skill telemetry was recorded.'))}</p>
          </section>
        """
    return f"""
      <section class="profile-snapshot">
        <h3>Used Tools and Skills</h3>
        <p class="note">Observed in public traces for this scored configuration. Configured-but-unused inventory is hidden in Snapshot Summary.</p>
        <div class="profile-columns">
          <section>
            <h4>Used Tools</h4>
            <div class="tag-list">{_render_tag_spans(usage.get('tools') or [], limit=18)}</div>
          </section>
          <section>
            <h4>Used Skills</h4>
            <div class="tag-list">{_render_tag_spans(usage.get('skills') or [], limit=18)}</div>
          </section>
        </div>
      </section>
    """


def _render_profile_units(profile: dict, *, open_cards: bool = False) -> str:
    units = profile.get("profile_units") or []
    if not units:
        return '<p class="note">No reusable profile units were published for this configuration.</p>'
    cards = []
    for unit in units:
        state = str(unit.get("publication_state") or "")
        state_class = " missing" if state == "missing_required_profile" else ""
        model = unit.get("model") or {}
        memory = unit.get("memory") or {}
        cards.append(f"""
          <details class="profile-unit-card{state_class}"{" open" if open_cards else ""}>
            <summary class="profile-unit-head">
              <div class="profile-unit-summary">
                <span class="mini-heading">{escape(_label_text(unit.get('role')))} profile</span>
                <h4>{escape(str(unit.get('profile') or '-'))}</h4>
              </div>
              <span class="profile-unit-role">{escape(_label_text(unit.get('role')))}</span>
            </summary>
            <div class="profile-unit-detail">
              <div class="profile-unit-state">
                <span>Status: {escape(_label_text(unit.get('status')))}</span>
                <span>{escape(str(unit.get('distribution_form') or '-'))}</span>
                <span>{escape(_label_text(unit.get('publication_state')))}</span>
              </div>
              <p>{escape(str(unit.get('evidence') or '-'))}</p>
              <dl class="detail-grid profile-metrics">
                <div><dt>Model</dt><dd>{escape(str(model.get('provider') or '-'))} / {escape(str(model.get('default') or '-'))}</dd></div>
                <div><dt>Memory</dt><dd>{escape(str(memory.get('provider') or '-'))}, {escape('enabled' if memory.get('enabled') else 'disabled')}</dd></div>
              </dl>
            </div>
          </details>
        """)
    return "".join(cards)


def _render_bundle_roles(profile: dict) -> str:
    roles = profile.get("roles") or []
    if not roles:
        return '<p class="note">No bundle roles were published.</p>'
    rows = []
    for role in roles:
        rows.append(f"""
          <article class="role-card">
            <div>
              <span class="mini-heading">Role</span>
              <strong><code>{escape(str(role.get('role') or '-'))}</code></strong>
            </div>
            <div>
              <span class="mini-heading">Profile</span>
              <span>{escape(str(role.get('profile') or '-'))}</span>
            </div>
            <div>
              <span class="mini-heading">Status</span>
              <span>{escape(_label_text(role.get('status')))}</span>
            </div>
            <p>{escape(str(role.get('evidence') or '-'))}</p>
          </article>
        """)
    return "".join(rows)


def _render_profile_unit_section(profile: dict, *, open_cards: bool = False) -> str:
    return f"""
      <section class="profile-layer unit-layer">
        <div class="layer-head">
          <p class="eyebrow">Profiles</p>
          <h3>Profile Units in This Setup</h3>
          <p class="note">These are the reusable profiles behind the scored configuration.</p>
        </div>
        <div class="profile-unit-list">{_render_profile_units(profile, open_cards=open_cards)}</div>
      </section>
    """


def _render_local_implementation_guidance() -> str:
    return """
      <section class="profile-loop">
        <h3>Learn and Implement Locally</h3>
        <ol>
          <li>Start from the reusable profile cards above; install the distribution when published, or copy the local implementation prompt for redacted profiles.</li>
          <li>Use strong suites and recipes to understand why this profile shape performed well.</li>
          <li>Bundle multiple profiles only through the published roles, keeping single profiles as the base unit.</li>
        </ol>
      </section>
    """


def _render_profile_content(
    profile: dict,
    related: dict,
    *,
    single_profile: bool = False,
) -> str:
    if single_profile:
        return f"""
          {_render_profile_readout(profile, related)}

          {_render_profile_unit_section(profile)}

          {_render_recipe_performance(related)}
        """
    return f"""
      {_render_profile_readout(profile, related)}

      {_render_profile_unit_section(profile)}

      {_render_recipe_performance(related)}
    """


def render_profiles_html(profile_index: dict) -> str:
    profiles = profile_index.get("profiles") or []
    profile_count = len(profiles)
    unit_count = int(profile_index.get("profile_unit_count") or 0)
    profile_count_label = "configuration bundle" if profile_count == 1 else "configuration bundles"
    surface_options = "\n".join(
        f'<option value="{escape(str(surface_id))}">{escape(_label_text(surface_id))}</option>'
        for surface_id in sorted({
            str((profile.get("execution_surface") or {}).get("id") or "direct")
            for profile in profiles
        })
    )
    single_profile = profile_count == 1
    profile_rows: list[str] = []
    for profile in profiles:
        baseline_id = str(profile.get("baseline_id") or "")
        surface = profile.get("execution_surface") or {}
        distribution = profile.get("distribution") or {}
        related = profile.get("related_scores") or {}
        search_text = " ".join([
            baseline_id,
            str(profile.get("model_provider") or ""),
            str(profile.get("model") or ""),
            str(surface.get("id") or ""),
            str(distribution.get("form") or ""),
            " ".join(profile.get("toolsets") or []),
            " ".join(profile.get("plugins_enabled") or []),
            " ".join(str(role.get("profile") or "") for role in profile.get("roles") or []),
            " ".join(str(unit.get("profile") or "") for unit in profile.get("profile_units") or []),
            " ".join(str(row.get("suite_id") or "") for row in related.get("suite_scores") or []),
        ]).lower()
        content = _render_profile_content(
            profile,
            related,
            single_profile=single_profile,
        )
        if single_profile:
            profile_rows.append(f"""
              <div class="profile-single" id="profile-{escape(_anchor(baseline_id))}" data-profile-row data-search="{escape(search_text)}" data-surface="{escape(str(surface.get('id') or 'direct'))}">
                <div class="profile-detail profile-detail-unwrapped">
                  {content}
                </div>
              </div>
            """)
        else:
            profile_rows.append(f"""
              <details class="profile-row" id="profile-{escape(_anchor(baseline_id))}" data-profile-row data-search="{escape(search_text)}" data-surface="{escape(str(surface.get('id') or 'direct'))}">
                <summary>
                  <span class="profile-summary-main">
                    <span>
                      <span class="profile-title">{escape(baseline_id)}</span>
                      <span class="table-subtext">{escape(str(surface.get('label') or _label_text(surface.get('id'))))} · {escape(str(len(profile.get('profile_units') or [])))} profile units · {escape(str(distribution.get('form') or 'profile_fingerprint_only'))}</span>
                    </span>
                  </span>
                  <span class="profile-summary-score">{escape(_score(profile.get('overall_score')))}</span>
                </summary>
                <div class="profile-detail">
                  {content}
                </div>
              </details>
            """)
    body = f"""
      <section class="recipe-search-hero">
        <p class="recipe-badge">{profile_count} {profile_count_label} · {unit_count} profile units</p>
        <h1>Profiles and Recipe Performance</h1>
        <p class="lede">Focus on the profile units in this bundle, the benchmark readout, and the recipe evidence behind the current score.</p>
        <div class="showcase-strip">
          <span>{profile_index.get('profile_count', 0)} scored setup</span>
          <span>{unit_count} profile units</span>
          <span>profile and recipe evidence</span>
        </div>
      </section>
      <section class="section compact">
        <div class="profile-list" data-profile-list>
          {''.join(profile_rows) if profile_rows else '<p class="note">No public profile architecture baselines have been generated yet.</p>'}
        </div>
        <script>
          (() => {{
            const hash = (location.hash || "").slice(1);
            if (hash) {{
              const row = document.getElementById(hash);
              if (row?.matches("[data-profile-row]")) {{
                if ("open" in row) row.open = true;
              }}
            }}
          }})();
        </script>
      </section>
    """
    return _page_shell("Profiles", body)


def render_traces_html(index: dict, traces: list[dict]) -> str:
    trace_blocks: list[str] = []
    for trace in traces:
        case_cards = []
        suite_count = len({case.get("suite_id") for case in trace["cases"] if case.get("suite_id")})
        transcript_turns = sum(len(case.get("public_transcript") or []) for case in trace["cases"])
        event_count = sum(len(case.get("public_events") or []) for case in trace["cases"])
        tool_event_count = sum(
            1
            for case in trace["cases"]
            for event in (case.get("public_events") or [])
            if str(event.get("type")) in {"tool_call", "tool_result", "tool_step"}
        )
        categories = sorted({
            (
                str(((case.get("task") or {}).get("category_id")) or case.get("suite_id") or ""),
                str(((case.get("task") or {}).get("category_label")) or _label_text(case.get("suite_id"))),
            )
            for case in trace["cases"]
            if case.get("suite_id") or (case.get("task") or {}).get("category_id")
        }, key=lambda item: item[1])
        category_options = "\n".join(
            f'<option value="{escape(category_id)}">{escape(label)}</option>'
            for category_id, label in categories
        )
        for case in trace["cases"]:
            driver = case.get("driver_decision") or {}
            judge = case.get("judge") or {}
            mech = case.get("mechanical") or {}
            task = case.get("task") or {}
            prompt = task.get("prompt") or "Task definition came from a prior suite set; see the stored case-result row."
            title = str(task.get("title") or _title_from_id(str(case.get("case") or "")))
            category_id = str(task.get("category_id") or case.get("suite_id") or "")
            category_label = str(task.get("category_label") or _label_text(case.get("suite_id")))
            closure = _label_text(driver.get("closure_type") or driver.get("scenario_closed"))
            case_events = case.get("public_events") or []
            case_tool_events = [
                event for event in case_events
                if str(event.get("type")) in {"tool_call", "tool_result", "tool_step"}
            ]
            search_text = " ".join([
                str(case.get("case") or ""),
                title,
                category_id,
                category_label,
                prompt,
                str(judge.get("reason") or ""),
                str(driver.get("reason") or ""),
                str(trace.get("baseline_id") or ""),
            ]).lower()
            card_id = f"trace-{_anchor(trace['baseline_id'])}-{_anchor(case.get('case'))}"
            score = _score(case.get("score"))
            score_class = " zero" if _float_or_none(case.get("score")) in (None, 0.0) else ""
            case_cards.append(f"""
              <details class="trace-detail trace-recipe-card" id="{escape(card_id)}" data-trace-row data-category="{escape(category_id)}" data-search="{escape(search_text)}">
                <summary class="trace-card-summary">
                  <span class="trace-card-main">
                    <span class="trace-card-header">
                      <span class="trace-card-category">{escape(category_label)}</span>
                    </span>
                    <span class="trace-card-title">{escape(title)}</span>
                    <span class="trace-card-prompt">{escape(_short(prompt, 180))}</span>
                  </span>
                  <span class="trace-card-result">
                    <span class="trace-card-score{score_class}">{escape(score)}</span>
                    <span class="trace-card-status">{escape(closure)}</span>
                  </span>
                </summary>
                <div class="case-narrative">
                  <section>
                    <h3>Task</h3>
                    <div class="task-prompt">{escape(prompt)}</div>
                  </section>
                  <section>
                    <h3>Outcome Readout</h3>
                    <div class="readout-grid">
                      <div>
                        <h4>Driver Decision</h4>
                        <p>{escape(str(driver.get('reason') or driver))}</p>
                      </div>
                      <div>
                        <h4>Judge Summary</h4>
                        <p>{escape(str(judge.get('reason') or judge))}</p>
                      </div>
                    </div>
                  </section>
                  <section>
                    <h3>Trace Timeline</h3>
                    {_render_trace_timeline(case)}
                  </section>
                  <details class="conversation-only">
                    <summary>Conversation-only transcript</summary>
                    {_render_transcript(case)}
                  </details>
                </div>
              </details>
            """)
        trace_blocks.append(f"""
        <section class="section compact trace-results-section" id="trace-{escape(_anchor(trace['baseline_id']))}">
          <div class="trace-browser-panel" data-trace-browser>
            <div class="trace-results-head">
              <div>
                <p class="eyebrow">Recipe traces</p>
                <h1>Recipe results with traces</h1>
              </div>
            </div>
            <label class="search-label" for="trace-search-{escape(_anchor(trace['baseline_id']))}">Search recipe results</label>
            <input id="trace-search-{escape(_anchor(trace['baseline_id']))}" class="task-search" type="search" data-trace-search placeholder="Search recipe, category, prompt, result..." />
            <div class="recipe-filters" aria-label="Trace filters">
              <select data-trace-category aria-label="Filter traces by category">
                <option value="">All categories</option>
                {category_options}
              </select>
              <button class="button" type="button" data-trace-clear>Clear</button>
            </div>
            <div class="recipe-count-row">
              <span><strong data-trace-count>{trace.get('case_count')}</strong> matching recipe traces</span>
            </div>
          </div>
          <div class="trace-recipe-list">{''.join(case_cards)}</div>
        </section>
        """)
    body = f"""
      {''.join(trace_blocks)}
      <script>
        (() => {{
          const browsers = Array.from(document.querySelectorAll("[data-trace-browser]"));
          browsers.forEach((browser) => {{
            const section = browser.closest("section");
            const rows = Array.from(section.querySelectorAll("[data-trace-row]"));
            const search = browser.querySelector("[data-trace-search]");
            const category = browser.querySelector("[data-trace-category]");
            const clear = browser.querySelector("[data-trace-clear]");
            const count = browser.querySelector("[data-trace-count]");
            const apply = () => {{
              const query = (search.value || "").trim().toLowerCase();
              const categoryValue = category.value || "";
              let visible = 0;
              rows.forEach((row) => {{
                const ok = (!query || (row.dataset.search || "").includes(query))
                  && (!categoryValue || row.dataset.category === categoryValue);
                row.hidden = !ok;
                if (ok) visible += 1;
              }});
              if (count) count.textContent = String(visible);
            }};
            [search, category].forEach((item) => {{
              item.addEventListener("input", apply);
              item.addEventListener("change", apply);
            }});
            clear.addEventListener("click", () => {{
              search.value = "";
              category.value = "";
              apply();
              search.focus();
            }});
            apply();
          }});
          const hash = (location.hash || "").slice(1);
          if (hash) {{
            const row = document.getElementById(hash);
            if (row?.matches("[data-trace-row]")) {{
              row.open = true;
              row.scrollIntoView({{ block: "start" }});
            }}
          }}
        }})();
      </script>
    """
    return _page_shell("Traces", body)


def build_public_artifacts(repo_root: Path) -> dict:
    """Generate repo and website task/trace artifacts."""
    data_root = repo_root / "data"
    tasks_root = data_root / "tasks"
    baselines_root = data_root / "baselines"
    traces_root = data_root / "traces"
    profiles_root = data_root / "profiles"
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
    if (repo_root / ".git").exists():
        sync_local_kanban_profile_snapshots(profiles_root)
    profile_index = build_profile_architecture_index(baselines_root, traces, profiles_root)
    _write_json(profiles_root / "index.json", profile_index)

    catalog = enrich_task_catalog_with_leaderboards(catalog, traces)
    _write_json(tasks_root / "tasks.json", catalog)
    _write_text(tasks_root / "README.md", render_tasks_markdown(catalog))

    _write_text(site_root / "recipes.html", render_tasks_html(catalog))
    _write_text(site_root / "profiles.html", render_profiles_html(profile_index))
    _write_text(site_root / "traces.html", render_traces_html(index, traces))
    _write_text(site_root / LEGACY_LEADERBOARD_PAGE, _redirect_page("Traces", TRACE_PAGE))
    _write_text(site_root / "tasks.html", _redirect_page("Recipes", "recipes.html"))
    _mirror_tree(tasks_root, site_root / "data" / "tasks")
    _mirror_tree(profiles_root, site_root / "data" / "profiles")
    _mirror_tree(traces_root, site_root / "data" / "traces")
    return {
        "tasks": catalog["task_count"],
        "traces": index["trace_count"],
        "profiles": profile_index["profile_count"],
        "profile_units": profile_index["profile_unit_count"],
        "tasks_path": str(tasks_root / "tasks.json"),
        "traces_path": str(traces_root / "index.json"),
        "profiles_path": str(profiles_root / "index.json"),
        "site_recipes": str(site_root / "recipes.html"),
        "site_profiles": str(site_root / "profiles.html"),
        "site_leaderboard": str(site_root / "leaderboard.html"),
        "site_tasks": str(site_root / "tasks.html"),
        "site_traces": str(site_root / "traces.html"),
    }
