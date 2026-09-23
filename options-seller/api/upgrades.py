"""Upgrade builder queue: the iOS app's "Build this upgrade" button files a
request here, a Muse worker picks it up, implements the change (backend +
iOS), pushes, rebuilds on Varun's Mac, and installs on his iPhone. After a
deploy, the app offers an Undo button that reverts the upgrade commit(s) and
reinstalls the previous build.

State lives in data/upgrades.json with atomic writes. Render's free tier has
no persistent disk, so the queue is best-effort across restarts — the worker
treats a missing/empty queue as "nothing to do".

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
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("pulse.upgrades")

ACTIVE_STATES = {"pending", "building", "deployed", "undo_requested", "undoing"}
TERMINAL_STATES = {"failed", "undone"}


def _path() -> Path:
    from options_seller.paths import data_dir
    return data_dir() / "upgrades.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> list[dict]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(jobs: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs, indent=1), encoding="utf-8")
    tmp.replace(p)


def _touch(job: dict) -> None:
    job["updated_at"] = _now()


def latest_job() -> dict | None:
    """The most recent job of any status (what the app shows)."""
    jobs = _load()
    return jobs[-1] if jobs else None


def pending_jobs() -> list[dict]:
    return [j for j in _load() if j.get("status") == "pending"]


def undo_requested_jobs() -> list[dict]:
    return [j for j in _load() if j.get("status") == "undo_requested"]


def _find(jobs: list[dict], job_id: str) -> dict | None:
    return next((j for j in jobs if j.get("id") == job_id), None)


def create_job(idea: dict) -> dict:
    """File a new upgrade request. Refuses when another job is active."""
    jobs = _load()
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
    _save(jobs)
    return job


def _transition(job_id: str, from_states: set[str], to_state: str,
                **fields) -> dict | None:
    jobs = _load()
    job = _find(jobs, job_id)
    if job is None or job.get("status") not in from_states:
        return None
    job["status"] = to_state
    for k, v in fields.items():
        job[k] = v
    _touch(job)
    _save(jobs)
    return job


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
