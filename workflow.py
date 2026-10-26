"""ဗီဒီယိုပေါင်းစည်းပြီးနောက် publish workflow —

    ① ဗီဒီယို (ပြီးစီး) 
      ↓
    ② ဇာတ်လမ်းအနှစ်ချုပ် + အခန်းအချက်အလက် (story.json ကနေ ယူ / မရှိရင် ထုတ်ယူ)
      ↓
    ③ generate_youtube_title() → ခေါင်းစဉ်များ
      ↓
    ④ generate_youtube_description() → SEO ဖော်ပြချက်
      ↓
    ⑤ generate_thumbnail_prompt() + generate_scene_image() → thumbnail base ပုံ
      ↓
    ⑥ PIL ဖြင့် စာသားထပ်ဆင့်ခြင်း
      ↓
    ⑦ YouTube API တင်ခြင်း
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import config
from models.story import METADATA_FILE, Story, StoryMetadata
from services import image_service, metadata_service, thumbnail_service, youtube_service
from services.youtube_service import UploadResult

logger = logging.getLogger(__name__)

PUBLISH_REPORT = "publish_result.json"
PAYLOAD_FILE = "youtube_payload.json"
FINAL_VIDEO_CANDIDATES = ("final.mp4", "video_final.mp4", "final_video.mp4", "output.mp4")
INTERMEDIATE_HINTS = ("noaudio", "clip_", "preview", "upload_source")


class StageError(RuntimeError):
    """Workflow အဆင့် တစ်ခု မအောင်မြင်တဲ့အခါ။"""


@dataclass
class PublishOptions:
    privacy_status: str | None = None
    publish_at: str | None = None
    title: str | None = None                 # ကိုယ်တိုင် သတ်မှတ်ထားတဲ့ ခေါင်းစဉ်
    title_candidates: int = 3
    tags: list[str] | None = None
    make_thumbnail: bool = True
    upload: bool = True
    dry_run: bool | None = None
    thumbnail_subtitle: str | None = None
    thumbnail_badge: str | None = None
    thumbnail_prompt: str | None = None


@dataclass
class StageResult:
    name: str
    ok: bool
    seconds: float = 0.0
    message: str = ""


@dataclass
class PublishArtifacts:
    job_dir: Path
    metadata: StoryMetadata
    video_path: Path
    title_candidates: list[str] = field(default_factory=list)
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    thumbnail_prompt: str = ""
    thumbnail_base: Path | None = None
    thumbnail: Path | None = None
    upload: UploadResult | None = None
    stages: list[StageResult] = field(default_factory=list)

    @property
    def stage_report(self) -> list[str]:
        return [f"{'✅' if s.ok else '❌'} {s.name} ({s.seconds:.1f}s) {s.message}".strip()
                for s in self.stages]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["job_dir"] = str(self.job_dir)
        data["video_path"] = str(self.video_path)
        data["thumbnail"] = str(self.thumbnail) if self.thumbnail else None
        data["thumbnail_base"] = str(self.thumbnail_base) if self.thumbnail_base else None
        return data


def resolve_final_video(job_dir: str | Path) -> Path:
    """`final.mp4` စတဲ့ ပုံစံဖိုင်ကို ရှာတယ် (မရှိရင် အသစ်ဆုံး mp4 ကို ယူ)။"""
    job_dir = Path(job_dir)
    for name in FINAL_VIDEO_CANDIDATES:
        candidate = job_dir / name
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate

    mp4s = [
        p for p in job_dir.glob("*.mp4")
        if p.is_file() and not any(hint in p.name.lower() for hint in INTERMEDIATE_HINTS)
    ]
    if mp4s:
        return max(mp4s, key=lambda p: p.stat().st_mtime)
    raise FileNotFoundError(f"ဗီဒီယိုဖိုင် မတွေ့ပါ: {job_dir} (final.mp4 ထည့်ပါ)")


class PublishWorkflow:
    """ဗီဒီယိုပြီးသားဖိုင်ကနေ YouTube တင်တဲ့အထိ အဆင့်လိုက် အလုပ်လုပ်တဲ့ class။"""

    def __init__(
        self,
        job_dir: str | Path,
        video_path: str | Path | None = None,
        *,
        options: PublishOptions | None = None,
        story: Story | None = None,
        image_generator: Callable[..., Path] | None = None,
        uploader: Callable[..., UploadResult] | None = None,
    ) -> None:
        self.job_dir = Path(job_dir)
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.options = options or PublishOptions()
        self.story = story
        self.image_generator = image_generator or image_service.generate_scene_image
        self.uploader = uploader or youtube_service.upload_video
        self._video_path = Path(video_path) if video_path else None
        self.artifacts: PublishArtifacts | None = None

    # ------------------------------------------------------------- helpers
    def _stage(self, name: str, func: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        try:
            result = func()
        except Exception as exc:
            elapsed = time.perf_counter() - started
            if self.artifacts is not None:
                self.artifacts.stages.append(StageResult(name, False, elapsed, str(exc)))
            logger.exception("အဆင့် '%s' မအောင်မြင်ပါ: %s", name, exc)
            raise StageError(f"{name}: {exc}") from exc

        elapsed = time.perf_counter() - started
        if self.artifacts is not None:
            self.artifacts.stages.append(StageResult(name, True, elapsed))
        logger.info("✅ %s (%.1fs)", name, elapsed)
        return result

    # ------------------------------------------------------------- ① metadata
    def load_metadata(self) -> StoryMetadata:
        return metadata_service.load_or_extract_metadata(
            self.job_dir, story=self.story, persist=True
        )

    # ------------------------------------------------------------- ② titles
    def make_titles(self, metadata: StoryMetadata) -> str:
        candidates = youtube_service.generate_youtube_title(
            metadata, count=self.options.title_candidates
        )
        self.artifacts.title_candidates = candidates
        if self.options.title:
            title = self.options.title.strip()
            if not title:
                raise ValueError("ခေါင်းစဉ် ဗလာ")
            if len(title) > config.TITLE_MAX_CHARS:
                raise ValueError(f"ခေါင်းစဉ် ရှည်လွန်းတယ် ({len(title)} > {config.TITLE_MAX_CHARS})")
            if title not in candidates:
                candidates.insert(0, title)
        else:
            title = youtube_service.pick_title(candidates, metadata)
        self.artifacts.title = title
        return title

    # ------------------------------------------------------------- ③ description
    def make_description(self, metadata: StoryMetadata, title: str) -> str:
        description = youtube_service.generate_youtube_description(metadata, title)
        self.artifacts.description = description
        self.artifacts.tags = self.options.tags or youtube_service.generate_youtube_tags(metadata)
        return description

    # ------------------------------------------------------------- ④ thumbnail prompt
    def make_thumbnail_prompt(self, metadata: StoryMetadata) -> str:
        prompt = self.options.thumbnail_prompt or thumbnail_service.generate_thumbnail_prompt(metadata)
        self.artifacts.thumbnail_prompt = prompt
        return prompt

    # ------------------------------------------------------------- ⑤ base image
    def make_thumbnail_base(self, prompt: str) -> Path:
        path = self.job_dir / "thumbnail_base.jpg"
        if not path.exists() or path.stat().st_size == 0:
            self.image_generator(
                prompt, path,
                width=config.THUMBNAIL_SIZE[0], height=config.THUMBNAIL_SIZE[1],
            )
        self.artifacts.thumbnail_base = path
        return path

    # ------------------------------------------------------------- ⑥ PIL overlay
    def overlay_thumbnail_text(self, base_path: Path, metadata: StoryMetadata) -> Path:
        path = thumbnail_service.compose_thumbnail(
            base_path,
            self.artifacts.title,
            self.job_dir / "thumbnail.jpg",
            subtitle=(
                self.options.thumbnail_subtitle
                if self.options.thumbnail_subtitle is not None
                else thumbnail_service.clamp_text(
                    metadata.logline or metadata.summary, 70
                )
            ),
            badge=self.options.thumbnail_badge if self.options.thumbnail_badge is not None
            else (metadata.genre or "ဇာတ်လမ်း"),
        )
        self.artifacts.thumbnail = path
        return path

    # ------------------------------------------------------------- ⑦ upload
    def upload(self, video_path: Path) -> UploadResult:
        result = self.uploader(
            video_path,
            self.artifacts.title,
            self.artifacts.description,
            self.artifacts.thumbnail,
            tags=self.artifacts.tags,
            privacy_status=self.options.privacy_status,
            publish_at=self.options.publish_at,
            dry_run=self.options.dry_run,
        )
        self.artifacts.upload = result
        return result

    # ------------------------------------------------------------- report
    def save_report(self) -> Path:
        payload = {
            "title": self.artifacts.title,
            "description": self.artifacts.description,
            "tags": self.artifacts.tags,
            "title_candidates": self.artifacts.title_candidates,
            "thumbnail_prompt": self.artifacts.thumbnail_prompt,
            "thumbnail": str(self.artifacts.thumbnail) if self.artifacts.thumbnail else None,
            "privacy_status": self.options.privacy_status or config.YOUTUBE_PRIVACY_STATUS,
            "stages": [asdict(s) for s in self.artifacts.stages],
            "upload": self.artifacts.upload.to_dict() if self.artifacts.upload else None,
        }
        youtube_service.dump_payload(self.job_dir / PAYLOAD_FILE, **payload)
        report = self.job_dir / PUBLISH_REPORT
        report.write_text(
            json.dumps(self.artifacts.to_dict(), ensure_ascii=False, indent=2, default=str),
            "utf-8",
        )
        return report

    # ------------------------------------------------------------- main (sync)
    def run(self) -> PublishArtifacts:
        video_path = self._video_path or resolve_final_video(self.job_dir)
        if not video_path.is_file() or video_path.stat().st_size == 0:
            raise StageError(f"ဗီဒီယိုဖိုင် မရှိပါ / ဗလာ: {video_path}")

        metadata = self._stage("ဇာတ်လမ်းအချက်အလက် ထုတ်ယူခြင်း", self.load_metadata)
        self.artifacts = PublishArtifacts(
            job_dir=self.job_dir, metadata=metadata, video_path=video_path
        )

        try:
            self._stage("ခေါင်းစဉ် ဖန်တီးခြင်း", lambda: self.make_titles(metadata))
            self._stage(
                "ဖော်ပြချက် ဖန်တီးခြင်း (SEO)",
                lambda: self.make_description(metadata, self.artifacts.title),
            )
            if self.options.make_thumbnail:
                prompt = self._stage("Thumbnail prompt ဖန်တီးခြင်း", lambda: self.make_thumbnail_prompt(metadata))
                base = self._stage("Thumbnail base ပုံ ဖန်တီးခြင်း", lambda: self.make_thumbnail_base(prompt))
                self._stage("Thumbnail စာသား ထပ်ဆင့်ခြင်း", lambda: self.overlay_thumbnail_text(base, metadata))
            if self.options.upload:
                self._stage("YouTube တင်ခြင်း", lambda: self.upload(video_path))
        finally:
            self.save_report()

        return self.artifacts

    # ------------------------------------------------------------- main (async)
    async def arun(self) -> PublishArtifacts:
        """Telegram/async handler ထဲကနေ ခေါ်ရန် — blocking အလုပ်တွေကို thread ထဲ ရွှေ့တယ်။"""
        return await asyncio.to_thread(self.run)


async def publish_after_video(
    job_dir: str | Path,
    video_path: str | Path | None = None,
    **kwargs: Any,
) -> PublishArtifacts:
    """ဗီဒီယိုပေါင်းစည်းပြီးတာနဲ့ ခေါ်ရတဲ့ one-liner။ `kwargs` က PublishOptions အတွက်။"""
    options = PublishOptions(**kwargs)
    workflow = PublishWorkflow(job_dir, video_path, options=options)
    return await workflow.arun()


__all__ = [
    "METADATA_FILE",
    "PUBLISH_REPORT",
    "PublishArtifacts",
    "PublishOptions",
    "PublishWorkflow",
    "StageError",
    "publish_after_video",
    "resolve_final_video",
]
