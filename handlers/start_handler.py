"""/start, /help — ဇာတ်လမ်းဖန်တီးခြင်း နဲ့ YouTube တင်ခြင်း ခလုတ်များ။"""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart

import config

router = Router()


def _limits() -> str:
    return f"{config.STORY_MIN_CHARS:,}–{config.STORY_MAX_CHARS:,}"


WELCOME = (
    "🎬 <b>မြန်မာ အသံဇာတ်လမ်း → YouTube</b>\n\n"
    "ခလုတ်တစ်ခု နှိပ်လိုက်ရင် အလိုအလျောက် လုပ်ပေးပါမယ် —\n"
    f"① ဇာတ်လမ်းရေး ({_limits()} စာလုံး)\n"
    "② voice over (မြန်မာ TTS / ElevenLabs Charon)\n"
    "③ ဇာတ်ကွက်အလိုက် ပုံဖန်တီး\n"
    "④ motion video ဖန်တီး\n"
    "⑤ အသံနဲ့ ပေါင်းစပ်\n"
    "⑥ သင်္ကေတပုံ + SEO ခေါင်းစဉ်/ဖော်ပြချက်\n"
    "⑦ YouTube channel မှာ တင်\n\n"
    "⏱ မိနစ် အတော်ကြာနိုင်တယ် (ဇာတ်လမ်းအရှည်ပေါ်မူတည်ပြီး)။"
)

HELP = (
    "<b>အသုံးပြုပုံ</b>\n\n"
    "🚀 <b>ဇာတ်လမ်းဖန်တီးပြီး တင်မယ်</b> — အဆင့် ၁-၇ အားလုံး run ပြီး YouTube တင်တယ်\n"
    "🧪 <b>စမ်းသပ် (dry-run)</b> — YouTube API မခေါ်ဘဲ ဗီဒီယို/thumbnail/SEO payload ထုတ်တယ်\n"
    "📤 <b>ဗီဒီယိုဖိုင် ပို့ပြီး တင်မယ်</b> — ပြီးသား mp4 ကို ဒီ chat ထဲ ပို့လိုက်ရင် "
    "ခေါင်းစဉ်/ဖော်ပြချက်/thumbnail ကို ဖန်တီးပြီး တင်ပေးတယ်\n"
    "/cleanup — temp/job folder များ ဖျက်ခြင်း\n\n"
    "<b>လိုအပ်ချက်</b>\n"
    "• <code>GEMINI_API_KEY</code> — ဇာတ်လမ်း/SEO/ပုံ prompt\n"
    "• <code>TTS_COMMAND</code> သို့ <code>ELEVENLABS_API_KEY</code> — voice over\n"
    "• <code>ffmpeg</code> — motion video\n"
    "• <code>client_secret.json</code> — YouTube တကယ်တင်ရန်"
)


def main_keyboard() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🚀 ဇာတ်လမ်းဖန်တီးပြီး YouTube တင်မယ်",
                                        callback_data="produce:ask")],
            [types.InlineKeyboardButton(text="⚡ အကြောင်းအရာ မပေးဘဲ စမယ်",
                                        callback_data="produce:real")],
            [types.InlineKeyboardButton(text="🧪 စမ်းသပ် (dry-run)", callback_data="produce:dry")],
            [types.InlineKeyboardButton(text="❓ အသုံးပြုပုံ", callback_data="help")],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    await message.answer(WELCOME, reply_markup=main_keyboard())


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(HELP)


@router.callback_query(F.data == "help")
async def cb_help(callback: types.CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(HELP)


@router.message(F.text == "🎬 ဇာတ်လမ်း ဖန်တီး")
async def text_generate(message: types.Message) -> None:
    await message.answer("ဘယ်လို စမလဲ?", reply_markup=main_keyboard())
