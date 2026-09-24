"""Upgrade builder queue: the iOS app's "Build this upgrade" button files a
request here, a Muse worker picks it up, implements the change (backend +
iOS), pushes, rebuilds on Varun's Mac, and installs on his iPhone. After a
deploy, the app offers an Undo button that reverts the upgrade commit(s) and
reinstalls the previous build.

State lives in Postgres when DATABASE_URL is set (a free Neon database), so
the queue survives Render restarts and redeploys. Without DATABASE_URL it
falls back to data/upgrades.json with atomic writes (local dev; still
ephemeral on Render's free tier, so a redeploy wipes it).

Job lifecycle:
    pending -> building -> deployed -> undo_requested -> undoing -> undone
    any non-terminal -> failed (with an error message)

Only one job is active at a time; requesting while one is active is refused
with HTTP 409 so upgrades never interleave.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("pulse.upgrades")

ACTIVE_STATES = {"pending", "building", "deployed", "undo_requested", "undoing"}
TERMINAL_STATES = {"failed", "undone"}

_JOB_COLS = (
    "id", "idea_id", "title", "detail", "measure", "effort", "status",
    "previous_sha", "commit_sha", "revert_sha", "error",
    "created_at", "updated_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Postgres store (used when DATABASE_URL is configured) ──────────────────

_db_init_done = False


def _db_configured() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def _db_connect():
    """Connect to Postgres. Raises on failure when DATABASE_URL is set —
    loud is better than silently splitting the queue across two stores."""
    import psycopg2

    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10)
    conn.autocommit = True
    return conn


@contextmanager
def _pg():
    conn = _db_connect()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _db_init(conn) -> None:
    global _db_init_done
    if _db_init_done:
        return
    defs = []
    for c in _JOB_COLS:
        d = f"{c} TEXT"
        if c in ("id", "status"):
            d += " NOT NULL"
        defs.append(d)
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS upgrade_jobs (seq SERIAL PRIMARY KEY, "
            + ", ".join(defs)
            + ", UNIQUE (id))"
        )
        cur.execute("SELECT COUNT(*) FROM upgrade_jobs")
        if cur.fetchone()[0] == 0:
            _migrate_json(conn)
    _db_init_done = True
    log.info("upgrade queue: postgres")


def _migrate_json(conn) -> None:
    """One-time import of the legacy JSON queue (best effort)."""
    jobs = _json_load()
    if not jobs:
        return
    cols = ", ".join(_JOB_COLS)
    placeholders = ", ".join(["%s"] * len(_JOB_COLS))
    with conn.cursor() as cur:
        for j in jobs:
            try:
                cur.execute(
                    f"INSERT INTO upgrade_jobs ({cols}) VALUES ({placeholders})",
                    [j.get(c) for c in _JOB_COLS],
                )
            except Exception:
                continue
    log.info("upgrade queue: migrated %d jobs from JSON", len(jobs))


def _row_to_job(row) -> dict:
    return dict(zip(_JOB_COLS, row))


def _db_latest() -> dict | None:
    cols = ", ".join(_JOB_COLS)
    with _pg() as conn:
        _db_init(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {cols} FROM upgrade_jobs ORDER BY seq DESC LIMIT 1"
            )
            row = cur.fetchone()
    return _row_to_job(row) if row else None


def _db_by_status(status: str) -> list[dict]:
    cols = ", ".join(_JOB_COLS)
    with _pg() as conn:
        _db_init(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {cols} FROM upgrade_jobs WHERE status = %s ORDER BY seq",
                (status,),
            )
            rows = cur.fetchall()
    return [_row_to_job(r) for r in rows]


def _db_create(idea: dict) -> dict:
    cols = ", ".join(_JOB_COLS)
    placeholders = ", ".join(["%s"] * len(_JOB_COLS))
    job = {
        "id": uuid.uuid4().hex[:8],
        "idea_id": str(idea.get("idea_id", "")),
        "title": str(idea.get("title", "")),
        "detail": str(idea.get("detail", "")),
        "measure": str(idea.get("measure", "")),
        "effort": str(idea.get("effort", "")),
        "status": "pending",
        "previous_sha": None,
        "commit_sha": None,
        "revert_sha": None,
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    with _pg() as conn:
        _db_init(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM upgrade_jobs WHERE status = ANY(%s) LIMIT 1",
                (list(ACTIVE_STATES),),
            )
            if cur.fetchone():
                raise ValueError("another upgrade is already in progress")
            cur.execute(
                f"INSERT INTO upgrade_jobs ({cols}) VALUES ({placeholders})",
                [job[c] for c in _JOB_COLS],
            )
    return job


def _db_transition(job_id: str, from_states: set[str], to_state: str,
                   **fields) -> dict | None:
    cols = ", ".join(_JOB_COLS)
    set_clauses = ["status = %s", "updated_at = %s"]
    params: list = [to_state, _now()]
    for k, v in fields.items():
        if k not in _JOB_COLS:
            continue
        set_clauses.append(f"{k} = %s")
        params.append(v)
    params += [job_id, list(from_states)]
    with _pg() as conn:
        _db_init(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE upgrade_jobs SET {', '.join(set_clauses)} "
                f"WHERE id = %s AND status = ANY(%s) "
                f"RETURNING {cols}",
                params,
            )
            row = cur.fetchone()
    return _row_to_job(row) if row else None


# ── JSON file store (fallback when DATABASE_URL is not configured) ─────────

def _json_path() -> Path:
    from options_seller.paths import data_dir
    return data_dir() / "upgrades.json"


def _json_load() -> list[dict]:
    try:
        data = json.loads(_json_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _json_save(jobs: list[dict]) -> None:
    p = _json_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs, indent=1), encoding="utf-8")
    tmp.replace(p)


def _json_touch(job: dict) -> None:
    job["updated_at"] = _now()


def _json_latest() -> dict | None:
    jobs = _json_load()
    return jobs[-1] if jobs else None


def _json_find(jobs: list[dict], job_id: str) -> dict | None:
    return next((j for j in jobs if j.get("id") == job_id), None)


def _json_create(idea: dict) -> dict:
    jobs = _json_load()
    if any(j.get("status") in ACTIVE_STATES for j in jobs):
        raise ValueError("another upgrade is already in progress")
    job = {
        "id": uuid.uuid4().hex[:8],
        "idea_id": str(idea.get("idea_id", "")),
        "title": str(idea.get("title", "")),
        "detail": str(idea.get("detail", "")),
        "measure": str(idea.get("measure", "")),
        "effort": str(idea.get("effort", "")),
        "status": "pending",
        "previous_sha": None,
        "commit_sha": None,
        "revert_sha": None,
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    jobs.append(job)
    _json_save(jobs)
    return job


def _json_transition(job_id: str, from_states: set[str], to_state: str,
                     **fields) -> dict | None:
    jobs = _json_load()
    job = _json_find(jobs, job_id)
    if job is None or job.get("status") not in from_states:
        return None
    job["status"] = to_state
    for k, v in fields.items():
        job[k] = v
    _json_touch(job)
    _json_save(jobs)
    return job


# ── Public API (same signatures as before; main.py is unchanged) ────────────

def _use_db() -> bool:
    return _db_configured()


def store() -> str:
    """Which backing store the queue is using — surfaced so we can verify
    the database is actually live."""
    return "postgres" if _use_db() else "json"


def latest_job() -> dict | None:
    """The most recent job of any status (what the app shows)."""
    if _use_db():
        return _db_latest()
    return _json_latest()


def pending_jobs() -> list[dict]:
    if _use_db():
        return _db_by_status("pending")
    return [j for j in _json_load() if j.get("status") == "pending"]


def undo_requested_jobs() -> list[dict]:
    if _use_db():
        return _db_by_status("undo_requested")
    return [j for j in _json_load() if j.get("status") == "undo_requested"]


def create_job(idea: dict) -> dict:
    """File a new upgrade request. Refuses when another job is active."""
    if _use_db():
        return _db_create(idea)
    return _json_create(idea)


def _transition(job_id: str, from_states: set[str], to_state: str,
                **fields) -> dict | None:
    if _use_db():
        return _db_transition(job_id, from_states, to_state, **fields)
    return _json_transition(job_id, from_states, to_state, **fields)


def claim(job_id: str) -> dict | None:
    """Worker picks up a pending job. Records what is currently deployed so
    undo can restore it."""
    return _transition(
        job_id, {"pending"}, "building",
        previous_sha=os.environ.get("RENDER_GIT_COMMIT"),
    )


def complete(job_id: str, commit_sha: str) -> dict | None:
    return _transition(job_id, {"building"}, "deployed",
                       commit_sha=commit_sha, error=None)


def fail(job_id: str, error: str) -> dict | None:
    return _transition(
        job_id, ACTIVE_STATES - {"undone"}, "failed", error=str(error)[:500])


def request_undo(job_id: str) -> dict | None:
    return _transition(job_id, {"deployed"}, "undo_requested")


def start_undo(job_id: str) -> dict | None:
    return _transition(job_id, {"undo_requested"}, "undoing")


def complete_undo(job_id: str, revert_sha: str) -> dict | None:
    return _transition(job_id, {"undoing"}, "undone",
                       revert_sha=revert_sha, error=None)
