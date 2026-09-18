from __future__ import annotations

import hashlib
import re

from autopost.config import NicheConfig, VideoConfig
from autopost.llm import prompts
from autopost.llm.client import LLMClient

WORDS_PER_SECOND = 2.5


def topic_dedupe_hash(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


async def generate_topics(
    llm: LLMClient, niche: NicheConfig, existing_titles: list[str], n: int = 5
) -> list[str]:
    niche_desc = prompts.NICHE_DESCRIPTIONS[niche.active_niche]
    data = await llm.chat_json(
        prompts.TOPIC_SYSTEM.format(niche_desc=niche_desc),
        prompts.TOPIC_USER.format(
            n=n, existing_titles="\n".join(f"- {t}" for t in existing_titles) or "(none yet)"
        ),
    )
    return [t.strip() for t in data.get("topics", []) if t and t.strip()]


async def generate_script(
    llm: LLMClient, niche: NicheConfig, video: VideoConfig, topic_title: str
) -> dict:
    niche_desc = prompts.NICHE_DESCRIPTIONS[niche.active_niche]
    min_words = int(video.target_duration_min_sec * WORDS_PER_SECOND)
    max_words = int(video.target_duration_max_sec * WORDS_PER_SECOND)
    data = await llm.chat_json(
        prompts.SCRIPT_SYSTEM.format(
            niche_desc=niche_desc,
            min_sec=video.target_duration_min_sec,
            max_sec=video.target_duration_max_sec,
            min_words=min_words,
            max_words=max_words,
        ),
        prompts.SCRIPT_USER.format(topic_title=topic_title),
    )
    scenes = data.get("scenes", [])
    full_text = " ".join(s.get("text", "") for s in scenes)
    word_count = len(full_text.split()) + len(data.get("hook_line", "").split())
    estimated_duration_sec = word_count / WORDS_PER_SECOND
    return {
        "hook_line": data.get("hook_line", "").strip(),
        "scenes": scenes,
        "cta_line": data.get("cta_line", "").strip(),
        "estimated_duration_sec": estimated_duration_sec,
    }


async def policy_check(llm: LLMClient, niche: NicheConfig, script_text: str) -> tuple[bool, str]:
    niche_desc = prompts.NICHE_DESCRIPTIONS[niche.active_niche]
    data = await llm.chat_json(
        prompts.POLICY_SYSTEM.format(niche_desc=niche_desc),
        prompts.POLICY_USER.format(script_text=script_text),
    )
    return bool(data.get("pass", False)), str(data.get("notes", ""))


async def generate_metadata(
    llm: LLMClient, niche: NicheConfig, topic_title: str, script_text: str
) -> dict:
    niche_desc = prompts.NICHE_DESCRIPTIONS[niche.active_niche]
    data = await llm.chat_json(
        prompts.METADATA_SYSTEM.format(niche_desc=niche_desc),
        prompts.METADATA_USER.format(topic_title=topic_title, script_text=script_text),
    )
    hashtags = data.get("hashtags", [])
    hashtags = [h if h.startswith("#") else f"#{h}" for h in hashtags]
    return {"caption_text": data.get("caption_text", "").strip(), "hashtags": hashtags}


def full_script_text(hook_line: str, scenes: list[dict], cta_line: str) -> str:
    body = " ".join(s.get("text", "") for s in scenes)
    return f"{hook_line} {body} {cta_line}".strip()
