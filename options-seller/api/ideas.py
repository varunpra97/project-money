"""Liked Product-lab ideas.

Tapping "I like it" on a deployed upgrade removes that suggestion from the
Product lab queue; the queue then refills from the backlog so a fresh idea
appears at the bottom. Persisted in Postgres when DATABASE_URL is set
(survives Render restarts), JSON file fallback otherwise.
"""
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("pulse.ideas")

_JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "liked_ideas.json"


def _db_configured() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def _pg():
    import psycopg2
    return psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10,
                            options="-c statement_timeout=15000")


def _db_init(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS liked_ideas (
                   idea_id TEXT PRIMARY KEY,
                   liked_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
        )
    conn.commit()


def _json_load() -> list:
    try:
        return json.loads(_JSON_PATH.read_text())
    except (OSError, ValueError):
        return []


def _json_save(ids: list) -> None:
    _JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _JSON_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(ids))
    tmp.replace(_JSON_PATH)


def liked_ids() -> set:
    """Idea ids the user has liked (accepted) — excluded from the queue."""
    if _db_configured():
        try:
            with _pg() as conn:
                _db_init(conn)
                with conn.cursor() as cur:
                    cur.execute("SELECT idea_id FROM liked_ideas")
                    return {row[0] for row in cur.fetchall()}
        except Exception as e:
            log.warning("liked ideas: db failed, json fallback: %s", e)
    return set(_json_load())


def like_idea(idea_id: str) -> None:
    idea_id = str(idea_id or "").strip()
    if not idea_id:
        raise ValueError("missing idea_id")
    if _db_configured():
        try:
            with _pg() as conn:
                _db_init(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO liked_ideas (idea_id) VALUES (%s)"
                        " ON CONFLICT DO NOTHING",
                        (idea_id,),
                    )
                conn.commit()
            return
        except Exception as e:
            log.warning("liked ideas: db failed, json fallback: %s", e)
    ids = _json_load()
    if idea_id not in ids:
        ids.append(idea_id)
        _json_save(ids)
