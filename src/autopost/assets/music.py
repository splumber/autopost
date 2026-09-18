"""Background music picker. Ships with no audio files (avoids bundling anything
with unclear licensing) -- drop your own royalty-free/licensed mp3s into
assets_bundled/music/ and they'll be picked up automatically. With none present,
videos render narration-only, which still works fine."""
from __future__ import annotations

import random
from pathlib import Path

MUSIC_DIR = Path(__file__).resolve().parents[3] / "assets_bundled" / "music"


def pick_random_track() -> str | None:
    if not MUSIC_DIR.exists():
        return None
    tracks = [str(p) for p in MUSIC_DIR.glob("*.mp3")]
    return random.choice(tracks) if tracks else None
