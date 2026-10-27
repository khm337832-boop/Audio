"""ဗီဒီယို ဖန်တီးခြင်း (workflow ရဲ့ အဆင့် ၅-၆) — `services.media` (ffmpeg) ကို ဖုံးအုပ်ထားတယ်။

`build_story_video()` က ဇာတ်ကွက်ပုံများ + အခန်းအသံကြာချိန် → motion clips → final.mp4
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import config
from models.story import Story
from services.media import (  # noqa: F401  (ပြန်လည် အသုံးပြုရန်)
    MediaError,
    build_final_video,
    combine_video_audio,
    concat_videos,
    image_to_motion_video,
    probe_duration,
)

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]


def finalize_job(
    clips: list[str | Path],
    audio_path: str | Path,
    job_dir: str | Path,
    *,
    filename: str = "final.mp4",
) -> Path:
    """clips + အသံ → `<job_dir>/final.mp4` (workflow ရဲ့ အဆင့် ၁)။"""
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    return build_final_video(clips, audio_path, job_dir / filename, work_dir=job_dir)


def build_story_video(
    story: Story,
    scenes,
    audio_path: str | Path,
    job_dir: str | Path,
    *,
    progress: ProgressFn | None = None,
) -> Path:
    """ဇာတ်ကွက်ပုံများ + အသံ → motion video → အသံပေါင်းပြီး final.mp4။"""
    job_dir = Path(job_dir)
    clip_dir = job_dir / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)

    from services.tts_service import estimate_duration

    scenes = [s for s in scenes if getattr(s, "image", None)]
    if not scenes:
        raise MediaError("ဇာတ်ကွက်ပုံ မရှိပါ — အဆင့် ၄ (ပုံဖန်တီးခြင်း) ကို အရင်လုပ်ပါ")

    clips: list[Path] = []
    total_chapters = len(story.chapters)
    for i, chapter in enumerate(story.chapters, start=1):
        duration = chapter.duration or estimate_duration(chapter.text)
        chapter_scenes = [s for s in scenes if s.chapter_index == chapter.index]
        if not chapter_scenes:  # ဒီအခန်းအတွက် ပုံ မရှိရင် အနီးစပ်ဆုံးကို သုံး
            chapter_scenes = [scenes[min(i - 1, len(scenes) - 1)]]
        per_scene = max(2.0, duration / len(chapter_scenes))

        for j, scene in enumerate(chapter_scenes):
            clip = clip_dir / f"clip_{chapter.index:03d}_{j:02d}.mp4"
            if not clip.exists() or clip.stat().st_size == 0:
                image_to_motion_video(
                    scene.image,
                    clip,
                    per_scene,
                    size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT),
                    fps=config.VIDEO_FPS,
                )
            clips.append(clip)
        if progress:
            progress(f"🎞️ motion clip {i}/{total_chapters}…")

    if progress:
        progress("🎬 ဗီဒီယိုနဲ့ အသံ ပေါင်းစပ်နေတယ်…")
    final = finalize_job(clips, audio_path, job_dir)
    logger.info("final video: %s", final)
    return final


__all__ = [
    "MediaError",
    "build_final_video",
    "build_story_video",
    "combine_video_audio",
    "concat_videos",
    "finalize_job",
    "image_to_motion_video",
    "probe_duration",
]
