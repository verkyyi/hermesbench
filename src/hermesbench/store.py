"""Time-series store for HermesBench runs (SQLite at $HERMES_HOME/hermesbench.db).

Writes are once-daily, single-process and serial, so we deliberately avoid WAL
(a torn WAL checkpoint under a concurrent burst is what corrupted kanban.db on
2026-05-27). A rollback journal with synchronous=FULL is the safest choice for a
low-frequency single writer and removes that failure mode entirely.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def default_db_path() -> Path:
    home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    return Path(home) / "hermesbench.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    ts            TEXT NOT NULL,           -- ISO8601 UTC, supplied by caller
    overall_score REAL,                    -- weighted over suites that ran
    passed        INTEGER NOT NULL,        -- legacy compatibility; score is the verdict
    suites_ran    INTEGER NOT NULL,
    git_sha       TEXT,
    model_id      TEXT,
    profile_hash  TEXT,
    profile_snapshot TEXT                 -- JSON, redacted
);
CREATE TABLE IF NOT EXISTS suite_results (
    run_id      TEXT NOT NULL,
    suite_id    TEXT NOT NULL,
    category    TEXT,
    mode        TEXT,
    score       REAL,
    passed      INTEGER,                    -- legacy compatibility; score is the verdict
    skipped     INTEGER NOT NULL DEFAULT 0,
    skip_reason TEXT,
    error       TEXT,
    duration_s  REAL,
    metrics     TEXT,                       -- JSON
    PRIMARY KEY (run_id, suite_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_runs_ts ON runs(ts);
"""


@contextmanager
def _connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()


def init(db_path: Path | None = None) -> None:
    db_path = db_path or default_db_path()
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        _ensure_columns(conn)
        conn.commit()


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
    if "profile_snapshot" not in cols:
        conn.execute("ALTER TABLE runs ADD COLUMN profile_snapshot TEXT")


def save_run(report: dict, db_path: Path | None = None) -> None:
    """Persist a full run report (the dict produced by run.run_benchmark)."""
    db_path = db_path or default_db_path()
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        _ensure_columns(conn)
        h = report["harness"]
        # The schema keeps the old pass/fail columns for existing dashboard DBs.
        # Product surfaces should use score only.
        legacy_passed = report.get("overall_score") is not None
        conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(run_id, ts, overall_score, passed, suites_ran, "
            " git_sha, model_id, profile_hash, profile_snapshot) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                report["run_id"], report["ts"],
                report.get("overall_score"), 1 if legacy_passed else 0,
                report["suites_ran"],
                h.get("git_sha"), h.get("model_id"), h.get("profile_hash"),
                json.dumps(h.get("profile_snapshot") or {}),
            ),
        )
        for s in report["suites"]:
            conn.execute(
                "INSERT OR REPLACE INTO suite_results "
                "(run_id, suite_id, category, mode, score, passed, "
                " skipped, skip_reason, error, duration_s, metrics) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    report["run_id"], s["id"], s.get("category"), s.get("mode"),
                    s.get("score"),
                    None,
                    1 if s.get("skipped") else 0, s.get("skip_reason"),
                    s.get("error"), s.get("duration_s"),
                    json.dumps(s.get("metrics") or {}),
                ),
            )
        conn.commit()


def recent_runs(limit: int = 30, db_path: Path | None = None) -> list[dict]:
    """Most-recent runs first, each with its per-suite results attached."""
    db_path = db_path or default_db_path()
    if not Path(db_path).exists():
        return []
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        _ensure_columns(conn)
        runs = [dict(r) for r in conn.execute(
            "SELECT * FROM runs ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()]
        for r in runs:
            r.pop("passed", None)
            try:
                r["profile_snapshot"] = json.loads(r.get("profile_snapshot") or "{}")
            except (TypeError, ValueError):
                r["profile_snapshot"] = {}
            r["suites"] = []
            for s in conn.execute(
                "SELECT * FROM suite_results WHERE run_id=? ORDER BY suite_id",
                (r["run_id"],),
            ).fetchall():
                sd = dict(s)
                sd["id"] = sd["suite_id"]  # match the in-memory report shape
                sd["skipped"] = bool(sd["skipped"])
                sd.pop("passed", None)
                try:
                    sd["metrics"] = json.loads(sd.get("metrics") or "{}")
                except (TypeError, ValueError):
                    sd["metrics"] = {}
                r["suites"].append(sd)
        return runs


def previous_run(before_run_id: str, db_path: Path | None = None) -> dict | None:
    """The run immediately preceding ``before_run_id`` (by ts), or None."""
    runs = recent_runs(limit=200, db_path=db_path)
    seen = False
    for r in runs:  # newest-first
        if seen:
            return r
        if r["run_id"] == before_run_id:
            seen = True
    return None
