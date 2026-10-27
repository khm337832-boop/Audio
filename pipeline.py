"""အဆင့် ၂–၈ တစ်ခုတည်းသော pipeline —

    ② ဇာတ်လမ်းရေး (၂၀,၀၀၀–၂၅,၀၀၀ စာလုံး)
    ③ voice over (မြန်မာ TTS / ElevenLabs Charon)
    ④ ဇာတ်ကွက်အလိုက် ပုံဖန်တီး
    ⑤ motion video
    ⑥ အသံနဲ့ ပေါင်းစပ်
    ⑦ YouTube သင်္ကေတပုံ + SEO (title/description)
    ⑧ YouTube တင်

Bot နဲ့ CLI နှစ်ခုလုံး ဒီ class ကို ခေါ်တယ်။
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import config
from models.story import Story
from services import scene_service, story_generator, tts_service, video_service
from workflow import PublishArtifacts, PublishOptions, PublishWorkflow

logger = logging.getLogger(__name__)

PIPELINE_REPORT = "pipeline_result.json"

ProgressFn = Callable[[str], None]


class PipelineError(RuntimeError):
    pass


@dataclass
class PipelineOptions:
    topic: str | None = None
    language: str | None = None
    min_chars: int | None = None
    max_chars: int | None = None
    target_chars: int | None = None
    tts_provider: str | None = None          # local | elevenlabs | None(auto)
    scenes_per_chapter: int | None = None
    upload: bool = True
    dry_run: bool | None = None
    privacy_status: str | None = None
    publish_at: str | None = None
    title: str | None = None
    make_thumbnail: bool = True


@dataclass
class StageTiming:
    name: str
    seconds: float
    ok: bool
    message: str = ""


@dataclass
class PipelineResult:
    job_dir: Path
    story: Story
    video_path: Path | None = None
    audio_path: Path | None = None
    scene_images: list[str] = field(default_factory=list)
    scenes: list[dict] = field(default_factory=list)
    publish: PublishArtifacts | None = None
    stages: list[StageTiming] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def story_chars(self) -> int:
        return self.story.total_chars

    @property
    def duration_seconds(self) -> float:
        return self.story.total_duration

    @property
    def video_id(self) -> str | None:
        return self.publish.upload.video_id if self.publish and self.publish.upload else None

    @property
    def video_url(self) -> str | None:
        if self.publish and self.publish.upload and not self.publish.upload.dry_run:
            return self.publish.upload.url or None
        return None

    def stage_report(self) -> list[str]:
        return [
            f"{'✅' if s.ok else '❌'} {s.name} — {s.seconds:.1f}s"
            + (f" ({s.message})" if s.message else "")
            for s in self.stages
        ]

    def summary(self) -> dict[str, Any]:
        return {
            "job_dir": str(self.job_dir),
            "title": self.story.title,
            "story_chars": self.story_chars,
            "target_chars": self.story.target_chars,
            "length_ok": self.story.length_ok,
            "chapters": len(self.story.chapters),
            "duration_seconds": round(self.duration_seconds, 1),
            "scenes": len(self.scenes),
            "video": str(self.video_path) if self.video_path else None,
            "thumbnail": str(self.publish.thumbnail) if self.publish and self.publish.thumbnail else None,
            "youtube": self.publish.upload.to_dict() if self.publish and self.publish.upload else None,
            "stages": [asdict(s) for s in self.stages],
            "warnings": self.warnings,
        }


class ProgressTracker:
    """Thread ထဲမှာ run နေတဲ့ pipeline ရဲ့ အခြေအနေကို bot က ဖတ်နိုင်အောင် သိမ်းထားတယ်။"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest = "စတင်နေပါတယ်…"
        self.history: list[str] = []

    def __call__(self, message: str) -> None:
        with self._lock:
            self._latest = message
            self.history.append(message)
            if len(self.history) > 200:
                del self.history[:100]
        logger.info("[progress] %s", message)

    @property
    def latest(self) -> str:
        with self._lock:
            return self._latest


class StoryPipeline:
    """ဇာတ်လမ်းရေးကနေ YouTube တင်တဲ့အထိ အဆင့်လိုက် အလုပ်လုပ်တဲ့ class။

    Test အတွက် အဆင့်တစ်ခုစီကို inject လုပ်နိုင်တယ် (`tts_fn`, `video_fn`, …)။
    """

    def __init__(
        self,
        job_dir: str | Path | None = None,
        *,
        options: PipelineOptions | None = None,
        progress: ProgressFn | None = None,
        story_fn: Callable[..., Story] = story_generator.generate_full_story,
        tts_fn: Callable[..., tuple[Path, list[dict]]] = tts_service.generate_voice,
        scene_plan_fn: Callable[..., list] = scene_service.build_scene_plan,
        render_fn: Callable[..., list] = scene_service.render_scene_images,
        video_fn: Callable[..., Path] = video_service.build_story_video,
        publish_factory: Callable[..., PublishWorkflow] = PublishWorkflow,
    ) -> None:
        self.options = options or PipelineOptions()
        self.job_dir = Path(job_dir) if job_dir else (
            config.TEMP_DIR / f"job_{datetime.now():%Y%m%d_%H%M%S}"
        )
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.progress = progress or (lambda _msg: None)
        self.story_fn = story_fn
        self.tts_fn = tts_fn
        self.scene_plan_fn = scene_plan_fn
        self.render_fn = render_fn
        self.video_fn = video_fn
        self.publish_factory = publish_factory
        self.result: PipelineResult | None = None
        self._stages: list[StageTiming] = []

    # ------------------------------------------------------------- helpers
    def _stage(self, name: str, func: Callable[[], Any]) -> Any:
        self.progress(f"⏳ {name}…")
        started = time.perf_counter()
        try:
            value = func()
        except Exception as exc:
            elapsed = time.perf_counter() - started
            self._stages.append(StageTiming(name, elapsed, False, str(exc)[:200]))
            if self.result is not None:
                self.result.stages = list(self._stages)
            logger.exception("အဆင့် '%s' မအောင်မြင်ပါ", name)
            raise PipelineError(f"{name} မအောင်မြင်ပါ: {exc}") from exc
        elapsed = time.perf_counter() - started
        self._stages.append(StageTiming(name, elapsed, True))
        if self.result is not None:
            self.result.stages = list(self._stages)
        logger.info("✅ %s (%.1fs)", name, elapsed)
        return value

    # ------------------------------------------------------------- steps
    def make_story(self) -> Story:
        opts = self.options
        return self.story_fn(
            opts.topic,
            target_chars=opts.target_chars,
            min_chars=opts.min_chars,
            max_chars=opts.max_chars,
            language=opts.language,
            progress=self.progress,
        )

    def make_audio(self, story: Story) -> tuple[Path, list[dict]]:
        return self.tts_fn(
            story,
            provider=self.options.tts_provider,
            progress=self.progress,
            work_dir=self.job_dir,
        )

    def make_scenes(self, story: Story) -> list:
        plan = self.scene_plan_fn(story, self.options.scenes_per_chapter)
        scene_service.save_scene_plan(plan, self.job_dir)
        return self.render_fn(plan, self.job_dir, progress=self.progress)

    def make_video(self, story: Story, scenes: list, audio_path: Path) -> Path:
        return self.video_fn(story, scenes, audio_path, self.job_dir, progress=self.progress)

    def publish_video(self, video_path: Path) -> PublishArtifacts:
        opts = self.options
        workflow = self.publish_factory(
            self.job_dir,
            video_path,
            options=PublishOptions(
                privacy_status=opts.privacy_status,
                publish_at=opts.publish_at,
                title=opts.title,
                make_thumbnail=opts.make_thumbnail,
                upload=opts.upload,
                dry_run=opts.dry_run,
            ),
        )
        return workflow.run()

    # ------------------------------------------------------------- main
    def run(self) -> PipelineResult:
        self.progress("🚀 လုပ်ငန်းစဉ် စတင်ပါပြီ…")

        story = self._stage("① ဇာတ်လမ်းရေး", self.make_story)
        story_generator.save_story(story, self.job_dir)
        self.result = PipelineResult(job_dir=self.job_dir, story=story)
        self.result.stages = list(self._stages)
        if not story.length_ok:
            self.result.warnings.append(
                f"စာလုံးရေ {story.total_chars:,} — ပစ်မှတ် "
                f"{config.STORY_MIN_CHARS:,}–{config.STORY_MAX_CHARS:,} မကိုက်ပါ"
            )
        self.result.warnings.extend(story.generation_notes)
        self.progress(
            f"📖 ဇာတ်လမ်း ပြီးပါပြီ — “{story.title}” "
            f"({len(story.chapters)} အခန်း၊ {story.total_chars:,} စာလုံး)"
        )

        audio_path, _chapter_info = self._stage("② အသံထွက် (voice over)", lambda: self.make_audio(story))
        self.result.audio_path = Path(audio_path)
        self.progress(f"🎙️ အသံ ပြီးပါပြီ — စုစုပေါင်း {story.total_duration / 60:.1f} မိနစ်")

        scenes = self._stage("③ ဇာတ်ကွက်ပုံများ ဖန်တီးခြင်း", lambda: self.make_scenes(story))
        self.result.scenes = [s.to_dict() for s in scenes]
        self.result.scene_images = [s.image for s in scenes if getattr(s, "image", None)]
        self.progress(f"🖼️ ပုံ {len(self.result.scene_images)} ပုံ ပြီးပါပြီ")

        video_path = self._stage(
            "④ motion video + အသံပေါင်းစပ်ခြင်း",
            lambda: self.make_video(story, scenes, self.result.audio_path),
        )
        self.result.video_path = Path(video_path)
        self.progress("🎬 final video ရပါပြီ")

        if self.options.upload:
            artifacts = self._stage(
                "⑤ YouTube (thumbnail + SEO + တင်ခြင်း)",
                lambda: self.publish_video(self.result.video_path),
            )
            self.result.publish = artifacts
            if artifacts.upload and artifacts.upload.dry_run:
                self.progress("🧪 dry-run — YouTube API မခေါ်ပါ (payload သိမ်းထားတယ်)")
            else:
                self.progress(f"🎉 YouTube တင်ပြီး — {artifacts.upload.url if artifacts.upload else ''}")

        self._save_report()
        return self.result

    async def arun(self) -> PipelineResult:
        return await asyncio.to_thread(self.run)

    def stage_report(self) -> list[str]:
        """အောင်မြင်/မအောင်မြင် အခြေအနေ (failure ဖြစ်လည်း ရနိုင်တယ်)။"""
        return [
            f"{'✅' if s.ok else '❌'} {s.name} — {s.seconds:.1f}s"
            + (f" ({s.message})" if s.message else "")
            for s in self._stages
        ]

    def _save_report(self) -> Path:
        path = self.job_dir / PIPELINE_REPORT
        payload = self.result.summary() if self.result else {}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        return path


async def produce_and_publish(job_dir: str | Path | None = None, **options: Any) -> PipelineResult:
    """Bot/CLI အတွက် one-liner: `await produce_and_publish(topic="…", dry_run=True)`"""
    opts = PipelineOptions(**options)
    return await StoryPipeline(job_dir, options=opts).arun()


__all__ = [
    "PIPELINE_REPORT",
    "PipelineError",
    "PipelineOptions",
    "PipelineResult",
    "ProgressTracker",
    "StoryPipeline",
    "produce_and_publish",
]
