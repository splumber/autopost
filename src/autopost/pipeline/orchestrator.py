"""Content pipeline: idea -> script -> policy check -> metadata -> render.
Each function processes at most one unit of work per call; the scheduler
calls these periodically so failures in one item never block the others.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from autopost.config import Settings
from autopost.db.repo import Database
from autopost.llm import generation
from autopost.llm.client import LLMClient
from autopost.video import assemble

logger = logging.getLogger(__name__)

IDEATION_BATCH_SIZE = 5
RECENT_TITLES_LOOKBACK = 30


async def run_ideation_cycle(db: Database, settings: Settings, llm: LLMClient) -> int:
    """Top up the proposed-topics backlog if it's empty. Returns count inserted."""
    if db.next_proposed_topic() is not None:
        return 0
    recent = [
        row["title"]
        for row in db.conn.execute(
            "SELECT title FROM topics ORDER BY created_at DESC LIMIT ?",
            (RECENT_TITLES_LOOKBACK,),
        ).fetchall()
    ]
    titles = await generation.generate_topics(llm, settings.niche, recent, n=IDEATION_BATCH_SIZE)
    inserted = 0
    for title in titles:
        dedupe_hash = generation.topic_dedupe_hash(title)
        if not db.topic_exists(dedupe_hash):
            db.insert_topic(settings.niche.active_niche, title, dedupe_hash)
            inserted += 1
    logger.info("Ideation cycle: proposed %s new topic(s)", inserted)
    return inserted


async def run_scripting_cycle(db: Database, settings: Settings, llm: LLMClient) -> int | None:
    """Take the oldest proposed topic through script -> policy check -> metadata.
    Returns the new content_item id, or None if there was nothing to do or the
    topic failed compliance twice in a row."""
    topic = db.next_proposed_topic()
    if topic is None:
        return None

    script, text, passed, notes = await _write_and_check(db, settings, llm, topic["title"])
    if not passed:
        # one revision attempt before giving up on this topic
        script, text, passed, notes = await _write_and_check(db, settings, llm, topic["title"])

    scene_text = " ".join(s.get("text", "") for s in script["scenes"])
    script_id = db.insert_script(
        topic_id=topic["id"],
        hook_line=script["hook_line"],
        body=scene_text,
        cta_line=script["cta_line"],
        scene_breakdown=script["scenes"],
        estimated_duration_sec=script["estimated_duration_sec"],
    )
    db.set_script_policy_result(script_id, "pass" if passed else "fail", notes)

    if not passed:
        db.set_topic_status(topic["id"], "rejected")
        logger.warning("Topic %r rejected by policy check twice: %s", topic["title"], notes)
        return None

    db.set_topic_status(topic["id"], "used")
    meta = await generation.generate_metadata(llm, settings.niche, topic["title"], text)
    status = "pending_review" if settings.scheduler.human_approval_required else "approved"
    item_id = db.insert_content_item(script_id, status=status)
    db.update_content_item(
        item_id,
        caption_text=meta["caption_text"],
        hashtags=json.dumps(meta["hashtags"]),
    )
    logger.info("Scripting cycle: content_item %s created (status=%s)", item_id, status)
    return item_id


async def _write_and_check(db: Database, settings: Settings, llm: LLMClient, topic_title: str):
    script = await generation.generate_script(llm, settings.niche, settings.video, topic_title)
    text = generation.full_script_text(script["hook_line"], script["scenes"], script["cta_line"])
    passed, notes = await generation.policy_check(llm, settings.niche, text)
    return script, text, passed, notes


async def run_render_cycle(db: Database, settings: Settings) -> int | None:
    """Render the oldest 'approved' content_item into a finished video."""
    rows = db.list_content_items(status="approved", limit=1)
    if not rows:
        return None
    item = rows[0]
    db.update_content_item(item["id"], status="rendering")
    script = db.get_script(item["script_id"])
    scenes = json.loads(script["scene_breakdown_json"])
    beats = assemble.build_beats(script["hook_line"], scenes, script["cta_line"])
    work_dir = str(Path(settings.storage.cache_dir) / "render_work")
    try:
        result = await assemble.assemble_video(settings, beats, work_dir, item_id=item["id"])
    except Exception as exc:  # noqa: BLE001 -- rendering has many failure modes (ffmpeg, network, disk)
        logger.exception("Render failed for content_item %s", item["id"])
        db.update_content_item(
            item["id"], status="failed", error_message=str(exc)[:2000],
            retry_count=item["retry_count"] + 1,
        )
        return None
    db.update_content_item(
        item["id"],
        status="ready_to_post",
        video_path=result["video_path"],
        duration_sec=result["duration_sec"],
    )
    logger.info("Render cycle: content_item %s ready (%.1fs)", item["id"], result["duration_sec"])
    return item["id"]
