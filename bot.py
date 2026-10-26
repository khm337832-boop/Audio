import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile

from config import BOT_TOKEN, TEMP_DIR
from handlers import start_handler
from services import (
    story_generator,
    tts_service,
    image_service,
    video_service,
    youtube_service,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def run_pipeline(message: types.Message):
    """ဇာတ်လမ်း → အသံ → ပုံ → ဗီဒီယို → YouTube"""
    status = await message.answer("① ဇာတ်လမ်း ရေးနေပါတယ်...")

    # ① ဇာတ်လမ်းရေး
    story = await story_generator.generate_full_story()
    await status.edit_text(
        f"① ဇာတ်လမ်းရေးပြီးပါပြီ (စာလုံးရေ {story['total_chars']})\n"
        f"② အသံထွက်နေပါတယ်..."
    )

    # ② အသံထွက်
    audio_path, chapter_audios = await tts_service.generate_voice(story["full_text"])
    await status.edit_text("② အသံထွက်ပြီးပါပြီ\n③ ပုံများ ဖန်တီးနေပါတယ်...")

    # ③ အခန်းတစ်ခန်းစီအတွက် ပုံ + motion clip
    clips = []
    for i, ch in enumerate(story["chapters"]):
        img_path = f"{TEMP_DIR}/scene_{i}.jpg"
        image_service.generate_image(
            f"adventure scene, {ch['text'][:200]}", img_path
        )
        duration = chapter_audios[i]["duration"] if i < len(chapter_audios) else 5
        clip = f"{TEMP_DIR}/clip_{i}.mp4"
        video_service.image_to_motion_video(img_path, clip, duration)
        clips.append(clip)

    await status.edit_text("③ ပုံများ ပြီးပါပြီ\n④ ဗီဒီယို ပေါင်းနေပါတယ်...")

    # ④ ဗီဒီယိုပေါင်း
    concat_video = f"{TEMP_DIR}/video_noaudio.mp4"
    video_service.concat_videos(clips, concat_video)
    final_video = f"{TEMP_DIR}/final.mp4"
    video_service.combine_video_audio(concat_video, audio_path, final_video)

    # ⑤ YouTube တင်
    await status.edit_text("④ ဗီဒီယို ပြီးပါပြီ\n⑤ YouTube တင်နေပါတယ်...")
    title = youtube_service.generate_seo_title("စွန့်စားခန်းဇာတ်လမ်း")
    desc = youtube_service.generate_seo_description(title, story["full_text"][:300])
    thumb = image_service.generate_thumbnail("adventure story")
    video_id = youtube_service.upload_video(final_video, title, desc, thumb)

    await status.edit_text(
        f"✅ အားလုံး ပြီးပါပြီ!\n"
        f"🎬 YouTube: https://youtu.be/{video_id}"
    )
    await message.answer_video(FSInputFile(final_video), caption="နောက်ဆုံး ဗီဒီယို")


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start_handler.router)

    @dp.callback_query(lambda c: c.data == "generate_story")
    async def on_generate(callback: types.CallbackQuery):
        await callback.answer("စတင်နေပါပြီ...")
        await run_pipeline(callback.message)

    logger.info("Bot စတင်နေပါပြီ...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot ရပ်လိုက်ပါပြီ")
