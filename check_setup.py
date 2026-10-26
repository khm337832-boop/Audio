"""Bot ကို သုံးလို့ရပြီလား ဆိုတာကို တစ်ချက်တည်း စစ်ပေးတဲ့ script။

    python check_setup.py

✅ = အဆင်သင့်   ⚠️ = မရှိလည်း အလုပ်လုပ်တယ် (fallback ရှိ)   ❌ = ဒါမပါရင် အဆင့်တစ်ခု ရပ်မယ်
"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

OK, WARN, FAIL = "✅", "⚠️", "❌"

CHECKS: list[tuple[str, str, str, str]] = []  # (status, name, detail, fix)


def add(status: str, name: str, detail: str = "", fix: str = "") -> None:
    CHECKS.append((status, name, detail, fix))
    print(f"{status} {name:<30} {detail}")


def check_module(module: str, name: str, fix: str, *, required: bool = True) -> bool:
    try:
        mod = importlib.import_module(module)
        version = getattr(mod, "__version__", "")
        add(OK, name, version)
        return True
    except Exception as exc:
        detail = "မထည့်ရသေးပါ" if "No module named" in str(exc) else str(exc)[:60]
        add(FAIL if required else WARN, name, detail, fix)
        return False


def main() -> int:
    try:
        import config
    except Exception as exc:
        print(f"{FAIL} config.py ဖတ်မရပါ: {exc}")
        return 1

    print("\n=== ① Python package များ ===")
    check_module("aiogram", "aiogram (Telegram)", "pip install -r requirements.txt")
    check_module("dotenv", "python-dotenv", "pip install python-dotenv")
    check_module("PIL", "Pillow (ပုံ/thumbnail)", "pip install Pillow")
    check_module("google.generativeai", "google-generativeai (ဇာတ်လမ်း/စာသား)",
                 "pip install google-generativeai", required=False)
    check_module("googleapiclient", "google-api-python-client (YouTube)",
                 "pip install google-api-python-client google-auth-oauthlib", required=False)

    print("\n=== ② မြန်မာစာသား ရေးဆွဲနိုင်မှု ===")
    from utils import textrender

    if textrender.raqm_available():
        add(OK, "Pillow + libraqm (အကောင်းဆုံး)", "HarfBuzz shaping")
    elif textrender.shaping_available():
        add(OK, "uharfbuzz + freetype-py", "မြန်မာစာသား မှန်ကန်စွာ ရေးနိုင်တယ်")
    else:
        add(FAIL, "text shaping backend", "စာလုံးတွေ လေပ်နိုင်တယ်",
            "pip install uharfbuzz freetype-py  (သို့) Pillow ကို libraqm နဲ့ တည်ဆောက်")

    font = Path("assets/fonts/Padauk-Bold.ttf")
    if font.is_file():
        add(OK, "မြန်မာ font", font.name)
    else:
        add(FAIL, "မြန်မာ font", f"{font} မတွေ့",
            "assets/fonts/ ထဲမှာ Padauk/Noto Sans Myanmar ထည့်ပါ (သို့) THUMBNAIL_FONT သတ်မှတ်ပါ")

    print("\n=== ③ ဇာတ်လမ်း အရှည် ===")
    low, high = config.story_target()
    add(OK, "ဇာတ်လမ်း ပစ်မှတ်", f"{low:,}–{high:,} စာလုံး "
        f"(အခန်း ~{config.STORY_CHAPTER_CHARS:,} စာလုံး၊ အများဆုံး {config.STORY_MAX_CHAPTERS})")

    print("\n=== ④ အသံ / ဗီဒီယို ===")
    from services import media

    ffmpeg = media.ffmpeg_binary()
    if ffmpeg:
        add(OK, "ffmpeg", ffmpeg)
    else:
        add(FAIL, "ffmpeg", "မတွေ့ပါ", "sudo apt install ffmpeg (သို့) pip install imageio-ffmpeg")
    if shutil.which("ffprobe"):
        add(OK, "ffprobe", "အသံကြာချိန် တိတိကျကျ တိုင်းနိုင်တယ်")
    elif ffmpeg:
        add(WARN, "ffprobe", "မရှိ — စာလုံးအရေအတွက်နဲ့ ခန့်မှန်းမယ်", "sudo apt install ffmpeg")

    from services import tts_service

    if tts_service.edge_available():
        add(OK, "edge-tts (အခမဲ့ မြန်မာအသံ)", "my-MM-NilarNeural — key မလို")
    else:
        add(WARN, "edge-tts", "မရှိ — အခမဲ့ မြန်မာအသံ မရနိုင်", "pip install edge-tts")

    if tts_service.gtts_available():
        add(OK, "gTTS (အရန်)", "key မလို")
    else:
        add(WARN, "gTTS", "မရှိ (မလိုအပ်ပါ)", "pip install gTTS")

    have_free = tts_service.edge_available() or tts_service.gtts_available()
    if tts_service.local_available():
        add(OK, "ကိုယ်ပိုင် TTS (local)", config.TTS_COMMAND[:50] + "…" if config.TTS_COMMAND
            else "f5-myanmar-tts တွေ့ပြီး (TTS_COMMAND မသတ်မှတ်ရသေး)")
        if not config.TTS_COMMAND:
            add(WARN, "TTS_COMMAND", "မသတ်မှတ်ရသေး",
                '.env: TTS_COMMAND="f5-tts_infer --gen_text_file {text_file} --output {output}"')
    else:
        add(WARN if have_free else FAIL, "ကိုယ်ပိုင် TTS (local)",
            "မရှိ — မလိုအပ်ပါ (edge-tts ကို သုံးမယ်)" if have_free else "မရှိပါ",
            "လိုရင်: pip install f5-myanmar-tts + TTS_COMMAND")

    if config.ELEVENLABS_API_KEY:
        add(OK, "ElevenLabs (deep voice)",
            f"voice={config.ELEVENLABS_VOICE_NAME} model={config.ELEVENLABS_MODEL}")
    else:
        add(WARN, "ElevenLabs", "မရှိ — အင်္ဂလိပ်/English deep voice မရနိုင်",
            "ELEVENLABS_API_KEY ထည့်ပါ (Charon voice)")

    provider = tts_service.resolve_provider("my")
    add(OK, "မြန်မာစာအတွက် provider", provider)
    add(OK, "အသုံးပြုနိုင်တဲ့ provider", ", ".join(tts_service.available_providers()) or "—")

    print("\n=== ⑤ Telegram / API key ===")
    env_file = Path(".env")
    if env_file.is_file():
        add(OK, ".env ဖိုင်", str(env_file.resolve()))
    else:
        add(FAIL, ".env ဖိုင်", "မရှိပါ", "cp .env.example .env ပြီး တန်ဖိုးများ ထည့်ပါ")

    if config.BOT_TOKEN:
        add(OK, "BOT_TOKEN", f"{config.BOT_TOKEN[:6]}…")
    else:
        add(FAIL, "BOT_TOKEN", "မရှိပါ", "@BotFather ကနေ token ယူပြီး .env မှာ ထည့်ပါ")

    if config.GEMINI_API_KEY and not config.FORCE_MOCK:
        add(OK, "GEMINI_API_KEY", "ဇာတ်လမ်း/title/description ကို AI နဲ့ ရေးမယ်")
    else:
        add(WARN, "GEMINI_API_KEY", "မရှိ — template/offline ဇာတ်လမ်းနဲ့ အလုပ်လုပ်မယ်",
            "https://aistudio.google.com/apikey ကနေ key ယူပါ")

    print("\n=== ⑥ YouTube ===")
    if Path(config.YOUTUBE_CLIENT_SECRETS).is_file():
        add(OK, "client_secret.json", str(config.YOUTUBE_CLIENT_SECRETS))
        if Path(config.YOUTUBE_TOKEN_FILE).is_file():
            add(OK, "youtube-oauth2.json", "OAuth token cache ရှိပြီး — bot တိုက်ရိုက် တင်နိုင်တယ်")
        else:
            add(WARN, "youtube-oauth2.json", "token မရှိသေး — bot က dry-run ပဲ လုပ်နိုင်တယ်",
                "python main.py auth  (တစ်ခါသာ) — လမ်းညွှန်: docs/YOUTUBE_AUTH_MM.md")
    else:
        add(WARN, "client_secret.json", "မရှိပါ (dry-run မှာ မလို)",
            "လမ်းညွှန်: docs/YOUTUBE_AUTH_MM.md → ပြီးရင် python main.py auth")

    print("\n=== ⑦ Thumbnail render စမ်းသပ်မှု ===")
    try:
        import tempfile

        from PIL import Image

        from services import image_service, thumbnail_service

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base = image_service.generate_scene_image(
                "test", tmp_path / "base.jpg", width=1280, height=720
            )
            out = thumbnail_service.compose_thumbnail(
                base, "မြစ်ကမ်းက မီးရောင် — စမ်းသပ်", tmp_path / "t.jpg",
                subtitle="ညတိုင်း ပေါ်လာတဲ့ မီးရောင်", badge="ဇာတ်လမ်း",
            )
            with Image.open(out) as img:
                size = img.size
            kb = out.stat().st_size / 1024
        add(OK, "thumbnail 1280×720", f"{size[0]}×{size[1]}, {kb:.0f} KB ≤ 2MB")
    except Exception as exc:
        add(FAIL, "thumbnail render", str(exc)[:80], "pip install Pillow uharfbuzz freetype-py")

    # ---------------- report
    print("\n" + "=" * 62)
    fails = [c for c in CHECKS if c[0] == FAIL]
    warns = [c for c in CHECKS if c[0] == WARN]
    print(f"✅ {sum(1 for c in CHECKS if c[0] == OK)}   ⚠️ {len(warns)}   ❌ {len(fails)}")
    print("=" * 62)

    if fails:
        print("\nဖြေရှင်းရန်:")
        for _, name, _, fix in fails:
            print(f"  • {name}: {fix}")

        if any("TTS" in name for _, name, _, _ in fails):
            print("\n👉 TTS မရှိသေးလို့ အဆင့် ③ (voice over) ကို မလုပ်နိုင်ပါ။")
            print("   အလွယ်ဆုံး: pip install edge-tts   (အခမဲ့၊ key မလို)")
        if any("client_secret" in name for _, name, _, _ in fails):
            print("\n👉 YouTube မတင်နိုင်သေးပါ — dry-run နဲ့ စမ်းနိုင်တယ်:")
            print("    python main.py produce --dry-run")
        return 1

    if warns:
        print("\n👉 စမ်းသပ် mode နဲ့ စတင်နိုင်ပါပြီ:")
        print("    python main.py produce --dry-run      # terminal")
        print("    DRY_RUN=true python bot.py            # Telegram (YouTube မတင်)")
    else:
        print("\n👉 အဆင်သင့်ပါပြီ: python bot.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
