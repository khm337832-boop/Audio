"""ဗီဒီယို ဖန်တီးခြင်း — `services.media` (ffmpeg) ကို ပါးလှပ်စွာ ဖုံးအုပ်ထားတယ်။

`workflow.PublishWorkflow` က ဒီအဆင့်ရဲ့ ရလဒ် `final.mp4` ကို လက်ခံတယ်။
"""

from __future__ import annotations

from pathlib import Path

from services.media import (  # noqa: F401  (ပြန်လည် အသုံးပြုရန်)
    MediaError,
    build_final_video,
    combine_video_audio,
    concat_videos,
    image_to_motion_video,
    probe_duration,
)


def finalize_job(
    clips: list[str | Path],
    audio_path: str | Path,
    job_dir: str | Path,
    *,
    filename: str = "final.mp4",
) -> Path:
    """workflow ရဲ့ ပထမအဆင့် — clips + အသံ → `<job_dir>/final.mp4`။"""
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    return build_final_video(clips, audio_path, job_dir / filename, work_dir=job_dir)


__all__ = [
    "MediaError",
    "build_final_video",
    "combine_video_audio",
    "concat_videos",
    "finalize_job",
    "image_to_motion_video",
    "probe_duration",
]
