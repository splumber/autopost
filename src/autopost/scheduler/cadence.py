"""Assigns `scheduled_for` timestamps to ready-to-post content, spacing posts
by `min_hours_between_posts` and keeping them inside the configured posting
window. The daily post cap itself is enforced again at publish time by
RateLimiter (defense in depth against clock drift / manual overrides)."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from autopost.config import TikTokConfig
from autopost.db.repo import Database


def next_available_slot(db: Database, cfg: TikTokConfig) -> datetime:
    tz = ZoneInfo(cfg.timezone)
    now = datetime.now(tz)
    last = db.last_scheduled_time()
    earliest = now
    if last:
        last_dt = datetime.fromisoformat(last).astimezone(tz)
        earliest = max(earliest, last_dt + timedelta(hours=cfg.min_hours_between_posts))

    candidate = earliest
    window_start = cfg.posting_window_start_hour
    window_end = cfg.posting_window_end_hour
    if candidate.hour < window_start:
        candidate = candidate.replace(hour=window_start, minute=0, second=0, microsecond=0)
    elif candidate.hour >= window_end:
        candidate = (candidate + timedelta(days=1)).replace(
            hour=window_start, minute=0, second=0, microsecond=0
        )
    return candidate


def schedule_ready_items(db: Database, cfg: TikTokConfig) -> int:
    # list_content_items returns newest-first; reverse so older content is
    # scheduled (and therefore posted) before newer content -- FIFO.
    rows = list(reversed(db.list_content_items(status="ready_to_post", limit=10)))
    count = 0
    for row in rows:
        slot = next_available_slot(db, cfg)
        db.update_content_item(row["id"], status="scheduled", scheduled_for=slot.isoformat())
        count += 1
    return count
