"""Three independent async loops sharing one DB connection and one LLM client:
content pipeline (idea->script->render->schedule), publish checker, and
analytics poller. Each loop catches its own exceptions so a failure in one
(e.g. the LLM proxy being briefly unreachable) never takes down the others.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from autopost.config import Settings
from autopost.db.repo import Database
from autopost.llm.client import LLMClient
from autopost.pipeline import orchestrator
from autopost.scheduler import cadence
from autopost.tiktok import client as tiktok_client
from autopost.tiktok.rate_limiter import RateLimiter
from autopost.analytics import poller as analytics_poller

logger = logging.getLogger(__name__)

PUBLISH_CHECK_INTERVAL_SEC = 300


async def _guarded(db: Database, job_name: str, coro_fn):
    run_id = db.start_job_run(job_name)
    try:
        result = await coro_fn()
        db.finish_job_run(run_id, "ok", str(result) if result is not None else "")
    except Exception as exc:  # noqa: BLE001 -- top-level loop guard, must never crash the service
        logger.exception("Job %s failed", job_name)
        db.finish_job_run(run_id, "error", str(exc)[:2000])


async def content_pipeline_loop(db: Database, settings: Settings, llm: LLMClient) -> None:
    interval = settings.scheduler.pipeline_interval_minutes * 60
    while True:
        await _guarded(db, "ideation", lambda: orchestrator.run_ideation_cycle(db, settings, llm))
        await _guarded(db, "scripting", lambda: orchestrator.run_scripting_cycle(db, settings, llm))
        await _guarded(db, "render", lambda: orchestrator.run_render_cycle(db, settings))
        await _guarded(
            db, "cadence", lambda: asyncio.to_thread(cadence.schedule_ready_items, db, settings.tiktok)
        )
        await asyncio.sleep(interval)


async def publish_loop(db: Database, settings: Settings) -> None:
    limiter = RateLimiter(db, settings.tiktok)
    while True:
        await _guarded(db, "publish_check", lambda: _publish_due_items(db, settings, limiter))
        await asyncio.sleep(PUBLISH_CHECK_INTERVAL_SEC)


async def _publish_due_items(db: Database, settings: Settings, limiter: RateLimiter) -> int:
    account = db.get_account()
    if not account or not account["access_token_enc"]:
        return 0
    now_iso = datetime.now(timezone.utc).isoformat()
    due = db.due_scheduled_items(now_iso)
    published = 0
    for item in due:
        if not limiter.can_post_today():
            logger.info("Daily posting cap reached, deferring remaining scheduled items")
            break
        db.update_content_item(item["id"], status="publishing")
        try:
            hashtags = _load_hashtags(item["hashtags"])
            result = await tiktok_client.publish_video(
                settings.tiktok, db, settings.secret_key, limiter,
                item["video_path"], item["caption_text"] or "", hashtags,
            )
        except Exception as exc:  # noqa: BLE001 -- many transient causes (network, token, API)
            logger.exception("Publish failed for content_item %s", item["id"])
            db.update_content_item(
                item["id"], status="failed", error_message=str(exc)[:2000],
                retry_count=item["retry_count"] + 1,
            )
            continue
        db.update_content_item(
            item["id"], status="posted", posted_at=now_iso,
            tiktok_publish_id=result.publish_id, tiktok_video_id=result.tiktok_video_id,
        )
        db.insert_posting_history(
            item["id"], result.tiktok_video_id, result.publish_id,
            settings.tiktok.effective_privacy_level, result.raw_response,
        )
        published += 1
    return published


def _load_hashtags(raw: str | None) -> list[str]:
    import json

    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


async def analytics_loop(db: Database, settings: Settings) -> None:
    interval = settings.scheduler.analytics_poll_interval_minutes * 60
    while True:
        await _guarded(db, "analytics_poll", lambda: analytics_poller.poll_and_record(db, settings))
        await asyncio.sleep(interval)


async def run_all(db: Database, settings: Settings, llm: LLMClient) -> None:
    await asyncio.gather(
        content_pipeline_loop(db, settings, llm),
        publish_loop(db, settings),
        analytics_loop(db, settings),
    )
