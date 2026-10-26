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
# bot ထဲမှာ browser ဖွင့်လို့မရတာမို့ default false — `python main.py auth` ကို အရင် run ပါ
YOUTUBE_INTERACTIVE = _env_bool("YOUTUBE_INTERACTIVE", False)
YOUTUBE_LANGUAGE = os.getenv("YOUTUBE_LANGUAGE", "my")
YOUTUBE_DEFAULT_AUDIO_LANGUAGE = os.getenv("YOUTUBE_DEFAULT_AUDIO_LANGUAGE", "my")

# ---------------------------------------------------------------- ဇာတ်လမ်း အရှည်
STORY_MIN_CHARS = int(os.getenv("STORY_MIN_CHARS", "20000"))
STORY_MAX_CHARS = int(os.getenv("STORY_MAX_CHARS", "25000"))
STORY_CHAPTER_CHARS = int(os.getenv("STORY_CHAPTER_CHARS", "1200"))  # အခန်းတစ်ခန်း ပျမ်းမျှ
STORY_MAX_CHAPTERS = int(os.getenv("STORY_MAX_CHAPTERS", "30"))
STORY_LANGUAGE = os.getenv("STORY_LANGUAGE", "my")

# ---------------------------------------------------------------- အသံ (voice over)
# auto | local | elevenlabs   (local = မြန်မာ TTS, elevenlabs = Charon စတဲ့ deep voice)
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "auto").strip().lower()
TTS_COMMAND = os.getenv("TTS_COMMAND", "").strip()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_NAME = os.getenv("ELEVENLABS_VOICE_NAME", "Charon")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
TTS_CHUNK_CHARS = int(os.getenv("TTS_CHUNK_CHARS", "2500"))   # တစ်ခါခေါ်မှာ စာလုံးအများဆုံး
TTS_CONCURRENCY = int(os.getenv("TTS_CONCURRENCY", "2"))

# ---------------------------------------------------------------- ပုံ / ဗီဒီယို
SCENES_PER_CHAPTER = int(os.getenv("SCENES_PER_CHAPTER", "2"))
IMAGE_CONCURRENCY = int(os.getenv("IMAGE_CONCURRENCY", "3"))
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1280"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "720"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "30"))

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


def elevenlabs_available() -> bool:
    return bool(ELEVENLABS_API_KEY)


def story_target() -> tuple[int, int]:
    """(min_chars, max_chars) — ဇာတ်လမ်း အရှည် ပစ်မှတ်။"""
    low, high = STORY_MIN_CHARS, STORY_MAX_CHARS
    if low > high:
        low, high = high, low
    return low, high


def is_offline() -> bool:
    """API မခေါ်ဘဲ template/mock နဲ့ အလုပ်လုပ်မလား။"""
    return FORCE_MOCK or DRY_RUN or not llm_available()


def ensure_dirs() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    FONTS_DIR.mkdir(parents=True, exist_ok=True)


ensure_dirs()
