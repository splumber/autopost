"""Ties together TTS + stock footage + ffmpeg into one finished vertical video."""
from __future__ import annotations

import logging
import random
import uuid
from pathlib import Path

from autopost.assets import music as music_lib
from autopost.assets import stock
from autopost.config import Settings
from autopost.tts import edge_tts_provider as tts
from autopost.video import captions, render

logger = logging.getLogger(__name__)


def build_beats(hook_line: str, scenes: list[dict], cta_line: str) -> list[dict]:
    """Flatten hook + scenes + cta into a uniform beat list with text + a
    visual search keyword each."""
    beats = [{"text": hook_line, "keyword": (scenes[0]["keyword"] if scenes else "abstract motion background")}]
    beats.extend({"text": s["text"], "keyword": s["keyword"]} for s in scenes)
    beats.append({"text": cta_line, "keyword": (scenes[-1]["keyword"] if scenes else "warm sunset glow")})
    return [b for b in beats if b["text"].strip()]


async def assemble_video(settings: Settings, beats: list[dict], work_dir: str, item_id: int) -> dict:
    """Runs the full render pipeline for one content item. Returns dict with
    video_path, duration_sec, caption_text (full narration text for reference)."""
    work = Path(work_dir) / f"item_{item_id}_{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True, exist_ok=True)

    # 1. TTS per beat (also gives us per-beat duration for clip sizing).
    narrations = []
    for i, beat in enumerate(beats):
        audio_path = str(work / f"beat_{i}.mp3")
        result = await tts.synthesize(settings.tts, beat["text"], audio_path)
        narrations.append(result)

    # 2. Stock clip per beat, avoiding recently-used assets.
    avoid_paths: set[str] = set()
    cache_dir = str(Path(settings.storage.cache_dir) / "stock")
    fetched = await stock.fetch_clips_for_scenes(
        settings.stock, [b["keyword"] for b in beats], cache_dir, avoid_paths
    )
    keyword_to_clip = {kw: path for kw, _provider, path in fetched}

    # 3. Build a same-length video segment per beat (loop/trim/scale/crop).
    segment_paths = []
    for i, (beat, narration) in enumerate(zip(beats, narrations)):
        clip_path = keyword_to_clip.get(beat["keyword"])
        seg_path = str(work / f"seg_{i}.mp4")
        if not clip_path:
            logger.warning("No stock clip for beat %s (%r); using solid color fallback", i, beat["keyword"])
            clip_path = _solid_color_fallback(work, i)
        render.build_segment(clip_path, max(narration.duration_sec, 0.5), settings.video, seg_path)
        segment_paths.append(seg_path)

    # 4. Concat video segments and audio beats separately.
    raw_video_path = str(work / "raw_video.mp4")
    render.concat_segments(segment_paths, raw_video_path, str(work))

    narration_track_path = str(work / "narration.m4a" if False else work / "narration_concat.mp3")
    render.concat_audio([n.audio_path for n in narrations], narration_track_path, str(work))

    # 5. Captions: shift each beat's word timings by its cumulative start offset.
    offset = 0.0
    beat_caption_data = []
    for narration in narrations:
        beat_caption_data.append({"word_timings": narration.word_timings, "offset_sec": offset})
        offset += narration.duration_sec
    total_duration = offset
    srt_content = captions.build_srt(beat_caption_data)
    srt_path = str(work / "captions.srt")
    Path(srt_path).write_text(srt_content, encoding="utf-8")

    # 6. Burn captions onto the (silent) concatenated video.
    captioned_video_path = str(work / "captioned.mp4")
    render.burn_captions(raw_video_path, srt_path, settings.video, captioned_video_path)

    # 7. Mix narration + background music.
    music_path = music_lib.pick_random_track()
    mixed_audio_path = str(work / "mixed_audio.m4a")
    render.mix_audio(narration_track_path, music_path, settings.video, total_duration, mixed_audio_path)

    # 8. Final mux.
    final_path = str(Path(settings.storage.video_output_dir) / f"item_{item_id}.mp4")
    render.mux_final(captioned_video_path, mixed_audio_path, final_path)

    return {"video_path": final_path, "duration_sec": total_duration}


def _solid_color_fallback(work_dir: Path, index: int) -> str:
    """When no stock clip could be fetched for a beat (e.g. no API keys
    configured yet), fall back to a generated color/gradient clip so the
    pipeline still produces a complete video rather than failing outright."""
    out_path = str(work_dir / f"fallback_{index}.mp4")
    color = random.choice(["0x1a1a2e", "0x16213e", "0x0f3460", "0x274156", "0x2c3e50"])
    render._run(
        [
            "-f", "lavfi",
            "-i", f"color=c={color}:s=1080x1920:d=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            out_path,
        ]
    )
    return out_path
