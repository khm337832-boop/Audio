"""ဇာတ်ကွက်အလိုက် ပုံဖန်တီးခြင်း (workflow ရဲ့ အဆင့် ၄)။

① အခန်းတစ်ခန်းစီကို ဇာတ်ကွက် (scene) များအဖြစ် ခွဲပြီး ပုံဖန်တီးရေး prompt ရေးတယ် (LLM၊ မရရင် heuristic)
② Prompt တွေကို ပုံအဖြစ် ပြောင်းတယ် (`image_service.generate_scene_image`၊ concurrency နဲ့)
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import config
from models.story import Story
from services import image_service, llm
from utils.textkit import clamp_text, normalize_whitespace

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]

SCENES_FILE = "scenes.json"

_STYLE = (
    "cinematic 16:9 story illustration, dramatic lighting, rich colors, detailed background, "
    "semi-realistic digital painting, emotional atmosphere, no text, no watermark, no letters"
)


@dataclass
class Scene:
    index: int
    chapter_index: int
    chapter_title: str
    prompt: str
    caption: str = ""
    image: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ ① prompts
def _heuristic_prompts(story: Story, per_chapter: int) -> list[Scene]:
    scenes: list[Scene] = []
    for chapter in story.chapters:
        sentences = [s.strip() for s in chapter.text.split("။") if s.strip()]
        for slot in range(per_chapter):
            piece = sentences[slot] if slot < len(sentences) else (sentences[-1] if sentences else chapter.title)
            caption = clamp_text(piece, 120)
            prompt = (
                f"{story.genre or 'adventure'} story scene: {caption}, "
                f"key moment of chapter '{chapter.title}', {_STYLE}"
            )
            scenes.append(
                Scene(
                    index=len(scenes),
                    chapter_index=chapter.index,
                    chapter_title=chapter.title,
                    prompt=prompt,
                    caption=caption,
                )
            )
    return scenes


def _llm_prompts(story: Story, per_chapter: int) -> list[Scene] | None:
    chapter_block = "\n".join(
        f"အခန်း {i + 1} — {ch.title}\n{clamp_text(ch.text, 700)}"
        for i, ch in enumerate(story.chapters)
    )
    prompt = f"""အောက်ပါ မြန်မာဇာတ်လမ်းအတွက် ဇာတ်ကွက်ပုံ (scene image) prompt များ ရေးပါ။

ဇာတ်လမ်း: {story.title} | အမျိုးအစား: {story.genre}
ဇာတ်ကောင်များ: {", ".join(story.characters[:6])}

{chapter_block[:6000]}

လိုအပ်ချက်:
- အခန်းတစ်ခန်းကို ဇာတ်ကွက် {per_chapter} ကွက် (စုစုပေါင်း {len(story.chapters) * per_chapter} ကွက်)
- prompt တစ်ခုကို အင်္ဂလိပ်လို ၂၅-၄၅ လုံး၊ ရုပ်ပုံဖန်တီးရေး (image model) အတွက် အသေးစိတ်
- ဇာတ်ကောင် ပုံသဏ္ဌာန်/ပတ်ဝန်းကျင်/အလင်း/ခံစားချက် ပါဝင်ပါ
- စာသား၊ စာလုံး၊ watermark မပါစေရ
- "caption": အဲဒီဇာတ်ကွက်ကို ဖော်ပြတဲ့ မြန်မာစာကြောင်းတို

JSON တစ်ခုတည်းသာ ပြန်ပါ:
{{"scenes": [{{"chapter": 1, "prompt": "...", "caption": "..."}}]}}"""
    try:
        data = llm.generate_json(prompt, temperature=0.9, max_output_tokens=4096)
    except llm.LLMUnavailable as exc:
        logger.info("scene prompt LLM မရပါ — heuristic သုံးမယ်: %s", exc)
        return None
    if not isinstance(data, dict):
        return None

    raw_scenes = data.get("scenes") or []
    scenes: list[Scene] = []
    for raw in raw_scenes:
        if not isinstance(raw, dict):
            continue
        prompt_text = normalize_whitespace(str(raw.get("prompt") or ""))
        if not prompt_text:
            continue
        chapter_no = int(raw.get("chapter") or 1) - 1
        chapter_no = max(0, min(len(story.chapters) - 1, chapter_no))
        chapter = story.chapters[chapter_no]
        scenes.append(
            Scene(
                index=len(scenes),
                chapter_index=chapter.index,
                chapter_title=chapter.title,
                prompt=f"{prompt_text}, {_STYLE}",
                caption=normalize_whitespace(str(raw.get("caption") or "")),
            )
        )
    if not scenes:
        return None
    return scenes


def build_scene_plan(story: Story, per_chapter: int | None = None) -> list[Scene]:
    """ဇာတ်ကွက် စာရင်း (prompt + caption) ကို ဖန်တီးတယ်။"""
    per_chapter = max(1, per_chapter or config.SCENES_PER_CHAPTER)
    scenes = _llm_prompts(story, per_chapter) if llm.available() else None
    if not scenes:
        scenes = _heuristic_prompts(story, per_chapter)

    # အခန်းတစ်ခန်းမှာ scene အနည်းဆုံး ၁ ကွက် ရှိရမယ်
    covered = {s.chapter_index for s in scenes}
    for chapter in story.chapters:
        if chapter.index not in covered:
            scenes.append(
                Scene(
                    index=len(scenes),
                    chapter_index=chapter.index,
                    chapter_title=chapter.title,
                    prompt=f"{story.genre} scene: {clamp_text(chapter.text, 150)}, {_STYLE}",
                    caption=clamp_text(chapter.text, 120),
                )
            )
    return scenes


def save_scene_plan(scenes: list[Scene], job_dir: str | Path) -> Path:
    path = Path(job_dir) / SCENES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([s.to_dict() for s in scenes], ensure_ascii=False, indent=2), "utf-8"
    )
    return path


# ------------------------------------------------------------------ ② images
def render_scene_images(
    scenes: list[Scene],
    work_dir: str | Path,
    *,
    concurrency: int | None = None,
    progress: ProgressFn | None = None,
    image_generator: Callable[..., Path] = image_service.generate_scene_image,
) -> list[Scene]:
    """Scene တစ်ခုစီအတွက် ပုံဖိုင် ထုတ်တယ် (thread pool)။"""
    work_dir = Path(work_dir)
    scene_dir = work_dir / "scenes"
    scene_dir.mkdir(parents=True, exist_ok=True)
    concurrency = max(1, concurrency or config.IMAGE_CONCURRENCY)

    def _render(scene: Scene) -> Scene:
        out = scene_dir / f"scene_{scene.index:03d}.jpg"
        try:
            image_generator(
                scene.prompt, out,
                width=config.VIDEO_WIDTH, height=config.VIDEO_HEIGHT,
                seed=scene.index,
            )
            scene.image = str(out)
        except Exception as exc:  # ပုံတစ်ခု မရရင် ကျန်တာ ဆက်သွား
            logger.warning("scene %s ပုံ မထုတ်နိုင်ပါ: %s", scene.index, exc)
        return scene

    done = 0
    total = len(scenes)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for scene in pool.map(_render, scenes):
            done += 1
            if progress:
                progress(f"🖼️ ဇာတ်ကွက်ပုံ {done}/{total}…")
    return scenes


__all__ = [
    "SCENES_FILE",
    "Scene",
    "build_scene_plan",
    "render_scene_images",
    "save_scene_plan",
]
