"""Target adapters.

Target adapters are the only layer that knows how to talk to a concrete agent
framework. Cases and drivers stay target-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from hermesbench import harness


@dataclass
class TargetConfig:
    """Runtime-selected target UI/capability surface."""

    ui: str = "cli"
    profile: str = "default"
    platform: str = "cli"
    toolsets: str | None = None
    skills: str | None = None
    command: str | None = None

    @classmethod
    def from_env(cls) -> "TargetConfig":
        raw_ui = (
            os.environ.get("HERMES_BENCH_TARGET_UI")
            or os.environ.get("HERMES_BENCH_TARGET_INTERFACE")
            or "cli"
        ).strip()
        ui = raw_ui or "cli"
        platform = (os.environ.get("HERMES_BENCH_TARGET_PLATFORM") or "").strip()
        if ui.startswith("platform:"):
            platform = platform or ui.split(":", 1)[1].strip()
            ui = "cli"
        elif ui not in {"cli", "command"}:
            # Simulate a messaging/UI platform through the Hermes CLI transport:
            # platform-specific toolsets/skills are selected, without sending a
            # real Telegram/Weixin/etc. message.
            platform = platform or ui
            ui = "cli"
        platform = platform or "cli"
        return cls(
            ui=ui,
            profile=(os.environ.get("HERMES_BENCH_TARGET_PROFILE") or "default"),
            platform=platform,
            toolsets=(os.environ.get("HERMES_BENCH_TARGET_TOOLSETS") or None),
            skills=(os.environ.get("HERMES_BENCH_TARGET_SKILLS") or None),
            command=(os.environ.get("HERMES_BENCH_TARGET_COMMAND") or None),
        )

    def describe(self) -> dict:
        return {
            "ui": self.ui,
            "profile": self.profile,
            "platform": self.platform,
            "toolsets": self.toolsets,
            "skills": self.skills,
            "command_configured": bool(self.command),
        }


@dataclass
class HermesAgenticSession:
    """Prepared Hermes target session for out-of-process evaluator drivers."""

    home: Path
    workdir: Path
    control_dir: Path
    state_path: Path
    timeout_s: int
    max_turns: int
    config: TargetConfig

    @classmethod
    def create(cls, *, timeout_s: int, max_turns: int, config: TargetConfig) -> "HermesAgenticSession":
        src_home = harness._default_home()
        harness._ensure_warm(src_home)
        home = harness._make_isolated_home(src_home)
        workdir = home / "workdir"
        workdir.mkdir(parents=True, exist_ok=True)
        control_dir = Path(tempfile.mkdtemp(prefix="hb-codex-driver-"))
        state_path = control_dir / "session.json"
        state = {
            "version": 1,
            "target": "hermes-cli",
            "home": str(home),
            "workdir": str(workdir),
            "timeout_s": int(timeout_s),
            "turn_timeout_s": int(timeout_s),
            "max_turns": int(max_turns),
            "target_ui": config.ui,
            "target_profile": config.profile,
            "target_platform": config.platform,
            "target_toolsets": config.toolsets,
            "target_skills": config.skills,
            "target_command": config.command,
            "target_session_id": None,
            "turns": [],
            "transcript": [],
        }
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        return cls(
            home=home,
            workdir=workdir,
            control_dir=control_dir,
            state_path=state_path,
            timeout_s=timeout_s,
            max_turns=max_turns,
            config=config,
        )

    @property
    def bridge_command(self) -> list[str]:
        return [
            os.environ.get("HERMES_BENCH_PYTHON") or sys.executable,
            "-m",
            "hermesbench.agentic_bridge",
            "send",
            str(self.state_path),
            "--prompt",
        ]

    @property
    def status_command(self) -> list[str]:
        return [
            os.environ.get("HERMES_BENCH_PYTHON") or sys.executable,
            "-m",
            "hermesbench.agentic_bridge",
            "status",
            str(self.state_path),
        ]

    def finish(self, *, controller: dict | None = None) -> dict:
        state = json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {}
        results = list(state.get("turns") or [])
        transcript = list(state.get("transcript") or [])
        final_side_effects = harness._artifact_manifest(self.workdir)
        retained_home = None
        if os.environ.get("HERMES_BENCH_KEEP_ARTIFACTS"):
            retained_home = str(self.home)
        else:
            shutil.rmtree(self.home, ignore_errors=True)
            shutil.rmtree(self.control_dir, ignore_errors=True)

        if not results:
            return {
                "prompt": "",
                "reply": "",
                "returncode": None,
                "timed_out": bool((controller or {}).get("timed_out")),
                "responded": False,
                "stable": False,
                "concluded": False,
                "ttfa_ms": None,
                "ttft_ms": None,
                "ttlt_ms": None,
                "wall_ms": (controller or {}).get("wall_ms"),
                "telemetry_status": None,
                "model": None,
                "error": (controller or {}).get("error") or "agentic driver sent no target turns",
                "side_effects": final_side_effects,
                "artifact_home": retained_home,
                "turns": [],
                "transcript": [],
                "turn_count": 0,
                "expected_turn_count": self.max_turns,
                "scenario_completion_rate": 0.0,
            }

        final = results[-1]
        return {
            **final,
            "turns": results,
            "transcript": transcript,
            "turn_count": len(results),
            "expected_turn_count": self.max_turns,
            "responded": all(r.get("responded") for r in results),
            "stable": all(r.get("stable") for r in results),
            "concluded": all(r.get("concluded") for r in results),
            "wall_ms": sum(float(r.get("wall_ms") or 0.0) for r in results),
            "ttfa_ms": final.get("ttfa_ms"),
            "ttlt_ms": final.get("ttlt_ms"),
            "reply": str(final.get("reply") or ""),
            "side_effects": final_side_effects,
            "artifact_home": retained_home,
            "scenario_completion_rate": len(results) / max(1, self.max_turns),
        }


@dataclass
class HermesCliTarget:
    """Target adapter for Hermes `chat -q` in an isolated benchmark session."""

    config: TargetConfig

    def __init__(self, config: TargetConfig | None = None):
        self.config = config or TargetConfig.from_env()

    def run_turns(self, turns: list[dict], *, timeout_s: int) -> dict:
        if len(turns) == 1:
            result = harness.run_case(
                turns[0]["prompt"],
                timeout_s=timeout_s,
                profile=self.config.profile,
                toolsets=turns[0].get("toolsets") or self.config.toolsets,
                skills=turns[0].get("skills") or self.config.skills,
                platform=self.config.platform,
                target_ui=self.config.ui,
                target_command=self.config.command,
            )
            result["turns"] = [dict(result, turn_index=1, profile="default")]
            result["transcript"] = [
                {
                    "turn": 1,
                    "user": turns[0]["prompt"],
                    "assistant": result.get("reply", ""),
                    "error": result.get("error"),
                    "timed_out": result.get("timed_out"),
                    "wall_ms": result.get("wall_ms"),
                    "offset_ms": result.get("wall_ms"),
                }
            ]
            result["turn_count"] = 1
            result["expected_turn_count"] = 1
            result["scenario_completion_rate"] = 1.0
            return result
        return harness.run_scenario(
            turns,
            timeout_s=timeout_s,
            profile=self.config.profile,
            toolsets=self.config.toolsets,
            skills=self.config.skills,
            platform=self.config.platform,
            target_ui=self.config.ui,
            target_command=self.config.command,
        )

    def start_agentic_session(self, *, timeout_s: int, max_turns: int) -> HermesAgenticSession:
        return HermesAgenticSession.create(timeout_s=timeout_s, max_turns=max_turns, config=self.config)

    def describe(self) -> dict:
        return self.config.describe()


def build_target() -> HermesCliTarget:
    """Build the target adapter for this run.

    The first public implementation targets Hermes. Other target frameworks can
    plug in here without changing cases.
    """
    return HermesCliTarget(TargetConfig.from_env())
