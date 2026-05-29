"""Public-safe observability extraction from upstream Hermes artifacts.

HermesBench treats Hermes as a black-box target. This module only reads local
artifacts that upstream Hermes already writes inside the isolated benchmark
home/workdir, and it probes every SQLite schema before reading columns.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|auth(?:orization)?|bearer|cookie|credential|password|"
    r"private[_-]?key|refresh[_-]?token|secret|session[_-]?cookie|token)",
    re.IGNORECASE,
)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def _select_cols(cols: set[str], wanted: list[str]) -> str:
    selected = [col for col in wanted if col in cols]
    return ", ".join(selected) if selected else ""


def _json_loads(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def _redact_value(value: Any, *, max_chars: int = 240) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            key_str = str(key)
            out[key_str] = "<redacted>" if _SECRET_KEY_RE.search(key_str) else _redact_value(item)
        return out
    if isinstance(value, list):
        return [_redact_value(item) for item in value[:20]]
    if isinstance(value, str):
        text = value
        text = re.sub(r"\b(?:sk|ghp|gho|xoxb|xoxp|AKIA)[A-Za-z0-9_\-]{12,}\b", "<redacted:token>", text)
        return text[:max_chars] + ("..." if len(text) > max_chars else "")
    return value


def _tool_name_from_call(call: Any) -> str | None:
    if isinstance(call, str):
        return call or None
    if not isinstance(call, dict):
        return None
    if call.get("name"):
        return str(call["name"])
    function = call.get("function")
    if isinstance(function, dict) and function.get("name"):
        return str(function["name"])
    return None


def _extract_tool_calls_from_message(row: dict) -> list[dict]:
    calls = []
    for call in _json_loads(row.get("tool_calls"), []) or []:
        name = _tool_name_from_call(call)
        if not name:
            continue
        calls.append({
            "name": name,
            "source": "state_db.messages.tool_calls",
            "tool_call_id": str(call.get("id") or "") if isinstance(call, dict) else "",
            "status": "observed",
            "args_retention": "omitted_public_safe",
            "result_retention": "omitted_public_safe",
        })
    return calls


def _parse_trajectory_tool_names(value: str) -> list[str]:
    names: list[str] = []
    for block in re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", value or "", flags=re.DOTALL):
        payload = _json_loads(block, {})
        name = _tool_name_from_call(payload)
        if name:
            names.append(name)
    for block in re.findall(r"<tool_response>\s*(.*?)\s*</tool_response>", value or "", flags=re.DOTALL):
        payload = _json_loads(block, {})
        name = _tool_name_from_call(payload)
        if name:
            names.append(name)
    return names


def _dedupe_tools(tools: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in tools:
        key = (item.get("name"), item.get("source"), item.get("tool_call_id"))
        if not item.get("name") or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _source_missing(name: str, path: Path, reason: str) -> dict:
    return {
        "available": False,
        "path": str(path),
        "reason": reason,
        "confidence": "high",
    }


def _redact_paths(value: Any, *, home: Path, workdir: Path) -> Any:
    if isinstance(value, dict):
        return {key: _redact_paths(item, home=home, workdir=workdir) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_paths(item, home=home, workdir=workdir) for item in value]
    if isinstance(value, str):
        text = value
        text = text.replace(str(workdir), "<benchmark_workdir>")
        text = text.replace(str(home), "<isolated_home>")
        return text
    return value


def _read_telemetry_db(home: Path, session_id: str | None) -> tuple[dict, dict | None, list[dict]]:
    path = home / "telemetry.db"
    if not path.exists():
        return _source_missing("telemetry_db", path, "telemetry.db not found in isolated home"), None, []
    try:
        with _connect(path) as conn:
            tables = _tables(conn)
            turns_cols = _columns(conn, "turns") if "turns" in tables else set()
            spans_cols = _columns(conn, "spans") if "spans" in tables else set()
            source = {
                "available": "turns" in tables,
                "path": str(path),
                "schema": {
                    "tables": sorted(tables),
                    "turns_columns": sorted(turns_cols),
                    "spans_columns": sorted(spans_cols),
                },
                "confidence": "high" if "turns" in tables else "medium",
            }
            turn = None
            if "turns" in tables:
                wanted = [
                    "id", "session_id", "started_at_ms", "ended_at_ms", "platform",
                    "profile", "model", "provider", "turn_class", "status", "error",
                    "ttfa_ms", "ttft_ms", "ttlt_ms", "ttfs_ms", "output_chars",
                    "tool_count", "attributes_json",
                ]
                cols = _select_cols(turns_cols, wanted)
                if cols:
                    where = ""
                    params: tuple[Any, ...] = ()
                    if session_id and "session_id" in turns_cols:
                        where = "WHERE session_id = ?"
                        params = (session_id,)
                    row = conn.execute(
                        f"SELECT {cols} FROM turns {where} ORDER BY started_at_ms DESC LIMIT 1",
                        params,
                    ).fetchone()
                    if row:
                        turn = dict(row)
                        if "attributes_json" in turn:
                            turn["attributes"] = _redact_value(_json_loads(turn.pop("attributes_json"), {}))
            spans: list[dict] = []
            if turn and "spans" in tables and "turn_id" in spans_cols:
                wanted = ["name", "status", "error", "start_ms", "end_ms", "attributes_json"]
                cols = _select_cols(spans_cols, wanted)
                if cols:
                    rows = conn.execute(
                        f"SELECT {cols} FROM spans WHERE turn_id = ? ORDER BY start_ms LIMIT 25",
                        (turn.get("id"),),
                    ).fetchall()
                    for row in rows:
                        item = dict(row)
                        if "attributes_json" in item:
                            item["attributes"] = _redact_value(_json_loads(item.pop("attributes_json"), {}))
                        spans.append(item)
            return source, turn, spans
    except sqlite3.Error as exc:
        return _source_missing("telemetry_db", path, f"sqlite error: {exc}"), None, []


def _read_state_db(home: Path, session_id: str | None) -> tuple[dict, dict | None, list[dict], list[dict]]:
    path = home / "state.db"
    if not path.exists():
        return _source_missing("state_db", path, "state.db not found in isolated home"), None, [], []
    try:
        with _connect(path) as conn:
            tables = _tables(conn)
            sessions_cols = _columns(conn, "sessions") if "sessions" in tables else set()
            messages_cols = _columns(conn, "messages") if "messages" in tables else set()
            source = {
                "available": "sessions" in tables or "messages" in tables,
                "path": str(path),
                "schema": {
                    "tables": sorted(tables),
                    "sessions_columns": sorted(sessions_cols),
                    "messages_columns": sorted(messages_cols),
                },
                "confidence": "high" if "messages" in tables else "medium",
            }
            session = None
            resolved_session_id = session_id
            if "sessions" in tables and sessions_cols:
                wanted = ["id", "source", "model", "message_count", "tool_call_count", "api_call_count", "started_at", "ended_at"]
                cols = _select_cols(sessions_cols, wanted)
                if cols:
                    where = ""
                    params: tuple[Any, ...] = ()
                    if session_id and "id" in sessions_cols:
                        where = "WHERE id = ?"
                        params = (session_id,)
                    row = conn.execute(f"SELECT {cols} FROM sessions {where} ORDER BY started_at DESC LIMIT 1", params).fetchone()
                    if row:
                        session = dict(row)
                        resolved_session_id = str(session.get("id") or resolved_session_id or "")
            messages: list[dict] = []
            tools: list[dict] = []
            if "messages" in tables and messages_cols:
                wanted = ["id", "session_id", "role", "content", "tool_call_id", "tool_calls", "tool_name", "timestamp", "finish_reason"]
                cols = _select_cols(messages_cols, wanted)
                if cols:
                    where = ""
                    params = ()
                    if resolved_session_id and "session_id" in messages_cols:
                        where = "WHERE session_id = ?"
                        params = (resolved_session_id,)
                    rows = conn.execute(f"SELECT {cols} FROM messages {where} ORDER BY id LIMIT 200", params).fetchall()
                    for row in rows:
                        msg = dict(row)
                        messages.append({
                            "id": msg.get("id"),
                            "role": msg.get("role"),
                            "tool_name": msg.get("tool_name"),
                            "has_tool_calls": bool(msg.get("tool_calls")),
                            "finish_reason": msg.get("finish_reason"),
                        })
                        tools.extend(_extract_tool_calls_from_message(msg))
                        if msg.get("role") == "tool" and msg.get("tool_name"):
                            tools.append({
                                "name": str(msg["tool_name"]),
                                "source": "state_db.messages.tool_name",
                                "tool_call_id": str(msg.get("tool_call_id") or ""),
                                "status": "observed_result",
                                "args_retention": "omitted_public_safe",
                                "result_retention": "omitted_public_safe",
                            })
            return source, session, messages, _dedupe_tools(tools)
    except sqlite3.Error as exc:
        return _source_missing("state_db", path, f"sqlite error: {exc}"), None, [], []


def _read_trajectories(workdir: Path) -> tuple[dict, list[dict], list[dict]]:
    paths = [
        path for name in ("trajectory_samples.jsonl", "failed_trajectories.jsonl")
        for path in [workdir / name]
        if path.exists()
    ]
    if not paths:
        return {
            "available": False,
            "path": str(workdir),
            "reason": "no upstream trajectory JSONL files found",
            "confidence": "high",
        }, [], []
    entries: list[dict] = []
    tools: list[dict] = []
    for path in paths:
        try:
            for line in path.read_text(encoding="utf-8").splitlines()[-5:]:
                if not line.strip():
                    continue
                entry = _json_loads(line, {})
                if not isinstance(entry, dict):
                    continue
                conversations = entry.get("conversations") or []
                for msg in conversations:
                    if not isinstance(msg, dict):
                        continue
                    for name in _parse_trajectory_tool_names(str(msg.get("value") or "")):
                        tools.append({
                            "name": name,
                            "source": f"trajectory:{path.name}",
                            "status": "observed",
                            "args_retention": "omitted_public_safe",
                            "result_retention": "omitted_public_safe",
                        })
                entries.append({
                    "path": str(path),
                    "model": entry.get("model"),
                    "completed": entry.get("completed"),
                    "conversation_turns": len(conversations),
                    "raw_conversations": "omitted_public_safe",
                })
        except OSError:
            continue
    return {
        "available": bool(entries),
        "path": str(workdir),
        "files": [str(path) for path in paths],
        "format": "sharegpt_jsonl",
        "confidence": "high" if entries else "medium",
    }, entries, _dedupe_tools(tools)


def _candidate_kanban_paths(home: Path) -> list[Path]:
    paths = [
        home / "kanban.db",
        home / "kanban" / "kanban.db",
        home / "state" / "kanban.db",
        *sorted(home.glob("kanban*.db")),
    ]
    if (home / "kanban").exists():
        paths.extend(sorted((home / "kanban").glob("*.db")))
    return paths


def _read_kanban(home: Path) -> tuple[dict, dict]:
    paths = []
    for path in _candidate_kanban_paths(home):
        if path.exists() and path not in paths:
            paths.append(path)
    if not paths:
        return {
            "available": False,
            "reason": "no upstream kanban SQLite DB found in isolated home",
            "confidence": "medium",
        }, {"used": False, "tasks_created": 0, "profiles": [], "status_counts": {}, "handoffs": []}
    path = paths[0]
    try:
        with _connect(path) as conn:
            tables = _tables(conn)
            tasks_cols = _columns(conn, "tasks") if "tasks" in tables else set()
            links_cols = _columns(conn, "task_links") if "task_links" in tables else set()
            events_cols = _columns(conn, "events") if "events" in tables else set()
            source = {
                "available": "tasks" in tables,
                "path": str(path),
                "schema": {
                    "tables": sorted(tables),
                    "tasks_columns": sorted(tasks_cols),
                    "task_links_columns": sorted(links_cols),
                    "events_columns": sorted(events_cols),
                },
                "confidence": "medium",
            }
            status_counts: dict[str, int] = {}
            profiles: set[str] = set()
            tasks_created = 0
            if "tasks" in tables and tasks_cols:
                if "status" in tasks_cols:
                    for row in conn.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status").fetchall():
                        status_counts[str(row["status"])] = int(row["n"])
                tasks_created = sum(status_counts.values()) if status_counts else int(conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"])
                for col in ("assignee", "owner", "profile"):
                    if col in tasks_cols:
                        for row in conn.execute(f"SELECT DISTINCT {col} AS profile FROM tasks WHERE {col} IS NOT NULL").fetchall():
                            if row["profile"]:
                                profiles.add(str(row["profile"]))
            handoffs = []
            if "task_links" in tables and {"parent_id", "child_id"} <= links_cols:
                for row in conn.execute("SELECT parent_id, child_id FROM task_links LIMIT 25").fetchall():
                    handoffs.append({
                        "from": str(row["parent_id"]),
                        "to": str(row["child_id"]),
                        "status": "linked",
                    })
            synthesis_observed = False
            if "events" in tables and events_cols:
                text_cols = [c for c in ("kind", "event_type", "type", "message") if c in events_cols]
                if text_cols:
                    expr = " || ' ' || ".join(f"COALESCE({c}, '')" for c in text_cols)
                    row = conn.execute(
                        f"SELECT COUNT(*) AS n FROM events WHERE lower({expr}) LIKE '%synth%' OR lower({expr}) LIKE '%complete%'"
                    ).fetchone()
                    synthesis_observed = bool(row and row["n"])
            return source, {
                "used": tasks_created > 0,
                "tasks_created": tasks_created,
                "profiles": sorted(profiles),
                "status_counts": status_counts,
                "handoffs": handoffs,
                "synthesis_observed": synthesis_observed,
                "returned_to_origin": None,
                "retention": "public_safe_metadata_only",
            }
    except sqlite3.Error as exc:
        return _source_missing("kanban", path, f"sqlite error: {exc}"), {"used": False, "tasks_created": 0, "profiles": [], "status_counts": {}, "handoffs": []}


def extract(home: str | Path, workdir: str | Path, *, session_id: str | None = None) -> dict:
    """Extract public-safe observability from upstream Hermes artifacts."""
    home_path = Path(home)
    workdir_path = Path(workdir)
    telemetry_source, turn, spans = _read_telemetry_db(home_path, session_id)
    state_source, session, messages, state_tools = _read_state_db(home_path, session_id)
    trajectory_source, trajectory_entries, trajectory_tools = _read_trajectories(workdir_path)
    kanban_source, kanban = _read_kanban(home_path)
    tools = _dedupe_tools([*state_tools, *trajectory_tools])
    skills = sorted({
        tool["name"].removeprefix("skill_")
        for tool in tools
        if str(tool.get("name") or "").startswith("skill_")
    })
    resolved_session_id = session_id or (turn or {}).get("session_id") or (session or {}).get("id")
    out = {
        "sources": {
            "telemetry_db": telemetry_source,
            "state_db": state_source,
            "trajectory": trajectory_source,
            "kanban": kanban_source,
        },
        "turn": turn or {},
        "spans": spans,
        "session": session or {},
        "session_id": resolved_session_id,
        "messages": {
            "count": len(messages),
            "sample": messages[:20],
            "retention": "content_omitted_public_safe",
        },
        "tools": tools,
        "skills": skills,
        "trajectory": {
            "entries": trajectory_entries,
            "retention": {
                "raw_conversations": "omitted_public_safe",
            },
        },
        "kanban": kanban,
        "retention": {
            "raw_tool_args": "omitted_public_safe",
            "raw_tool_results": "omitted_public_safe",
            "raw_kanban_payloads": "omitted_public_safe",
            "raw_trajectory": "omitted_unless_opted_in",
        },
    }
    return _redact_paths(out, home=home_path, workdir=workdir_path)
