"""Enforces TikTok's per-minute request cap and the shared daily post cap.
Backed by SQLite so limits survive restarts. The daily cap is deliberately
hard-clamped to `absolute_daily_ceiling` in config.py regardless of user
config, since TikTok's ~15-25/day cap is shared across all apps and manual
posts on the account, not just this service.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from autopost.config import TikTokConfig
from autopost.db.repo import Database


class RateLimiter:
    def __init__(self, db: Database, cfg: TikTokConfig):
        self.db = db
        self.cfg = cfg

    def can_call_api_now(self) -> bool:
        one_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        return self.db.count_calls_since(one_min_ago) < self.cfg.requests_per_minute_limit

    def record_api_call(self, endpoint: str) -> None:
        self.db.record_rate_limit_event(endpoint)

    def can_post_today(self) -> bool:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        daily_max = min(self.cfg.max_posts_per_day, self.cfg.absolute_daily_ceiling)
        return self.db.count_posts_since(since) < daily_max
