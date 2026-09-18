"""Fetch licensed, free-to-use vertical stock video clips matching a keyword.
Pexels and Pixabay both grant a broad free license for this kind of use
(no attribution required, commercial use allowed) -- see their license pages.
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from autopost.config import StockConfig

logger = logging.getLogger(__name__)

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"


async def _fetch_pexels(client: httpx.AsyncClient, cfg: StockConfig, keyword: str) -> str | None:
    if not cfg.pexels_api_key:
        return None
    resp = await client.get(
        PEXELS_SEARCH_URL,
        params={"query": keyword, "orientation": cfg.orientation, "per_page": cfg.max_results_per_query},
        headers={"Authorization": cfg.pexels_api_key},
        timeout=20,
    )
    if resp.status_code != 200:
        logger.warning("Pexels search failed for %r: %s", keyword, resp.status_code)
        return None
    videos = resp.json().get("videos", [])
    for video in videos:
        if video.get("duration", 0) < cfg.min_clip_duration_sec:
            continue
        files = sorted(
            (f for f in video.get("video_files", []) if f.get("width") and f.get("height")),
            key=lambda f: f["width"] * f["height"],
        )
        portrait_files = [f for f in files if f["height"] > f["width"]]
        chosen = (portrait_files or files)
        if chosen:
            return chosen[-1]["link"]
    return None


async def _fetch_pixabay(client: httpx.AsyncClient, cfg: StockConfig, keyword: str) -> str | None:
    if not cfg.pixabay_api_key:
        return None
    resp = await client.get(
        PIXABAY_SEARCH_URL,
        params={"key": cfg.pixabay_api_key, "q": keyword, "per_page": cfg.max_results_per_query},
        timeout=20,
    )
    if resp.status_code != 200:
        logger.warning("Pixabay search failed for %r: %s", keyword, resp.status_code)
        return None
    hits = resp.json().get("hits", [])
    for hit in hits:
        videos = hit.get("videos", {})
        for quality in ("large", "medium", "small"):
            if quality in videos:
                return videos[quality]["url"]
    return None


async def fetch_clip_for_keyword(
    cfg: StockConfig, keyword: str, dest_dir: str, avoid_paths: set[str]
) -> tuple[str, str] | None:
    """Returns (provider, local_path) or None if nothing found across all providers."""
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    fetchers = {"pexels": _fetch_pexels, "pixabay": _fetch_pixabay}
    async with httpx.AsyncClient() as client:
        for provider in cfg.provider_priority:
            fetcher = fetchers.get(provider)
            if not fetcher:
                continue
            try:
                url = await fetcher(client, cfg, keyword)
            except httpx.HTTPError as exc:
                logger.warning("%s fetch error for %r: %s", provider, keyword, exc)
                continue
            if not url:
                continue
            local_path = str(Path(dest_dir) / f"{provider}_{abs(hash((provider, url)))}.mp4")
            if local_path in avoid_paths and Path(local_path).exists():
                continue
            if not Path(local_path).exists():
                video_resp = await client.get(url, timeout=60, follow_redirects=True)
                video_resp.raise_for_status()
                Path(local_path).write_bytes(video_resp.content)
            return provider, local_path
    return None


async def fetch_clips_for_scenes(
    cfg: StockConfig, keywords: list[str], dest_dir: str, avoid_paths: set[str]
) -> list[tuple[str, str, str]]:
    """Returns list of (keyword, provider, local_path). Falls back to a broader
    generic keyword if a specific one returns nothing, so a scene never blocks
    the whole render."""
    results: list[tuple[str, str, str]] = []
    for keyword in keywords:
        found = await fetch_clip_for_keyword(cfg, keyword, dest_dir, avoid_paths)
        if not found:
            found = await fetch_clip_for_keyword(cfg, "abstract background", dest_dir, avoid_paths)
        if found:
            provider, path = found
            results.append((keyword, provider, path))
        else:
            logger.warning("No stock clip found for keyword %r (all providers/fallback failed)", keyword)
    return results
