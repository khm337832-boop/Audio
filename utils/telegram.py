"""Telegram token ကို စစ်ဆေးခြင်း/ဖုံးကွယ်ခြင်း (aiogram မလိုဘဲ သုံးနိုင်တယ်)။"""

from __future__ import annotations

import re

# BotFather token ပုံစံ — <bot id>:<35 လုံးလောက် base64url>
TOKEN_RE = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{30,}$")


def token_problem(token: str) -> str | None:
    """Token ပုံစံ မှန်/မမှန် စစ်တယ်။ မှန်ရင် None၊ မမှန်ရင် မြန်မာလို အကြောင်းရင်း။"""
    token = (token or "").strip()
    if not token:
        return "BOT_TOKEN မရှိပါ"
    if " " in token or "\t" in token:
        return "BOT_TOKEN မှာ ကွက်လပ်/အပိုစာလုံး ပါနေတယ် — BotFather က token ကို အတိအကျ copy ပါ"
    if not TOKEN_RE.match(token):
        return ("BOT_TOKEN ပုံစံ မမှန်ပါ (123456789:AAF... ပုံစံ ဖြစ်ရမယ်) — "
                "BotFather → /mybots → API Token ကို ပြန်ယူပါ")
    return None


def mask_token(token: str) -> str:
    """Log/print အတွက် token ကို ဖုံးကွယ်တယ် (ဥပမာ `123456789:••••`)。"""
    token = (token or "").strip()
    if not token:
        return "(မရှိ)"
    head = token.split(":", 1)[0]
    return f"{head}:••••••••"
