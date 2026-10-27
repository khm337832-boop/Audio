"""Render / VPS အတွက် — Telegram bot (polling) + HTTP health server ကို တွဲ run ပေးတယ်။

Render က **web service** ဆိုရင် port တစ်ခုကို bind လုပ်မှ deploy အောင်တယ်။
ဒါကြောင့် `python main.py serve` က —

  • `0.0.0.0:$PORT` မှာ HTTP server (`/`, `/healthz`) ဖွင့်
  • တစ်ချိန်တည်းမှာ bot polling ကို run
  • SIGTERM (Render restart) ရရင် နှစ်ခုလုံး သန့်ရှင်းစွာ ရပ်

Worker (port မလိုတဲ့) ဆိုရင် `python main.py bot` ကို သုံးနိုင်တယ်။
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import time
from typing import Any

import config

logger = logging.getLogger(__name__)

_STARTED = time.time()
_STATE: dict[str, Any] = {
    "bot": "starting",
    "username": None,
    "error": None,
    "restarts": 0,
}


def _status_payload() -> dict[str, Any]:
    token_set = bool(config.BOT_TOKEN)
    return {
        "ok": True,
        "service": "audio-bot",
        "uptime_seconds": int(time.time() - _STARTED),
        "bot": _STATE["bot"],
        "username": _STATE["username"],
        "token": "set" if token_set else "missing",
        "gemini": "set" if config.GEMINI_API_KEY else "missing",
        "model": config.GEMINI_MODEL,
        "error": _STATE["error"],
        "restarts": _STATE["restarts"],
        "privacy": config.YOUTUBE_PRIVACY_STATUS,
    }


def build_web_app():
    """aiohttp app — Render health check အတွက်။"""
    from aiohttp import web

    async def healthz(request):  # noqa: ANN001, ARG001
        return web.Response(text="ok")

    async def index(request):  # noqa: ANN001, ARG001
        return web.json_response(_status_payload())

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/status", index)
    return app


async def _bot_forever(stop: asyncio.Event) -> None:
    """Bot ကို အဆက်မပြတ် run — ကွန်ရက်/conflict error ရင် ပြန်စ။"""
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.exceptions import (
        TelegramConflictError,
        TelegramNetworkError,
        TelegramRetryAfter,
        TelegramUnauthorizedError,
    )

    import bot as bot_module

    attempt = 0
    while not stop.is_set():
        attempt += 1
        if attempt > 1:
            _STATE["restarts"] = attempt - 1
        try:
            async with Bot(
                token=config.BOT_TOKEN,
                default=DefaultBotProperties(parse_mode="HTML"),
            ) as tg_bot:
                try:
                    me = await tg_bot.get_me()
                except TelegramUnauthorizedError:
                    _STATE.update(bot="token_invalid", error="Token မှားနေတယ်")
                    logger.error("Token မှားနေတယ် — BotFather က token ပြန်ယူပါ")
                    return
                _STATE.update(bot="running", username=me.username, error=None)
                logger.info("Bot @%s စတင်ပြီး (polling)", me.username)
                info = await tg_bot.get_webhook_info()
                if info.url:
                    logger.info("webhook (%s) ဖျက်ပြီး polling သုံးမယ်", info.url)
                    await tg_bot.delete_webhook(drop_pending_updates=False)
                dp = bot_module.build_dispatcher(tg_bot)
                await dp.start_polling(tg_bot, handle_signals=False)
                logger.info("polling ရပ်သွားတယ်")
                return
        except TelegramUnauthorizedError:
            _STATE.update(bot="token_invalid", error="Token မှားနေတယ်")
            logger.error("Token မှားနေတယ်")
            return
        except TelegramConflictError:
            _STATE.update(bot="conflict", error="အခြား instance တစ်ခု run နေတယ်")
            logger.error("Conflict — အခြား bot instance တစ်ခု run နေတယ် (၃၀ စက္ကန့်နောက် ပြန်စ)")
            await _sleep_or_stop(stop, 30)
        except TelegramRetryAfter as exc:
            wait = int(getattr(exc, "retry_after", 20)) + 1
            _STATE.update(bot="rate_limited")
            logger.warning("Telegram က %s စက္ကန့် စောင့်ခိုင်းတယ်", wait)
            await _sleep_or_stop(stop, wait)
        except (TelegramNetworkError, OSError) as exc:
            wait = min(60, 5 * attempt)
            _STATE.update(bot="network_error", error=str(exc)[:200])
            logger.warning("ကွန်ရက် error (%s) — %s စက္ကန့်နောက် ပြန်စ", exc, wait)
            await _sleep_or_stop(stop, wait)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            wait = min(60, 5 * attempt)
            _STATE.update(bot="error", error=f"{type(exc).__name__}: {exc}"[:200])
            logger.exception("Bot error — %s စက္ကန့်နောက် ပြန်စ", wait)
            await _sleep_or_stop(stop, wait)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def _main(port: int) -> int:
    from aiohttp import web

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            with contextlib.suppress(NotImplementedError, ValueError):
                loop.add_signal_handler(sig, stop.set)

    from bot import token_problem

    app = build_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("🌐 HTTP ဖွင့်ပြီး: 0.0.0.0:%s (health: /healthz)", port)
    print(f"🌐 HTTP: http://0.0.0.0:{port}/healthz")

    problem = token_problem(config.BOT_TOKEN)
    tasks: list[asyncio.Task] = []
    if problem:
        _STATE.update(bot="token_missing", error=problem)
        logger.error("Bot မ​စတင်နိုင်ပါ — %s", problem)
        print(f"⚠️ Bot မ​စတင်နိုင်ပါ — {problem} (.env စစ်ပါ၊ server က run နေတယ်)")
    else:
        tasks.append(asyncio.create_task(_bot_forever(stop), name="bot"))

    try:
        await stop.wait()
    except asyncio.CancelledError:
        raise
    finally:
        logger.info("ရပ်နေတယ်… (SIGTERM/Ctrl+C)")
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await runner.cleanup()
    return 0


def run(port: int | None = None) -> int:
    """`python main.py serve` — PORT env (မဟုတ်) ပေးထားတဲ့ port မှာ run။"""
    port = int(port or os.getenv("PORT") or config.PORT)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    try:
        return asyncio.run(_main(port))
    except KeyboardInterrupt:
        return 0
