"""Free, keyless TTS narration via edge-tts, with word-level timing for captions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import edge_tts

from autopost.config import TTSConfig


@dataclass
class WordTiming:
    text: str
    start_sec: float
    end_sec: float


@dataclass
class NarrationResult:
    audio_path: str
    duration_sec: float
    word_timings: list[WordTiming]


async def synthesize(cfg: TTSConfig, text: str, out_path: str) -> NarrationResult:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(
        text, voice=cfg.voice, rate=cfg.rate, pitch=cfg.pitch, boundary="WordBoundary"
    )
    word_timings: list[WordTiming] = []
    max_end = 0.0
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000  # 100-ns units -> seconds
                end = start + chunk["duration"] / 10_000_000
                word_timings.append(WordTiming(text=chunk["text"], start_sec=start, end_sec=end))
                max_end = max(max_end, end)
    return NarrationResult(audio_path=out_path, duration_sec=max_end, word_timings=word_timings)


def group_into_captions(word_timings: list[WordTiming], max_words: int = 4) -> list[dict]:
    """Group words into short caption chunks (for burned-in subtitles)."""
    captions = []
    for i in range(0, len(word_timings), max_words):
        group = word_timings[i : i + max_words]
        if not group:
            continue
        captions.append(
            {
                "text": " ".join(w.text for w in group),
                "start_sec": group[0].start_sec,
                "end_sec": group[-1].end_sec,
            }
        )
    return captions
