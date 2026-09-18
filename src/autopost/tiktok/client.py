"""TikTok Content Posting API (Direct Post) client, plus minimal analytics
polling. Every publish call passes through the caller-supplied effective
privacy_level (see config.TikTokConfig.effective_privacy_level, which
force-clamps to SELF_ONLY until audit_status == "approved") and the AIGC
disclosure flag, and every call is gated by the shared RateLimiter.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx

from autopost.config import TikTokConfig
from autopost.db.repo import Database
from autopost.tiktok import models, oauth
from autopost.tiktok.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5
POLL_MAX_ATTEMPTS = 24  # ~2 minutes


async def publish_video(
    cfg: TikTokConfig,
    db: Database,
    secret_key: str,
    limiter: RateLimiter,
    video_path: str,
    caption_text: str,
    hashtags: list[str],
) -> models.PublishResult:
    if not limiter.can_post_today():
        raise RuntimeError("Daily posting cap reached -- will retry on the next cadence pass")
    if not limiter.can_call_api_now():
        raise RuntimeError("Per-minute API rate limit reached -- will retry shortly")

    access_token = await oauth.get_valid_access_token(cfg, db, secret_key)
    video_size = Path(video_path).stat().st_size
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    effective_privacy = cfg.effective_privacy_level
    post_info = models.build_post_info(
        caption_text, hashtags, effective_privacy, cfg.disable_duet, cfg.disable_stitch, cfg.disable_comment
    )
    init_body = {
        "post_info": post_info,
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        },
    }

    async with httpx.AsyncClient(base_url=cfg.api_base_url, timeout=60) as client:
        limiter.record_api_call("post/publish/video/init")
        init_resp = await client.post("/v2/post/publish/video/init/", headers=headers, json=init_body)
        init_resp.raise_for_status()
        init_data = init_resp.json()
        if init_data.get("error", {}).get("code") not in (None, "ok"):
            raise RuntimeError(f"TikTok init error: {init_data['error']}")
        publish_id = init_data["data"]["publish_id"]
        upload_url = init_data["data"]["upload_url"]

        with open(video_path, "rb") as f:
            video_bytes = f.read()
        upload_resp = await client.put(
            upload_url,
            content=video_bytes,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
            },
        )
        upload_resp.raise_for_status()

        status, tiktok_video_id, raw = await _poll_publish_status(client, headers, publish_id, limiter)

    logger.info(
        "Published content to TikTok: publish_id=%s status=%s privacy=%s",
        publish_id, status, effective_privacy,
    )
    return models.PublishResult(
        publish_id=publish_id, status=status, tiktok_video_id=tiktok_video_id, raw_response=raw
    )


async def _poll_publish_status(
    client: httpx.AsyncClient, headers: dict, publish_id: str, limiter: RateLimiter
) -> tuple[str, str | None, dict]:
    for _ in range(POLL_MAX_ATTEMPTS):
        limiter.record_api_call("post/publish/status/fetch")
        resp = await client.post(
            "/v2/post/publish/status/fetch/", headers=headers, json={"publish_id": publish_id}
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("data", {}).get("status")
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            video_id = data.get("data", {}).get("publicly_available_post_id")
            video_id = video_id[0] if isinstance(video_id, list) and video_id else video_id
            return status, video_id, data
        await asyncio.sleep(POLL_INTERVAL_SEC)
    return "TIMEOUT", None, {}


async def fetch_account_metrics(cfg: TikTokConfig, db: Database, secret_key: str) -> dict:
    access_token = await oauth.get_valid_access_token(cfg, db, secret_key)
    async with httpx.AsyncClient(base_url=cfg.api_base_url, timeout=30) as client:
        resp = await client.get(
            "/v2/user/info/",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "open_id,display_name,follower_count,likes_count,video_count"},
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("user", {})


async def fetch_video_metrics(
    cfg: TikTokConfig, db: Database, secret_key: str, tiktok_video_ids: list[str]
) -> list[dict]:
    if not tiktok_video_ids:
        return []
    access_token = await oauth.get_valid_access_token(cfg, db, secret_key)
    async with httpx.AsyncClient(base_url=cfg.api_base_url, timeout=30) as client:
        resp = await client.post(
            "/v2/video/query/",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "id,view_count,like_count,comment_count,share_count"},
            json={"filters": {"video_ids": tiktok_video_ids}},
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("videos", [])
