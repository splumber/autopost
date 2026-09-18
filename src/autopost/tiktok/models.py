"""Request/response shapes for TikTok's Content Posting API (Direct Post).
Isolated here so a field-name change on TikTok's side (this API has evolved
before, e.g. the AIGC disclosure flag) is a one-file fix.

NOTE: `AIGC_DISCLOSURE_FIELD` below reflects the field name at the time this
was written. Re-verify against the current Content Posting API reference
(https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post)
before going live with the audited/public app, since disclosure requirements
are a newer, actively evolving part of the API.
"""
from __future__ import annotations

from dataclasses import dataclass

PRIVACY_SELF_ONLY = "SELF_ONLY"
PRIVACY_PUBLIC = "PUBLIC_TO_EVERYONE"

AIGC_DISCLOSURE_FIELD = "is_aigc"  # verify against current docs before audit submission


@dataclass
class PublishResult:
    publish_id: str
    status: str
    tiktok_video_id: str | None
    raw_response: dict


def build_post_info(
    caption_text: str,
    hashtags: list[str],
    privacy_level: str,
    disable_duet: bool,
    disable_stitch: bool,
    disable_comment: bool,
) -> dict:
    title = caption_text.strip()
    if hashtags:
        title = f"{title} " + " ".join(hashtags)
    return {
        "title": title[:2200],  # TikTok caption length limit
        "privacy_level": privacy_level,
        "disable_duet": disable_duet,
        "disable_stitch": disable_stitch,
        "disable_comment": disable_comment,
        AIGC_DISCLOSURE_FIELD: True,  # always true -- this pipeline uses TTS + AI-sourced visuals
    }
