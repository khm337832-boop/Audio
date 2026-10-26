"""ပရောဂျက်အတွက် ဗဟိုချက် configuration ဖိုင်။

တန်ဖိုးအားလုံးကို `.env` (သို့) ပတ်ဝန်းကျင် variable မှ ယူပါတယ်။
API key မရှိရင် pipeline က offline (dry-run) mode နဲ့ အလုပ်လုပ်ပါတယ်။
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv မရှိရင်လည်း ဆက်အလုပ်လုပ်နိုင်ရမယ်
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - optional dependency
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------- paths
TEMP_DIR = Path(os.getenv("TEMP_DIR", str(BASE_DIR / "temp")))
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = Path(os.getenv("FONTS_DIR", str(ASSETS_DIR / "fonts")))

# ---------------------------------------------------------------- telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ---------------------------------------------------------------- LLM (Gemini)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "imagen-3.0-generate-002")

# ---------------------------------------------------------------- YouTube
YOUTUBE_CLIENT_SECRETS = Path(
    os.getenv("YOUTUBE_CLIENT_SECRETS", str(BASE_DIR / "client_secret.json"))
)
YOUTUBE_TOKEN_FILE = Path(
    os.getenv("YOUTUBE_TOKEN_FILE", str(BASE_DIR / "youtube-oauth2.json"))
)
YOUTUBE_CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID", "24")  # 24 = Entertainment
YOUTUBE_PRIVACY_STATUS = os.getenv("YOUTUBE_PRIVACY_STATUS", "private")
YOUTUBE_MADE_FOR_KIDS = _env_bool("YOUTUBE_MADE_FOR_KIDS", False)
YOUTUBE_LANGUAGE = os.getenv("YOUTUBE_LANGUAGE", "my")
YOUTUBE_DEFAULT_AUDIO_LANGUAGE = os.getenv("YOUTUBE_DEFAULT_AUDIO_LANGUAGE", "my")

# ---------------------------------------------------------------- 業務ルール / limits
TITLE_MAX_CHARS = 100          # YouTube hard limit
DESCRIPTION_MAX_CHARS = 5000   # YouTube hard limit
DESCRIPTION_SAFE_CHARS = 4800  # ကိုယ့်ဘက်က ချန်ထားတဲ့ margin
THUMBNAIL_SIZE = (1280, 720)   # YouTube recommended (16:9)
THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024  # YouTube hard limit 2MB

# ---------------------------------------------------------------- runtime
DRY_RUN = _env_bool("DRY_RUN", False)
FORCE_MOCK = _env_bool("FORCE_MOCK", False)  # API key ရှိလည်း mock ကိုပဲ သုံးမယ်


def llm_available() -> bool:
    """Gemini API key ရှိပြီး mock မဖြစ်မှ True."""
    return bool(GEMINI_API_KEY) and not FORCE_MOCK and not DRY_RUN


def is_offline() -> bool:
    """API မခေါ်ဘဲ template/mock နဲ့ အလုပ်လုပ်မလား။"""
    return FORCE_MOCK or DRY_RUN or not llm_available()


def ensure_dirs() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    FONTS_DIR.mkdir(parents=True, exist_ok=True)


ensure_dirs()
