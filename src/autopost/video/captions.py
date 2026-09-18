from __future__ import annotations

from autopost.tts.edge_tts_provider import WordTiming, group_into_captions


def _srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(beats: list[dict]) -> str:
    """beats: [{"word_timings": [WordTiming...], "offset_sec": float}, ...]
    word_timings are relative to the start of that beat's own audio clip;
    offset_sec shifts them into the final concatenated timeline."""
    lines: list[str] = []
    index = 1
    for beat in beats:
        timings: list[WordTiming] = beat["word_timings"]
        offset = beat["offset_sec"]
        shifted = [
            WordTiming(text=w.text, start_sec=w.start_sec + offset, end_sec=w.end_sec + offset)
            for w in timings
        ]
        for cap in group_into_captions(shifted, max_words=4):
            lines.append(str(index))
            lines.append(f"{_srt_timestamp(cap['start_sec'])} --> {_srt_timestamp(cap['end_sec'])}")
            lines.append(cap["text"])
            lines.append("")
            index += 1
    return "\n".join(lines)
