"""HermesBench v2 — isolated agent driver (black box).

Drives the default profile exactly as an end user would (`hermes chat -q ...`)
inside a throwaway HERMES_HOME. A scenario can be one turn or many turns; the
harness keeps the same isolated home/workdir for the whole scenario so chat
state and scoped side effects can carry across turns. It reports only what's
observable from outside: replies and mechanical reliability signals (did it
respond, how fast, did it stay stable, did it reach terminal conclusions within
budget). No kanban/orchestrator internals are inspected by prompt scenarios.

Each call runs in its own temp HERMES_HOME (config.yaml + .env + context-length
cache copied from the real default profile) plus a benchmark-owned working
directory. Side effects are allowed inside that working directory and summarized
before cleanup; real chats, production boards, external messaging, money, and
cloud infrastructure are out of scope for the default prompt suites. Built on
the same isolation pattern as evals/responsiveness/run_live.
"""

from __future__ import annotations

import os
import hashlib
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from pathlib import Path

_ERROR_STATUSES = {"error", "failed", "failure", "exception"}

_SIDE_EFFECT_SCOPE = """

[HermesBench side-effect scope]
You are running inside a benchmark-owned sandbox. If the user asks for an action
with side effects, only act inside the current working directory or the
HERMES_BENCH_WORKDIR directory. Do not mutate real user data, send external
messages, spend money, restart production services, or change cloud
infrastructure in default HermesBench prompt suites. If an action would exceed
that scope, ask for confirmation/context or state the boundary clearly.
"""

# Per-process warm-up. The first measured turn would otherwise pay a cold-start
# tax (cold OS file cache, cold provider/model) unrelated to the agent's
# steady-state responsiveness — and the 04:00 cron always runs cold. We run one
# throwaway, tool-free turn first (under a lock, so concurrent trials all wait
# for it) so measured turns reflect warm steady-state and are comparable
# day-to-day. Set HERMES_BENCH_WARMUP=0 to skip.
_warm_lock = threading.Lock()
_warmed = False


def _hermes_argv() -> list[str]:
    try:
        from hermes_cli import kanban_db as kb
        return list(kb._resolve_hermes_argv())  # type: ignore[attr-defined]
    except Exception:
        return ["hermes"]


def _default_home() -> Path:
    from hermes_cli.profiles import resolve_profile_env
    return Path(resolve_profile_env("default"))


def _make_isolated_home(src_home: Path) -> Path:
    home = Path(tempfile.mkdtemp(prefix="hb-usecase-"))
    for name in ("config.yaml", ".env", "context_length_cache.yaml"):
        s = src_home / name
        if s.exists():
            shutil.copy2(s, home / name)
            try:
                (home / name).chmod(0o600)
            except OSError:
                pass
    return home


def _scope_prompt(prompt: str) -> str:
    return f"{prompt.rstrip()}{_SIDE_EFFECT_SCOPE}"


def _artifact_manifest(workdir: Path, *, limit: int = 25) -> dict:
    files = []
    total_files = 0
    total_bytes = 0
    if not workdir.exists():
        return {"scope": "benchmark_workdir", "total_files": 0, "total_bytes": 0, "files": []}

    for path in sorted(p for p in workdir.rglob("*") if p.is_file()):
        total_files += 1
        try:
            stat = path.stat()
        except OSError:
            continue
        total_bytes += stat.st_size
        if len(files) >= limit:
            continue
        rel = path.relative_to(workdir).as_posix()
        digest = None
        if stat.st_size <= 1024 * 1024:
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            except OSError:
                digest = None
        files.append({"path": rel, "bytes": stat.st_size, "sha256_16": digest})
    return {
        "scope": "benchmark_workdir",
        "total_files": total_files,
        "total_bytes": total_bytes,
        "files": files,
        "truncated": total_files > len(files),
    }


def _read_turn_row(home: Path) -> dict | None:
    db = home / "telemetry.db"
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(str(db), timeout=2.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT ttfa_ms, ttft_ms, ttlt_ms, status, model, output_chars "
            "FROM turns ORDER BY started_at_ms DESC LIMIT 1"
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    return dict(row) if row else None


def _spawn_in_session(
    prompt: str,
    *,
    home: Path,
    workdir: Path,
    timeout_s: int,
    profile: str = "default",
    toolsets: str | None = None,
):
    """Run one `hermes chat -q` turn inside an existing isolated session."""
    env = dict(os.environ)
    env["HERMES_HOME"] = str(home)
    env["HERMES_PROFILE"] = profile
    env["HERMES_BENCH_WORKDIR"] = str(workdir)
    env["HERMES_BENCH_SIDE_EFFECT_SCOPE"] = "benchmark_workdir"
    env.pop("HERMES_KANBAN_TASK", None)
    cmd = [*_hermes_argv(), "chat", "-q", _scope_prompt(prompt), "--quiet"]
    if toolsets is not None:
        cmd.extend(["--toolsets", toolsets])

    reply, rc, timed_out, err = "", None, False, None
    wall0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, env=env, cwd=workdir, capture_output=True, text=True, timeout=timeout_s)
        rc = proc.returncode
        reply = (proc.stdout or "").strip()
        if rc != 0 and not reply:
            err = (proc.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        rc, timed_out, err = 124, True, f"timeout after {timeout_s}s"
    except Exception as exc:
        rc, err = 1, f"{type(exc).__name__}: {exc}"[:400]
    wall_ms = round((time.monotonic() - wall0) * 1000.0, 1)
    row = _read_turn_row(home)
    return rc, reply, timed_out, err, row, wall_ms


def _turn_result(
    *,
    prompt: str,
    rc,
    reply: str,
    timed_out: bool,
    err: str | None,
    row: dict | None,
    wall_ms: float,
    side_effects: dict,
    retained_home: str | None,
) -> dict:
    status = (row or {}).get("status")
    responded = (rc == 0) and bool(reply)
    stable = (rc == 0) and (not timed_out) and (str(status or "").lower() not in _ERROR_STATUSES)
    concluded = responded and not timed_out

    return {
        "prompt": prompt,
        "reply": reply,
        "returncode": rc,
        "timed_out": timed_out,
        "responded": responded,
        "stable": stable,
        "concluded": concluded,
        "ttfa_ms": (row or {}).get("ttfa_ms"),
        "ttft_ms": (row or {}).get("ttft_ms"),
        "ttlt_ms": (row or {}).get("ttlt_ms"),
        "wall_ms": wall_ms,
        "telemetry_status": status,
        "model": (row or {}).get("model"),
        "error": err,
        "side_effects": side_effects,
        "artifact_home": retained_home,
    }


def _spawn(prompt: str, *, src_home: Path, timeout_s: int, toolsets: str | None = None):
    """Run one isolated `hermes chat -q` turn."""
    home = _make_isolated_home(src_home)
    workdir = home / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    retained_home = None
    try:
        rc, reply, timed_out, err, row, wall_ms = _spawn_in_session(
            prompt, home=home, workdir=workdir, timeout_s=timeout_s, toolsets=toolsets
        )
    finally:
        side_effects = _artifact_manifest(workdir)
        if os.environ.get("HERMES_BENCH_KEEP_ARTIFACTS"):
            retained_home = str(home)
        else:
            shutil.rmtree(home, ignore_errors=True)
    return rc, reply, timed_out, err, row, wall_ms, side_effects, retained_home


def _ensure_warm(src_home: Path) -> None:
    """Once per process, run a throwaway tool-free turn to warm OS/provider caches."""
    global _warmed
    if _warmed or os.environ.get("HERMES_BENCH_WARMUP") == "0":
        return
    with _warm_lock:
        if _warmed:
            return
        try:
            _spawn("Reply with the single word: ready.", src_home=src_home,
                   timeout_s=120, toolsets="__none__")
        except Exception:
            pass
        _warmed = True


def run_case(prompt: str, *, timeout_s: int, src_home: Path | None = None) -> dict:
    """Drive one isolated default-profile turn. Returns reply + mechanical signals.

    Mechanical signals (no LLM judgement):
      responded  — process exited 0 with a non-empty reply
      stable     — exited 0, not a timeout, telemetry status not an error
      concluded  — responded AND not timed out (a terminal reply arrived in budget)
      ttfa_ms / ttlt_ms / wall_ms — latency (telemetry; wall is the fallback)

    A one-time per-process warm-up runs first (see module note) so measured
    latency reflects warm steady-state, not cold start.
    """
    src_home = src_home or _default_home()
    _ensure_warm(src_home)
    rc, reply, timed_out, err, row, wall_ms, side_effects, retained_home = _spawn(
        prompt, src_home=src_home, timeout_s=timeout_s
    )

    return _turn_result(
        prompt=prompt,
        rc=rc,
        reply=reply,
        timed_out=timed_out,
        err=err,
        row=row,
        wall_ms=wall_ms,
        side_effects=side_effects,
        retained_home=retained_home,
    )


def run_scenario(
    turns: list[dict],
    *,
    timeout_s: int,
    src_home: Path | None = None,
    stop_on_error: bool = True,
) -> dict:
    """Drive a multi-turn scenario in one isolated Hermes session.

    ``turns`` is a list of objects with at least ``prompt``. Optional keys:
    ``profile`` (defaults to ``default``), ``toolsets``, and ``timeout_s``.
    The return shape preserves the final turn fields for backwards-compatible
    scoring and adds ``turns``/``transcript`` for multi-turn judges.
    """
    if not turns:
        raise ValueError("scenario must contain at least one turn")

    src_home = src_home or _default_home()
    _ensure_warm(src_home)
    home = _make_isolated_home(src_home)
    workdir = home / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    retained_home = None
    results: list[dict] = []
    transcript: list[dict] = []

    try:
        for idx, turn in enumerate(turns, start=1):
            prompt = str(turn.get("prompt") or "").strip()
            if not prompt:
                raise ValueError(f"scenario turn {idx} missing prompt")
            rc, reply, timed_out, err, row, wall_ms = _spawn_in_session(
                prompt,
                home=home,
                workdir=workdir,
                timeout_s=int(turn.get("timeout_s") or timeout_s),
                profile=str(turn.get("profile") or "default"),
                toolsets=turn.get("toolsets"),
            )
            side_effects = _artifact_manifest(workdir)
            result = _turn_result(
                prompt=prompt,
                rc=rc,
                reply=reply,
                timed_out=timed_out,
                err=err,
                row=row,
                wall_ms=wall_ms,
                side_effects=side_effects,
                retained_home=None,
            )
            result["turn_index"] = idx
            result["profile"] = str(turn.get("profile") or "default")
            results.append(result)
            transcript.append({"turn": idx, "user": prompt, "assistant": reply})
            if stop_on_error and (not result["stable"] or timed_out):
                break
    finally:
        final_side_effects = _artifact_manifest(workdir)
        if os.environ.get("HERMES_BENCH_KEEP_ARTIFACTS"):
            retained_home = str(home)
        else:
            shutil.rmtree(home, ignore_errors=True)

    final = results[-1] if results else {}
    return {
        **final,
        "turns": results,
        "transcript": transcript,
        "turn_count": len(results),
        "expected_turn_count": len(turns),
        "responded": bool(results) and all(r["responded"] for r in results),
        "stable": bool(results) and all(r["stable"] for r in results),
        "concluded": bool(results) and all(r["concluded"] for r in results),
        "wall_ms": sum(float(r.get("wall_ms") or 0.0) for r in results),
        "ttfa_ms": final.get("ttfa_ms"),
        "ttlt_ms": final.get("ttlt_ms"),
        "reply": str(final.get("reply") or ""),
        "side_effects": final_side_effects,
        "artifact_home": retained_home,
        "scenario_completion_rate": len(results) / len(turns),
    }
