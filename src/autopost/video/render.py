"""ffmpeg orchestration: per-beat clip -> concatenated background video ->
mixed audio (narration + ducked music) -> burned-in captions -> final mux.

Uses the static ffmpeg binary bundled by imageio-ffmpeg so no system ffmpeg
install is required (works the same on the host and inside the container).
"""
from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path

import imageio_ffmpeg

from autopost.config import VideoConfig

logger = logging.getLogger(__name__)


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str]) -> None:
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", *args]
    logger.debug("ffmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{result.stderr[-4000:]}")


def _escape_for_filter(path: str) -> str:
    """Escape a filesystem path for use inside an ffmpeg filtergraph argument
    (colons and backslashes need escaping, notably on Windows paths)."""
    p = path.replace("\\", "/")
    p = p.replace(":", r"\:")
    return p


def _escape_for_concat_list(path: str) -> str:
    """Escape a filesystem path for an ffmpeg concat-demuxer list file entry.
    Unlike filtergraph args, colons must NOT be escaped here -- only forward
    slashes are needed for Windows paths, plus doubling any literal quote."""
    p = path.replace("\\", "/")
    p = p.replace("'", "'\\''")
    return p


def build_segment(clip_path: str, duration_sec: float, video: VideoConfig, out_path: str) -> None:
    """Loop/trim a stock clip to exactly `duration_sec`, scale+crop to cover the
    target frame, strip audio, normalize fps."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={video.width}:{video.height}:force_original_aspect_ratio=increase,"
        f"crop={video.width}:{video.height},setsar=1,fps={video.fps}"
    )
    _run(
        [
            "-stream_loop", "-1",
            "-i", clip_path,
            "-t", f"{duration_sec:.3f}",
            "-vf", vf,
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            out_path,
        ]
    )


def concat_segments(segment_paths: list[str], out_path: str, work_dir: str) -> None:
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    list_file = Path(work_dir) / f"concat_{uuid.uuid4().hex}.txt"
    list_file.write_text(
        "\n".join(f"file '{_escape_for_concat_list(str(Path(p).resolve()))}'" for p in segment_paths),
        encoding="utf-8",
    )
    _run(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", out_path])
    list_file.unlink(missing_ok=True)


def concat_audio(audio_paths: list[str], out_path: str, work_dir: str) -> None:
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    list_file = Path(work_dir) / f"aconcat_{uuid.uuid4().hex}.txt"
    list_file.write_text(
        "\n".join(f"file '{_escape_for_concat_list(str(Path(p).resolve()))}'" for p in audio_paths),
        encoding="utf-8",
    )
    _run(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", out_path])
    list_file.unlink(missing_ok=True)


def mix_audio(
    narration_path: str, music_path: str | None, video: VideoConfig, duration_sec: float, out_path: str
) -> None:
    if not music_path or not Path(music_path).exists():
        _run(["-i", narration_path, "-t", f"{duration_sec:.3f}", "-c:a", "aac", out_path])
        return
    filter_complex = (
        f"[0:a]volume={video.narration_volume_db}dB[a0];"
        f"[1:a]aloop=loop=-1:size=2000000000,volume={video.background_music_volume_db}dB[a1];"
        f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    _run(
        [
            "-i", narration_path,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-t", f"{duration_sec:.3f}",
            "-c:a", "aac",
            out_path,
        ]
    )


def burn_captions(video_path: str, srt_path: str, video: VideoConfig, out_path: str) -> None:
    style = f"FontSize={video.caption_font_size},Alignment=2,Outline=3,Bold=1,MarginV=120"
    vf = f"subtitles='{_escape_for_filter(str(Path(srt_path).resolve()))}':force_style='{style}'"
    _run(
        [
            "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-an",
            out_path,
        ]
    )


def mux_final(video_with_captions_path: str, audio_path: str, out_path: str) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "-i", video_with_captions_path,
            "-i", audio_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac",
            "-shortest",
            out_path,
        ]
    )


def probe_duration_sec(path: str) -> float:
    result = subprocess.run(
        [ffmpeg_exe(), "-i", path, "-hide_banner"],
        capture_output=True, text=True,
    )
    for line in result.stderr.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            ts = line.split(",")[0].split("Duration:")[1].strip()
            h, m, s = ts.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0
