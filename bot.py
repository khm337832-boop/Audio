"""Telegram bot — ဇာတ်လမ်း → အသံ → ပုံ → ဗီဒီယို → YouTube publish workflow။"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile

import config
from config import TEMP_DIR
from handlers import start_handler
from services import image_service, story_generator, tts_service, video_service
from workflow import PublishOptions, PublishWorkflow, StageError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _update(status: types.Message | None, text: str) -> None:
    if status is None:
        return
    try:
        await status.edit_text(text)
    except Exception as exc:  # message မပြောင်းနိုင်/rate limit
        logger.debug("status edit မရပါ: %s", exc)


async def _build_video(job_dir: Path, story, status: types.Message | None) -> Path:
    """အခန်းတစ်ခန်းစီအတွက် ပုံ + clip ဖန်တီးပြီး final.mp4 ထုတ်တယ်။"""
    await _update(status, "③ အခန်းပုံများ ဖန်တီးနေပါတယ်...")

    audio_path, chapter_audios = await asyncio.to_thread(tts_service.generate_voice, story)

    clips: list[Path] = []
    for i, chapter in enumerate(story.chapters):
        image_path = job_dir / "scenes" / f"scene_{i}.jpg"
        prompt = (
            f"cinematic story illustration, {story.genre}, chapter scene: "
            f"{chapter.text[:220]}, 16:9, dramatic lighting, no text"
        )
        await asyncio.to_thread(image_service.generate_scene_image, prompt, image_path)

        duration = chapter.duration or (
            chapter_audios[i]["duration"] if i < len(chapter_audios) else 5.0
        )
        clip_path = job_dir / "clips" / f"clip_{i}.mp4"
        await asyncio.to_thread(
            video_service.image_to_motion_video, image_path, clip_path, max(3.0, duration)
        )
        clips.append(clip_path)
        await _update(status, f"③ ပုံ/clip {i + 1}/{len(story.chapters)} ပြီးပါပြီ...")

    await _update(status, "④ ဗီဒီယို ပေါင်းစည်းနေပါတယ်...")
    final_video = await asyncio.to_thread(
        video_service.finalize_job, clips, audio_path, job_dir
    )
    return final_video


async def run_pipeline(message: types.Message, topic: str | None = None) -> None:
    job_dir = TEMP_DIR / f"job_{datetime.now():%Y%m%d_%H%M%S}"
    job_dir.mkdir(parents=True, exist_ok=True)
    status = await message.answer("① ဇာတ်လမ်း ရေးနေပါတယ်...")

    try:
        story = await asyncio.to_thread(story_generator.generate_full_story, topic)
        story_generator.save_story(story, job_dir)
        await _update(
            status,
            f"① ဇာတ်လမ်းရေးပြီးပါပြီ — <b>{story.title}</b>\n"
            f"(အခန်း {len(story.chapters)} ခန်း၊ စာလုံးရေ {story.total_chars})\n"
            "② အသံထွက်နေပါတယ်...",
        )

        final_video = await _build_video(job_dir, story, status)

        await _update(status, "⑤ ခေါင်းစဉ်/ဖော်ပြချက်/thumbnail ပြင်ဆင်နေပါတယ်...")
        workflow = PublishWorkflow(
            job_dir,
            final_video,
            options=PublishOptions(
                privacy_status=config.YOUTUBE_PRIVACY_STATUS,
                dry_run=True if config.DRY_RUN else None,
            ),
        )
        artifacts = await workflow.arun()

        lines = [
            "✅ <b>အားလုံး ပြီးပါပြီ</b>",
            "",
            f"📌 ခေါင်းစဉ်: {artifacts.title}",
        ]
        if artifacts.upload and artifacts.upload.dry_run:
            lines.append("🧪 DRY-RUN — YouTube API မခေါ်ပါ (payload ကို job folder မှာ သိမ်းထားတယ်)")
        elif artifacts.upload and artifacts.upload.url:
            lines.append(f"🎬 YouTube: {artifacts.upload.url}")
        lines.append(f"📁 {job_dir}")
        await _update(status, "\n".join(lines))

        await message.answer_video(FSInputFile(final_video), caption=artifacts.title[:1000])
    except (StageError, tts_service.TTSError, video_service.MediaError) as exc:
        logger.exception("pipeline မအောင်မြင်ပါ")
        await _update(status, f"❌ မအောင်မြင်ပါ\n{exc}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("မမျှော်လင့်တဲ့ အမှား")
        await _update(status, f"❌ အမှား: {exc}")


def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN မရှိပါ — .env ထဲမှာ သတ်မှတ်ပါ")

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start_handler.router)

    @dp.callback_query(lambda c: c.data == "generate_story")
    async def on_generate(callback: types.CallbackQuery) -> None:
        await callback.answer("စတင်နေပါပြီ...")
        if callback.message:
            await run_pipeline(callback.message)

    logger.info("Bot စတင်နေပါပြီ...")
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot ရပ်လိုက်ပါပြီ")
