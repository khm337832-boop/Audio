"""Telegram bot —

“🚀 ဇာတ်လမ်းဖန်တီးပြီး YouTube တင်မယ်” ကို နှိပ်လိုက်တာနဲ့
ဇာတ်လမ်းရေး (၂၀,၀၀၀–၂၅,၀၀၀ စာလုံး) → voice over → ဇာတ်ကွက်ပုံ → motion video →
အသံပေါင်း → thumbnail + SEO → YouTube တင်ခြင်း အထိ အလိုအလျောက် လုပ်ပေးတယ်။

ဗီဒီယိုဖိုင် ပြီးသားရှိရင် ဖိုင်ကို ပို့ပြီး “YouTube တင်မယ်” ကို နှိပ်လိုက်ရုံပါ။
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile

import config
from config import TEMP_DIR
from handlers import start_handler
from pipeline import PipelineError, PipelineOptions, PipelineResult, ProgressTracker, StoryPipeline
from workflow import PublishOptions, PublishWorkflow, StageError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TELEGRAM_VIDEO_LIMIT = 50 * 1024 * 1024  # Bot API က 50MB အထိသာ ပို့နိုင်တယ်

# user_id → {"mode": "real"|"dry", "waiting": "topic"} (memory only)
_PENDING: dict[int, dict] = {}


def _new_job_dir(prefix: str = "job") -> Path:
    return TEMP_DIR / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}"


async def _safe_edit(status: types.Message | None, text: str, markup=None) -> None:
    if status is None:
        return
    try:
        await status.edit_text(text, reply_markup=markup)
    except Exception as exc:  # စာသား မပြောင်း/rate limit
        logger.debug("status edit မရပါ: %s", exc)


async def _run_in_thread_with_progress(status, tracker: ProgressTracker, func):
    """Blocking pipeline ကို thread ထဲမှာ run ပြီး status message ကို update လုပ်တယ်။"""
    task = asyncio.create_task(asyncio.to_thread(func))
    started = time.time()
    last = ""
    while not task.done():
        await asyncio.sleep(4)
        message = tracker.latest
        if message != last and not task.done():
            elapsed = int(time.time() - started)
            await _safe_edit(status, f"{message}\n\n⏱ {elapsed // 60}:{elapsed % 60:02d}")
            last = message
    return await task


def _result_text(result: PipelineResult) -> str:
    lines = [
        "✅ <b>ပြီးပါပြီ</b>",
        "",
        f"📖 ဇာတ်လမ်း: <b>{result.story.title}</b>",
        f"✍️ စာလုံးရေ: {result.story_chars:,} (ပစ်မှတ် {result.story.target_chars:,})",
        f"🎬 အခန်း: {len(result.story.chapters)} | ကြာချိန်: {result.duration_seconds / 60:.1f} မိနစ်",
        f"🖼️ ဇာတ်ကွက်ပုံ: {len(result.scene_images)}",
    ]
    if result.publish:
        lines += ["", f"📌 ခေါင်းစဉ်: {result.publish.title}"]
        upload = result.publish.upload
        if upload and upload.dry_run:
            lines.append("🧪 <b>dry-run</b> — YouTube API မခေါ်ပါ (စမ်းသပ်မှု)")
            lines.append(f"video id: <code>{upload.video_id}</code>")
        elif upload and upload.url:
            lines.append(f"🎬 YouTube: {upload.url}")
            lines.append(f"🔒 privacy: {upload.privacy_status}")
            if result.publish.thumbnail:
                lines.append("🖼️ thumbnail တင်ပြီး")
    if result.warnings:
        lines += ["", "⚠️ " + "\n⚠️ ".join(result.warnings[:4])]
    lines += ["", f"📁 <code>{result.job_dir}</code>"]
    return "\n".join(lines)


async def _send_final(message: types.Message, result: PipelineResult) -> None:
    video_path = result.video_path
    if video_path and Path(video_path).is_file():
        size = Path(video_path).stat().st_size
        if size <= TELEGRAM_VIDEO_LIMIT:
            try:
                await message.answer_video(
                    FSInputFile(video_path),
                    caption=result.story.title[:900],
                    supports_streaming=True,
                )
                return
            except Exception as exc:
                logger.warning("ဗီဒီယို ပို့မရပါ: %s", exc)
        await message.answer(f"🎬 ဗီဒီယိုဖိုင် ({size / 1024 / 1024:.0f}MB) — Telegram limit ကျော်တာမို့ ဖိုင်လမ်းကြောင်း:\n<code>{video_path}</code>")


# ===================================================================== produce
async def run_full_pipeline(
    message: types.Message,
    *,
    topic: str | None = None,
    dry_run: bool = False,
) -> None:
    job_dir = _new_job_dir()
    tracker = ProgressTracker()
    mode = "🧪 စမ်းသပ် (dry-run)" if dry_run else "🚀 တကယ် YouTube တင်မယ်"
    status = await message.answer(
        f"{mode}\n\n📖 ဇာတ်လမ်း {config.STORY_MIN_CHARS:,}–{config.STORY_MAX_CHARS:,} စာလုံး ရေးတော့မယ်…\n"
        f"📁 <code>{job_dir.name}</code>"
    )

    pipeline = StoryPipeline(
        job_dir,
        options=PipelineOptions(
            topic=topic,
            dry_run=True if dry_run else None,
            privacy_status=config.YOUTUBE_PRIVACY_STATUS,
        ),
        progress=tracker,
    )

    try:
        result = await _run_in_thread_with_progress(status, tracker, pipeline.run)
    except (PipelineError, StageError, Exception) as exc:  # noqa: BLE001
        logger.exception("pipeline မအောင်မြင်ပါ")
        report = "\n".join(pipeline.stage_report())
        hint = ""
        text = str(exc)
        if "TTS" in text:
            hint = (
                "\n\n💡 မြန်မာ TTS အတွက် `.env` မှာ "
                "<code>TTS_COMMAND</code> သတ်မှတ်ပါ (သို့) "
                "<code>TTS_PROVIDER=elevenlabs</code> + <code>ELEVENLABS_API_KEY</code> ထည့်ပါ"
            )
        elif "YouTube" in text or "OAuth" in text:
            hint = "\n\n💡 YouTube တင်ရန် <code>client_secret.json</code> လိုပါ (သို့) dry-run သုံးပါ"
        elif "ffmpeg" in text:
            hint = "\n\n💡 <code>sudo apt install ffmpeg</code>"
        await _safe_edit(status, f"❌ မအောင်မြင်ပါ\n{text}{hint}" + (f"\n\n{report}" if report else ""))
        return

    await _safe_edit(status, _result_text(result))
    await _send_final(message, result)


# ===================================================================== upload existing
async def _publish_existing(message: types.Message, job_dir: Path, dry_run: bool) -> None:
    video = next(iter(sorted(job_dir.glob("*.mp4"))), None)
    if video is None:
        await message.answer("❌ ဗီဒီယိုဖိုင် မတွေ့ပါ")
        return

    tracker = ProgressTracker()
    status = await message.answer("⏳ thumbnail + SEO ပြင်ဆင်နေတယ်…")
    workflow = PublishWorkflow(
        job_dir,
        video,
        options=PublishOptions(dry_run=True if dry_run else None,
                               privacy_status=config.YOUTUBE_PRIVACY_STATUS),
    )

    def _run():
        return workflow.run()

    try:
        artifacts = await _run_in_thread_with_progress(status, tracker, _run)
    except Exception as exc:  # noqa: BLE001
        await _safe_edit(status, f"❌ YouTube တင် မရပါ: {exc}")
        return

    upload = artifacts.upload
    lines = ["✅ ပြီးပါပြီ", "", f"📌 {artifacts.title}"]
    if upload and upload.dry_run:
        lines.append(f"🧪 dry-run — video id: <code>{upload.video_id}</code>")
    elif upload:
        lines.append(f"🎬 {upload.url}")
    await _safe_edit(status, "\n".join(lines))


# ===================================================================== main
def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN မရှိပါ — .env ထဲမှာ သတ်မှတ်ပါ")

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start_handler.router)

    @dp.callback_query(F.data.startswith("produce:"))
    async def on_produce(callback: types.CallbackQuery) -> None:
        mode = callback.data.split(":", 1)[1]  # real | dry | ask
        await callback.answer("စတင်နေပါပြီ…")
        if callback.from_user and mode != "ask":
            _PENDING.pop(callback.from_user.id, None)  # topic စောင့်နေတာ ပယ်ဖျက်
        if callback.from_user and mode == "ask":
            _PENDING[callback.from_user.id] = {"waiting": "topic", "mode": "real"}
            if callback.message:
                await callback.message.answer(
                    "✍️ ဇာတ်လမ်း အကြောင်းအရာ (ဥပမာ — ရှေးခေတ် ရွာတစ်ရွာက လျှို့ဝှက်ချက်) ရိုက်ထည့်ပါ။\n"
                    "ဒါမှမဟုတ် “ကျော်မယ်” ကို နှိပ်ပါ။",
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                        types.InlineKeyboardButton(text="⏭ ကျော်မယ်", callback_data="produce:real"),
                    ]]),
                )
            return

        if not callback.message:
            return
        await run_full_pipeline(callback.message, dry_run=(mode == "dry"))

    @dp.message(F.text & ~F.text.startswith("/"))
    async def on_text(message: types.Message) -> None:
        pending = _PENDING.pop(message.from_user.id, None) if message.from_user else None
        if pending and pending.get("waiting") == "topic":
            await run_full_pipeline(
                message, topic=message.text.strip(), dry_run=pending.get("mode") == "dry"
            )
            return
        await message.answer(
            "ဇာတ်လမ်း စတင်ရန် /start ကို နှိပ်ပါ။\n"
            "ဗီဒီယိုဖိုင် ပြီးသားရှိရင် ဖိုင်ကို ပို့ပြီး “YouTube တင်မယ်” ကို နှိပ်ပါ။"
        )

    @dp.message(F.video | F.document)
    async def on_video(message: types.Message) -> None:
        if message.from_user:
            _PENDING.pop(message.from_user.id, None)
        document = message.video or message.document
        if document is None:
            return
        job_dir = _new_job_dir("upload")
        job_dir.mkdir(parents=True, exist_ok=True)
        status = await message.answer("⬇️ ဗီဒီယို လက်ခံနေတယ်…")
        try:
            file = await bot.get_file(document.file_id)
            target = job_dir / "final.mp4"
            await bot.download_file(file.file_path, destination=target)
        except Exception as exc:  # noqa: BLE001
            await _safe_edit(status, f"❌ ဖိုင် ယူမရပါ: {exc}")
            return

        size_mb = target.stat().st_size / 1024 / 1024
        await _safe_edit(
            status,
            f"✅ ဗီဒီယို ရပါပြီ ({size_mb:.0f}MB)\n\nYouTube တင်မလား?",
            markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🎬 YouTube တင်မယ်", callback_data=f"upload:real:{job_dir.name}")],
                [types.InlineKeyboardButton(text="🧪 စမ်းသပ် (dry-run)", callback_data=f"upload:dry:{job_dir.name}")],
            ]),
        )

    @dp.callback_query(F.data.startswith("upload:"))
    async def on_upload(callback: types.CallbackQuery) -> None:
        _, mode, job_name = callback.data.split(":")
        await callback.answer("စတင်နေပါပြီ…")
        if callback.message:
            await _publish_existing(callback.message, TEMP_DIR / job_name, mode == "dry")

    @dp.message(Command("cleanup"))
    async def on_cleanup(message: types.Message) -> None:
        removed = 0
        for path in TEMP_DIR.glob("job_*"):
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
        await message.answer(f"🧹 job folder {removed} ခု ဖျက်ပြီး")

    logger.info("Bot စတင်နေပါပြီ…")
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot ရပ်လိုက်ပါပြီ")
