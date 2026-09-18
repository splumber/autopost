"""Periodic analytics polling: pulls follower count + per-video metrics from
TikTok and recomputes progress toward Creator Rewards Program eligibility."""
from __future__ import annotations

import logging

from autopost.config import Settings
from autopost.db.repo import Database
from autopost.tiktok import client as tiktok_client

logger = logging.getLogger(__name__)

REWARDS_FOLLOWER_THRESHOLD = 10_000
REWARDS_VIEWS_THRESHOLD = 100_000
REWARDS_MIN_VIDEO_DURATION_SEC = 60


async def poll_and_record(db: Database, settings: Settings) -> None:
    account = db.get_account()
    if not account or not account["access_token_enc"]:
        logger.debug("Analytics poll skipped: TikTok account not linked yet")
        return

    secret_key = settings.secret_key
    posted = db.posted_items_with_video_id()
    video_ids = [row["tiktok_video_id"] for row in posted]
    metrics = await tiktok_client.fetch_video_metrics(settings.tiktok, db, secret_key, video_ids)
    metrics_by_id = {m["id"]: m for m in metrics}

    for row in posted:
        m = metrics_by_id.get(row["tiktok_video_id"])
        if not m:
            continue
        db.insert_analytics_snapshot(
            content_item_id=row["id"],
            tiktok_video_id=row["tiktok_video_id"],
            views=m.get("view_count", 0),
            likes=m.get("like_count", 0),
            comments=m.get("comment_count", 0),
            shares=m.get("share_count", 0),
            raw=m,
        )

    user_info = await tiktok_client.fetch_account_metrics(settings.tiktok, db, secret_key)
    followers = user_info.get("follower_count", 0)
    trailing_views = db.trailing_30d_views()
    eligible_video_count = sum(
        1 for row in posted if (row["duration_sec"] or 0) >= REWARDS_MIN_VIDEO_DURATION_SEC
    )
    is_eligible = followers >= REWARDS_FOLLOWER_THRESHOLD and trailing_views >= REWARDS_VIEWS_THRESHOLD

    db.insert_rewards_progress(
        followers=followers,
        trailing_30d_views=trailing_views,
        eligible_video_count=eligible_video_count,
        is_eligible=int(is_eligible),
        notes="",
    )
    logger.info(
        "Analytics: followers=%s trailing_30d_views=%s eligible=%s",
        followers, trailing_views, is_eligible,
    )
