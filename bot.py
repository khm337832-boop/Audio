"""Telegram bot —

“🚀 ဇာတ်လမ်းဖန်တီးပြီး YouTube တင်မယ်” ကို နှိပ်လိုက်တာနဲ့
ဇာတ်လမ်းရေး (၂၀,၀၀၀–၂၅,၀၀၀ စာလုံး) → voice over → ဇာတ်ကွက်ပုံ → motion video →
အသံပေါင်း → thumbnail + SEO → YouTube တင်ခြင်း အထိ အလိုအလျောက် လုပ်ပေးတယ်။

ဗီဒီယိုဖိုင် ပြီးသားရှိရင် ဖိုင်ကို ပို့ပြီး “YouTube တင်မယ်” ကို နှိပ်လိုက်ရုံပါ။
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.exceptions import (
    TelegramConflictError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)
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
        if "TTS" in text or "voice" in text.lower():
            hint = (
                "\n\n💡 အသံထွက် မရပါ — အလွယ်ဆုံး: <code>pip install edge-tts</code> "
                "(အခမဲ့၊ key မလို၊ မြန်မာ neural voice)"
                "\nသို့ <code>TTS_PROVIDER=elevenlabs</code> + "
                "<code>ELEVENLABS_API_KEY</code>"
            )
        elif "accessNotConfigured" in text or "has not been used in project" in text:
            hint = (
                "\n\n💡 YouTube Data API v3 ကို Google Cloud project မှာ ဖွင့်ရမယ်"
                "\n→ console.cloud.google.com/apis/library/youtube.googleapis.com → Enable"
            )
        elif "YouTube" in text or "OAuth" in text or "token" in text:
            hint = (
                "\n\n💡 YouTube တင်ရန် <code>client_secret.json</code> + "
                "<code>python main.py auth</code> လိုပါ"
                "\nလမ်းညွှန်: <code>docs/YOUTUBE_AUTH_MM.md</code> (သို့) dry-run သုံးပါ"
            )
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


# ===================================================================== dispatcher
def build_dispatcher(bot: Bot) -> Dispatcher:
    """Handler အားလုံးကို မှတ်ပုံတင်ပြီး Dispatcher ပြန်ပေးတယ်။"""
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

    # handler ထဲက မမျှော်လင့်တဲ့ error ကို log ချပြီး bot ကို ဆက်အလုပ်လုပ်စေမယ်
    @dp.errors()
    async def on_error(event) -> bool:  # noqa: ANN001
        logger.exception("handler မှာ error ဖြစ်တယ်: %s", event.exception)
        return True

    return dp


# ===================================================================== preflight
from utils.telegram import mask_token, token_problem  # noqa: E402

_mask = mask_token


async def preflight(bot: Bot) -> bool:
    """Bot token + webhook အခြေအနေ စစ်တယ်။ ဆက်လုပ်နိုင်ရင် True။"""
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError:
        print("❌ Token မှားနေတယ် (Telegram က လက်မခံပါ)")
        print("   → BotFather (@BotFather) → /mybots → သင့် bot → API Token → ပြန်ယူပြီး")
        print("     .env ထဲ BOT_TOKEN=… ကို အစားထိုးပါ (bot ကို revoke လုပ်ထားရင် token အသစ် လိုတယ်)")
        return False
    except TelegramNetworkError as exc:
        print(f"❌ Telegram API ကို မချိတ်နိုင်ပါ: {exc}")
        print("   → အင်တာနက်/VPN စစ်ပါ။ VPN သုံးရင် တစ်ခါ ပိတ်ကြည့်ပါ")
        print("   → api.telegram.org ကို ပိတ်ထားတဲ့ network (ကုမ္ပဏီ/ကျောင်း) ဖြစ်နိုင်")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Bot စစ်ဆေးမှု မအောင်မြင်ပါ: {exc}")
        return False

    print(f"✅ Token မှန်တယ် — @{me.username} (id {me.id})")
    webhook = await bot.get_webhook_info()
    if webhook.url:
        print(f"ℹ️ Webhook ချိတ်ထားတယ် ({webhook.url}) — polling အတွက် ဖျက်မယ်")
        await bot.delete_webhook(drop_pending_updates=False)
        print("✅ Webhook ဖျက်ပြီး")
    else:
        print("✅ Webhook မရှိပါ (polling အတွက် ကောင်းတယ်)")
    print("ℹ️ ဖုန်းမှာ bot ကို /start နှိပ်ထားဖို့ လိုတယ်")
    return True


def _setup_logging(log_file: Path | None) -> Path | None:
    if log_file is None:
        return None
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=3,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    return log_file


# ===================================================================== runner
def run_bot(*, restart: bool = True, check_only: bool = False,
            log_file: Path | None = None, max_retries: int = 5) -> int:
    """Bot ကို run လုပ်တယ်။ `check_only` ဆိုရင် စစ်ဆေးပြီး ပြန်ထွက်တယ်။"""
    problem = token_problem(config.BOT_TOKEN)
    if problem:
        print(f"❌ {problem}")
        print("\n   .env ဖိုင် (bot.py ရှိတဲ့ folder) ထဲမှာ ဒီလို ထည့်ပါ:")
        print("   BOT_TOKEN=123456789:AAF...")
        print("   ပြီးရင်: python main.py bot")
        print("   လမ်းညွှန်: docs/BOT_TROUBLESHOOT_MM.md")
        return 2
    if os.getenv("BOT_TOKEN", "").strip() != config.BOT_TOKEN.strip():
        print("ℹ️ BOT_TOKEN ကို environment မှ မဟုတ်ဘဲ .env မှ ဖတ်ထားတယ်")

    log_path = _setup_logging(log_file if log_file is not None else TEMP_DIR / "bot.log")

    if check_only:
        try:
            ok = asyncio.run(_serve(check_only=True))
        except KeyboardInterrupt:
            return 0
        if log_path:
            print(f"📝 log: {log_path}")
        return 0 if ok else 1

    attempt = 0
    while True:
        attempt += 1
        print(f"\n🤖 Bot စတင်နေတယ် (token {_mask(config.BOT_TOKEN)}, ကြိုးစားမှု {attempt})")
        if log_path:
            print(f"📝 log: {log_path}")
        print("   ရပ်ချင်ရင် Ctrl+C နှိပ်ပါ\n")
        try:
            logger.info("Bot စတင်နေပါပြီ…")
            ok = asyncio.run(_serve(check_only=False))
            if not ok:
                return 1
            print("ℹ️ Bot ရပ်သွားတယ် (polling ပြီးဆုံး)")
            return 0
        except KeyboardInterrupt:
            print("\n⏹ Ctrl+C — Bot ရပ်လိုက်တယ်")
            return 0
        except TelegramUnauthorizedError:
            print("❌ Token မှားနေတယ် — BotFather က token ပြန်ယူပါ")
            return 2
        except TelegramConflictError:
            print("❌ အခြား bot instance တစ်ခု run နေတယ် (တူတူ token နဲ့ ၂ ခု မရပါ)")
            print("   → အရင် terminal/ဝင်းဒိုး က bot ကို ပိတ်ပါ (သို့) PC ပြန် restart လုပ်ပါ")
            print("   → ဖုန်း/ဆာဗာ (Render) မှာလည်း run နေတာ မရှိရပါ")
            return 3
        except TelegramRetryAfter as exc:
            wait = exc.retry_after
            print(f"⏳ Telegram က {wait} စက္ကန့် စောင့်ခိုင်းတယ်…")
            time.sleep(wait + 1)
            continue
        except (TelegramNetworkError, OSError) as exc:
            if not restart:
                print(f"❌ ကွန်ရက် error: {exc}")
                return 1
            wait = min(60, 5 * attempt)
            print(f"⚠️ ကွန်ရက် error: {exc}\n   {wait} စက္ကန့်နောက် ပြန်ကြိုးစားမယ်…")
            time.sleep(wait)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.exception("Bot ရပ်သွားတယ်")
            print(f"❌ Bot ရပ်သွားတယ်: {type(exc).__name__}: {exc}")
            if log_path:
                print(f"   အသေးစိတ်: {log_path}")
            if not restart or attempt >= max_retries:
                print("   ဒီ error ကို ပို့ပြီး ကူညီတောင်းပါ — secret မလိုပါ")
                return 1
            wait = min(60, 5 * attempt)
            print(f"   {wait} စက္ကန့်နောက် ပြန်ကြိုးစားမယ်…")
            time.sleep(wait)
            continue


async def _serve(*, check_only: bool) -> bool:
    """တစ်ကြိမ် run — bot + polling ကို loop တစ်ခုတည်းမှာ လုပ်တယ်။ အောင်ရင် True။"""
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        ok = await preflight(bot)
        if not ok:
            return False
        if check_only:
            return True
        dp = build_dispatcher(bot)
        await dp.start_polling(bot, handle_signals=True)
        return True
    finally:
        try:
            await bot.session.close()
        except Exception:  # noqa: BLE001
            pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram bot (YouTube auto pipeline)")
    parser.add_argument("--check", action="store_true", help="Token/webhook ကို စစ်ပြီး ပြန်ထွက်")
    parser.add_argument("--no-restart", action="store_true", help="Error ရင် ပြန် မ​ကြိုးစားဘဲ ထွက်")
    parser.add_argument("--log-file", default=None, help="log ဖိုင် (default: temp/bot.log)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log_file = Path(args.log_file) if args.log_file else None
    return run_bot(restart=not args.no_restart, check_only=args.check, log_file=log_file)


if __name__ == "__main__":
    sys.exit(main())
