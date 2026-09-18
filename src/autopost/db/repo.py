"""Thin synchronous SQLite access layer. The whole service runs as a single
process/single OS thread (scheduler loop + FastAPI share one asyncio loop), so a
single shared connection with WAL mode is enough -- no connection pool needed.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        with closing(SCHEMA_PATH.open("r", encoding="utf-8")) as f:
            self.conn.executescript(f.read())
        self.conn.commit()

    # ---- accounts ----
    def get_account(self) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM accounts WHERE id = 1").fetchone()

    def upsert_account(self, **fields: Any) -> None:
        fields["updated_at"] = now_iso()
        cols = ", ".join(fields.keys())
        placeholders = ", ".join(f":{k}" for k in fields)
        updates = ", ".join(f"{k} = excluded.{k}" for k in fields)
        self.conn.execute(
            f"INSERT INTO accounts (id, {cols}) VALUES (1, {placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            fields,
        )
        self.conn.commit()

    # ---- oauth_states ----
    def save_oauth_state(self, state: str, code_verifier: str) -> None:
        self.conn.execute(
            "INSERT INTO oauth_states (state, code_verifier, created_at) VALUES (?, ?, ?)",
            (state, code_verifier, now_iso()),
        )
        self.conn.commit()

    def consume_oauth_state(self, state: str) -> str | None:
        row = self.conn.execute(
            "SELECT code_verifier FROM oauth_states WHERE state = ? AND consumed_at IS NULL",
            (state,),
        ).fetchone()
        if not row:
            return None
        self.conn.execute(
            "UPDATE oauth_states SET consumed_at = ? WHERE state = ?", (now_iso(), state)
        )
        self.conn.commit()
        return row["code_verifier"]

    # ---- topics ----
    def topic_exists(self, dedupe_hash: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM topics WHERE dedupe_hash = ?", (dedupe_hash,)
            ).fetchone()
            is not None
        )

    def insert_topic(self, niche: str, title: str, dedupe_hash: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO topics (niche, title, dedupe_hash, created_at) VALUES (?, ?, ?, ?)",
            (niche, title, dedupe_hash, now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid

    def next_proposed_topic(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM topics WHERE status = 'proposed' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()

    def set_topic_status(self, topic_id: int, status: str) -> None:
        self.conn.execute("UPDATE topics SET status = ? WHERE id = ?", (status, topic_id))
        self.conn.commit()

    # ---- scripts ----
    def insert_script(
        self,
        topic_id: int,
        hook_line: str,
        body: str,
        cta_line: str,
        scene_breakdown: list[dict],
        estimated_duration_sec: float,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO scripts (topic_id, hook_line, body, cta_line, scene_breakdown_json, "
            "estimated_duration_sec, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                topic_id,
                hook_line,
                body,
                cta_line,
                json.dumps(scene_breakdown),
                estimated_duration_sec,
                now_iso(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def set_script_policy_result(self, script_id: int, status: str, notes: str) -> None:
        self.conn.execute(
            "UPDATE scripts SET policy_check_status = ?, policy_check_notes = ? WHERE id = ?",
            (status, notes, script_id),
        )
        self.conn.commit()

    def get_script(self, script_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()

    # ---- content_items ----
    def insert_content_item(self, script_id: int, status: str = "draft") -> int:
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT INTO content_items (script_id, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (script_id, status, ts, ts),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_content_item(self, item_id: int, **fields: Any) -> None:
        fields["updated_at"] = now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE content_items SET {set_clause} WHERE id = ?",
            (*fields.values(), item_id),
        )
        self.conn.commit()

    def get_content_item(self, item_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM content_items WHERE id = ?", (item_id,)
        ).fetchone()

    def list_content_items(self, status: str | None = None, limit: int = 50) -> list[sqlite3.Row]:
        if status:
            return self.conn.execute(
                "SELECT * FROM content_items WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM content_items ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def due_scheduled_items(self, before_iso: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM content_items WHERE status = 'scheduled' AND scheduled_for <= ? "
            "ORDER BY scheduled_for ASC",
            (before_iso,),
        ).fetchall()

    def count_posts_since(self, since_iso: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM posting_history WHERE posted_at >= ?", (since_iso,)
        ).fetchone()
        return row["c"]

    def last_scheduled_time(self) -> str | None:
        row = self.conn.execute(
            "SELECT MAX(scheduled_for) AS t FROM content_items "
            "WHERE status IN ('scheduled', 'posted')"
        ).fetchone()
        return row["t"]

    # ---- content_assets ----
    def insert_content_asset(
        self, content_item_id: int, asset_type: str, provider: str, local_path: str,
        query_keyword: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO content_assets (content_item_id, asset_type, provider, local_path, "
            "query_keyword, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (content_item_id, asset_type, provider, local_path, query_keyword, now_iso()),
        )
        self.conn.commit()

    def recently_used_asset_paths(self, days: int = 14) -> set[str]:
        rows = self.conn.execute(
            "SELECT local_path FROM content_assets WHERE created_at >= datetime('now', ?)",
            (f"-{days} days",),
        ).fetchall()
        return {r["local_path"] for r in rows}

    # ---- posting_history ----
    def insert_posting_history(
        self, content_item_id: int, tiktok_video_id: str | None, publish_id: str | None,
        privacy_level: str, api_response: dict,
    ) -> None:
        self.conn.execute(
            "INSERT INTO posting_history (content_item_id, tiktok_video_id, publish_id, "
            "posted_at, privacy_level, api_response_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                content_item_id, tiktok_video_id, publish_id, now_iso(), privacy_level,
                json.dumps(api_response),
            ),
        )
        self.conn.commit()

    # ---- analytics ----
    def insert_analytics_snapshot(
        self, content_item_id: int, tiktok_video_id: str, views: int, likes: int,
        comments: int, shares: int, raw: dict,
    ) -> None:
        self.conn.execute(
            "INSERT INTO analytics_snapshots (content_item_id, tiktok_video_id, views, likes, "
            "comments, shares, raw_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (content_item_id, tiktok_video_id, views, likes, comments, shares,
             json.dumps(raw), now_iso()),
        )
        self.conn.commit()

    def posted_items_with_video_id(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM content_items WHERE status = 'posted' AND tiktok_video_id IS NOT NULL"
        ).fetchall()

    def trailing_30d_views(self) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(views), 0) AS total FROM ("
            "  SELECT content_item_id, MAX(views) AS views FROM analytics_snapshots "
            "  WHERE fetched_at >= datetime('now', '-30 days') GROUP BY content_item_id"
            ")"
        ).fetchone()
        return row["total"]

    def insert_rewards_progress(self, **fields: Any) -> None:
        fields["snapshot_date"] = now_iso()
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self.conn.execute(
            f"INSERT INTO rewards_progress ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
        self.conn.commit()

    def latest_rewards_progress(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM rewards_progress ORDER BY snapshot_date DESC LIMIT 1"
        ).fetchone()

    # ---- rate limiting ----
    def record_rate_limit_event(self, endpoint: str) -> None:
        self.conn.execute(
            "INSERT INTO rate_limit_events (endpoint, called_at) VALUES (?, ?)",
            (endpoint, now_iso()),
        )
        self.conn.commit()

    def count_calls_since(self, since_iso: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM rate_limit_events WHERE called_at >= ?", (since_iso,)
        ).fetchone()
        return row["c"]

    # ---- job_runs ----
    def start_job_run(self, job_name: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO job_runs (job_name, started_at) VALUES (?, ?)",
            (job_name, now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_job_run(self, run_id: int, status: str, detail: str = "") -> None:
        self.conn.execute(
            "UPDATE job_runs SET finished_at = ?, status = ?, detail = ? WHERE id = ?",
            (now_iso(), status, detail, run_id),
        )
        self.conn.commit()

    def recent_job_runs(self, limit: int = 30) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM job_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
