"""/start နဲ့ /help — ဇာတ်လမ်းဖန်တီးဖို့ inline keyboard ပေးတယ်။"""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart

router = Router()

WELCOME = (
    "🎬 <b>မြန်မာ အသံဇာတ်လမ်း စက်ရုံ</b>\n\n"
    "ဇာတ်လမ်းရေးခြင်း → အသံထွက်ခြင်း → ပုံဖန်တီးခြင်း → ဗီဒီယိုပေါင်းစည်းခြင်း → "
    "YouTube တင်ခြင်း အထိ အလိုအလျောက် လုပ်ပေးပါတယ်။\n\n"
    "စတင်ဖို့ အောက်က ခလုတ်ကို နှိပ်ပါ။"
)

HELP = (
    "<b>အသုံးပြုပုံ</b>\n"
    "① /start → “ဇာတ်လမ်း ဖန်တီး” ကို နှိပ်ပါ\n"
    "② ဇာတ်လမ်း + အနှစ်ချုပ် + အခန်းအချက်အလက် တစ်ခါတည်း သိမ်းပါတယ် (story.json)\n"
    "③ ခေါင်းစဉ်/ဖော်ပြချက်/thumbnail ကို အလိုအလျောက် ဖန်တီးပါတယ်\n"
    "④ နောက်ဆုံး ဗီဒီယို + YouTube link ကို ပြန်ပို့ပါတယ်\n\n"
    "DRY_RUN=true ဆိုရင် YouTube API မခေါ်ဘဲ စမ်းသပ်နိုင်ပါတယ်။"
)


def main_keyboard() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[[
            types.InlineKeyboardButton(text="🎬 ဇာတ်လမ်း ဖန်တီး", callback_data="generate_story"),
        ]]
    )


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    await message.answer(WELCOME, reply_markup=main_keyboard())


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(HELP)


@router.message(F.text == "🎬 ဇာတ်လမ်း ဖန်တီး")
async def text_generate(message: types.Message) -> None:
    """Keyboard မဟုတ်ဘဲ စာသားနဲ့ ခေါ်ရင်လည်း အလုပ်လုပ်ရမယ်။"""
    await message.answer("ခလုတ်ကို နှိပ်ပါ 👇", reply_markup=main_keyboard())
