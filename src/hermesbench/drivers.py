"""Driver adapters.

Drivers orchestrate scenarios against a target adapter. HermesBench prompt
suites are agent-driven: a Codex headless controller provides bounded user
turns and observations, then reports whether the scenario closed. The driver
does not solve the task for the target.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import shlex
import subprocess
import time
from pathlib import Path


@dataclass
class CodexDriver:
    """Use Codex headless mode as a bounded evaluator-side controller."""

    max_turns: int

    def run(self, scenario: dict, target, *, timeout_s: int) -> dict:
        if not hasattr(target, "start_agentic_session"):
            raise ValueError("target does not support agentic evaluator sessions")
        session = target.start_agentic_session(timeout_s=timeout_s, max_turns=self.max_turns)
        controller = _run_codex_controller(
            scenario=scenario,
            session=session,
            timeout_s=_codex_timeout_s(timeout_s),
            max_turns=self.max_turns,
        )
        result = session.finish(controller=controller)
        decision = controller.get("decision") or {}
        if isinstance(decision, dict):
            result["driver_decision"] = decision
            result["driver_reply"] = str(decision.get("driver_reply") or decision.get("reason") or "")
            if "scenario_closed" in decision:
                result["driver_scenario_closed"] = bool(decision.get("scenario_closed"))
                if result["driver_scenario_closed"]:
                    result["scenario_completion_rate"] = 1.0
        result["driver"] = {
            "kind": "codex",
            "max_turns": self.max_turns,
            "turns_sent": result.get("turn_count", 0),
            "controller": controller,
        }
        return result


def _codex_max_turns(scenario: dict) -> int:
    raw = scenario.get("driver") or {}
    if os.environ.get("HERMES_BENCH_AGENTIC_MAX_TURNS"):
        return max(1, int(os.environ["HERMES_BENCH_AGENTIC_MAX_TURNS"]))
    if raw.get("_declared_max_turns"):
        return max(1, int(raw.get("max_turns") or 1))
    return max(1, int(raw.get("max_turns") or 1), 2)


def _codex_timeout_s(timeout_s: int) -> int:
    if os.environ.get("HERMES_BENCH_CODEX_TIMEOUT_S"):
        return max(1, int(os.environ["HERMES_BENCH_CODEX_TIMEOUT_S"]))
    # Controller time covers its reasoning plus all target turns.
    return max(timeout_s + 60, timeout_s * 3)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _quote_command(parts: list[str]) -> str:
    return " ".join(shlex.quote(str(p)) for p in parts)


def _controller_prompt(scenario: dict, session, *, max_turns: int) -> str:
    declared_turns = [
        {"turn": idx, "prompt": str(turn.get("prompt") or "")}
        for idx, turn in enumerate(scenario.get("turns") or [], start=1)
    ]
    payload = {
        "scenario_id": scenario.get("id"),
        "audience": scenario.get("audience"),
        "category": scenario.get("category"),
        "goal": scenario.get("goal"),
        "expectation": scenario.get("expectation"),
        "notes": scenario.get("notes") or "",
        "initial_prompt": scenario.get("initial_prompt"),
        "declared_turns": declared_turns,
        "checks": scenario.get("checks") or [],
        "max_turns": max_turns,
    }
    bridge = _quote_command(session.bridge_command + ["-"])
    status = _quote_command(session.status_command)
    return (
        "You are the HermesBench evaluator-side driver, not the target agent.\n"
        "Your job is to orchestrate a bounded user conversation with the target "
        "through the provided bridge command. Do not solve the user's task "
        "yourself, do not edit target artifacts yourself, and do not inspect "
        "secrets. Only send natural user turns to the target and observe the "
        "target's replies/artifacts.\n\n"
        "Rules:\n"
        "1. Send the initial prompt as the first target turn exactly as written.\n"
        "2. If declared_turns contains later turns, send them in order before "
        "creating your own follow-up turns.\n"
        "3. Optimize for speed: most scenarios should finish after one target "
        "turn. Do not send a follow-up just to improve or polish an already "
        "evaluable reply.\n"
        "4. Send a follow-up only when a declared turn remains, the target "
        "failed to respond, or the target explicitly asks for missing user "
        "information that the scenario provides. Do not coach the target with "
        "the rubric.\n"
        "5. Stop after max_turns. Stop earlier when the target reaches a clear "
        "terminal answer, refusal, clarification, or scoped artifact result.\n"
        "6. Your final response must be JSON only: "
        "{\"done\": true, \"scenario_closed\": true|false, "
        "\"closure_type\": \"completed|rejected|clarification|none\", "
        "\"turns_sent\": <n>, \"driver_reply\": \"optional user-facing summary\", "
        "\"reason\": \"one sentence\"}.\n\n"
        "To send a target turn, pipe the user text on stdin:\n"
        f"printf '%s\\n' 'YOUR USER TURN' | {bridge}\n\n"
        f"To inspect transcript/artifact status, run:\n{status}\n\n"
        "Scenario JSON:\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}"
    )


def _run_codex_controller(*, scenario: dict, session, timeout_s: int, max_turns: int) -> dict:
    prompt = _controller_prompt(scenario, session, max_turns=max_turns)
    last_message_path = Path(session.control_dir) / "codex-final.json"
    schema_path = Path(session.control_dir) / "codex-output-schema.json"
    schema_path.write_text(json.dumps({
        "type": "object",
        "additionalProperties": False,
        "required": ["done", "scenario_closed", "closure_type", "turns_sent", "driver_reply", "reason"],
        "properties": {
            "done": {"type": "boolean"},
            "scenario_closed": {"type": "boolean"},
            "closure_type": {"type": "string", "enum": ["completed", "rejected", "clarification", "none"]},
            "turns_sent": {"type": "integer", "minimum": 0},
            "driver_reply": {"type": "string"},
            "reason": {"type": "string"},
        },
    }, indent=2), encoding="utf-8")
    model = os.environ.get("HERMES_BENCH_CODEX_MODEL")
    profile = os.environ.get("HERMES_BENCH_CODEX_PROFILE")
    sandbox = os.environ.get("HERMES_BENCH_CODEX_SANDBOX")
    bypass = os.environ.get("HERMES_BENCH_CODEX_BYPASS_SANDBOX")
    use_bypass = bypass.lower() in {"1", "true", "yes", "on"} if bypass is not None else sandbox is None
    if use_bypass:
        cmd = [
            os.environ.get("HERMES_BENCH_CODEX_BIN") or "codex",
            "--dangerously-bypass-approvals-and-sandbox",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-C",
            str(session.control_dir),
            "-o",
            str(last_message_path),
            "--output-schema",
            str(schema_path),
        ]
    else:
        cmd = [
            os.environ.get("HERMES_BENCH_CODEX_BIN") or "codex",
            "--ask-for-approval",
            "never",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            sandbox,
            "-C",
            str(session.control_dir),
            "--add-dir",
            str(session.home),
            "--add-dir",
            str(session.control_dir),
            "-o",
            str(last_message_path),
            "--output-schema",
            str(schema_path),
        ]
    if model:
        cmd.extend(["-m", model])
    if profile:
        cmd.extend(["-p", profile])
    cmd.append(prompt)

    env = dict(os.environ)
    src = str(_repo_root() / "src")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else src

    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=session.control_dir, env=env, capture_output=True, text=True, timeout=timeout_s)
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": 124,
            "timed_out": True,
            "wall_ms": round((time.monotonic() - start) * 1000.0, 1),
            "stdout_tail": (exc.stdout or "")[-1000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-1000:] if isinstance(exc.stderr, str) else "",
            "final_message": "",
            "decision": {},
            "error": f"codex controller timeout after {timeout_s}s",
        }

    final_message = ""
    if last_message_path.exists():
        final_message = last_message_path.read_text(encoding="utf-8")[:2000]
    decision = _parse_controller_decision(final_message)
    return {
        "returncode": proc.returncode,
        "timed_out": timed_out,
        "wall_ms": round((time.monotonic() - start) * 1000.0, 1),
        "stdout_tail": (proc.stdout or "")[-1000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
        "final_message": final_message,
        "decision": decision,
        "error": None if proc.returncode == 0 else f"codex controller exited {proc.returncode}",
    }


def _parse_controller_decision(content: str) -> dict:
    if not content:
        return {}
    s = content.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1]
            if s.lstrip().lower().startswith("json"):
                s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start:end + 1]
    try:
        data = json.loads(s)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    closure_type = str(data.get("closure_type") or "none").strip().lower()
    if closure_type not in {"completed", "rejected", "clarification", "none"}:
        closure_type = "none"
    return {
        "done": bool(data.get("done")),
        "scenario_closed": bool(data.get("scenario_closed")),
        "closure_type": closure_type,
        "turns_sent": data.get("turns_sent"),
        "driver_reply": str(data.get("driver_reply") or "")[:1000],
        "reason": str(data.get("reason") or "")[:1000],
    }


def build_driver(scenario: dict):
    kind = str((scenario.get("driver") or {}).get("kind") or "codex").strip().lower()
    if kind != "codex":
        raise ValueError(f"unsupported driver kind: {kind}; HermesBench prompt suites are agent-driven")
    return CodexDriver(max_turns=_codex_max_turns(scenario))


def run(scenario: dict, target, *, timeout_s: int) -> dict:
    """Run one scenario using its configured driver."""
    return build_driver(scenario).run(scenario, target, timeout_s=timeout_s)
