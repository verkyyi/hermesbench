"""Command bridge used by out-of-process agentic evaluator drivers.

The Codex evaluator driver runs as a separate process, so it cannot call the
in-memory target adapter directly. This module exposes a small CLI that sends a
single user turn to the prepared target session and records the observable
reply/transcript in a JSON state file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from hermesbench import harness


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _read_prompt(value: str | None) -> str:
    if value == "-" or value is None:
        return sys.stdin.read()
    return value


def send_turn(
    state_path: Path,
    *,
    prompt: str,
    profile: str = "default",
    toolsets: str | None = None,
    timeout_s: int | None = None,
) -> dict:
    state = _load(state_path)
    turns = list(state.get("turns") or [])
    max_turns = int(state.get("max_turns") or 1)
    if len(turns) >= max_turns:
        out = {
            "ok": False,
            "error": f"max_turns reached ({max_turns})",
            "turn_count": len(turns),
            "max_turns": max_turns,
        }
        print(json.dumps(out, indent=2), flush=True)
        return out

    prompt = prompt.strip()
    if not prompt:
        out = {"ok": False, "error": "empty prompt", "turn_count": len(turns), "max_turns": max_turns}
        print(json.dumps(out, indent=2), flush=True)
        return out

    home = Path(state["home"])
    workdir = Path(state["workdir"])
    rc, reply, timed_out, err, row, wall_ms = harness._spawn_in_session(
        prompt,
        home=home,
        workdir=workdir,
        timeout_s=int(timeout_s or state.get("turn_timeout_s") or state.get("timeout_s") or 120),
        profile=profile,
        toolsets=toolsets,
    )
    side_effects = harness._artifact_manifest(workdir)
    result = harness._turn_result(
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
    result["turn_index"] = len(turns) + 1
    result["profile"] = profile
    turns.append(result)
    transcript = list(state.get("transcript") or [])
    transcript.append({"turn": result["turn_index"], "user": prompt, "assistant": reply})
    state["turns"] = turns
    state["transcript"] = transcript
    state["side_effects"] = side_effects
    _save(state_path, state)

    out = {
        "ok": True,
        "turn": result["turn_index"],
        "turn_count": len(turns),
        "max_turns": max_turns,
        "responded": result["responded"],
        "stable": result["stable"],
        "concluded": result["concluded"],
        "reply": reply,
        "side_effects": side_effects,
    }
    print(json.dumps(out, indent=2), flush=True)
    return out


def status(state_path: Path) -> dict:
    state = _load(state_path)
    out = {
        "turn_count": len(state.get("turns") or []),
        "max_turns": state.get("max_turns"),
        "transcript": state.get("transcript") or [],
        "side_effects": harness._artifact_manifest(Path(state["workdir"])),
    }
    print(json.dumps(out, indent=2), flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hermesbench.agentic_bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)

    send = sub.add_parser("send", help="send one user turn to the target session")
    send.add_argument("state")
    send.add_argument("--prompt", "-p", help="prompt text; use '-' or omit to read stdin")
    send.add_argument("--profile", default="default")
    send.add_argument("--toolsets")
    send.add_argument("--timeout-s", type=int)

    stat = sub.add_parser("status", help="print transcript and side-effect summary")
    stat.add_argument("state")

    args = ap.parse_args(argv)
    if args.cmd == "send":
        out = send_turn(
            Path(args.state),
            prompt=_read_prompt(args.prompt),
            profile=args.profile,
            toolsets=args.toolsets,
            timeout_s=args.timeout_s,
        )
        return 0 if out.get("ok") else 2
    if args.cmd == "status":
        status(Path(args.state))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
