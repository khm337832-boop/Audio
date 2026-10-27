"""`.env` ဖန်တီး/စစ်ဆေးတဲ့ wizard — terminal မှာ `python main.py setup` လို့ ရိုက်ပါ။

လုပ်ပေးတာ:
  ① BOT_TOKEN ကို Telegram API နဲ့ တကယ် စစ် (getMe) → bot @username ပြ
  ② GEMINI_API_KEY ကို Google API နဲ့ တကယ် စစ် → model list ပြ
  ③ အသံ (voice over) အတွက် ရွေးချယ်စရာ — edge-tts (key မလို) / f5-myanmar-tts / ElevenLabs
  ④ `.env` ထဲ သိမ်း (ရှိပြီးသား တန်ဖိုးများ မပျက်စေရ)
"""

from __future__ import annotations

import importlib
import re
import shutil
from pathlib import Path

ENV_PATH = Path(".env")
ENV_EXAMPLE = Path(".env.example")

OK, WARN, FAIL = "✅", "⚠️", "❌"


# --------------------------------------------------------------------- env file
def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env(updates: dict[str, str], path: Path = ENV_PATH) -> Path:
    """ရှိပြီးသား `.env` ရဲ့ comment/အခြား key များကို မဖျက်ဘဲ update လုပ်တယ်။"""
    if not path.exists() and ENV_EXAMPLE.exists():
        shutil.copyfile(ENV_EXAMPLE, path)
    lines = path.read_text("utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        match = re.match(r"^\s*([A-Z0-9_]+)\s*=", line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n", "utf-8")
    return path


# --------------------------------------------------------------------- validators
def validate_bot_token(token: str, timeout: int = 20) -> tuple[bool, str]:
    if not token or ":" not in token:
        return False, "token ပုံစံ မမှန်ပါ (123456:ABC-DEF… ပုံစံ ဖြစ်ရမယ်)"
    try:
        import requests

        response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe", timeout=timeout
        )
        data = response.json()
        if data.get("ok"):
            bot = data["result"]
            return True, f"@{bot.get('username')} ({bot.get('first_name', '')})"
        return False, str(data.get("description", "Telegram က ငြင်းပယ်တယ်"))
    except Exception as exc:  # noqa: BLE001
        return False, f"အင်တာနက်/Telegram ချိတ်ဆက်မှု မရပါ: {exc}"


def validate_gemini_key(api_key: str, timeout: int = 30) -> tuple[bool, str]:
    if not api_key or len(api_key) < 20:
        return False, "key ပုံစံ မမှန်ပါ"
    try:
        import requests

        response = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": api_key},
            timeout=timeout,
        )
        if response.status_code != 200:
            return False, f"Google က ငြင်းပယ်တယ် ({response.status_code}): {response.text[:120]}"
        models = [
            m.get("name", "").replace("models/", "")
            for m in response.json().get("models", [])
        ]
        flash = [m for m in models if "flash" in m][:2]
        return True, f"model {len(models)} ခု ရတယ် ({', '.join(flash) or models[:2]})"
    except Exception as exc:  # noqa: BLE001
        return False, f"အင်တာနက်ချိတ်ဆက်မှု မရပါ: {exc}"


def mask(value: str, keep: int = 6) -> str:
    if not value:
        return "(ဗလာ)"
    return value[:keep] + "…" + value[-4:] if len(value) > keep + 4 else value[:keep] + "…"


# --------------------------------------------------------------------- wizard
def run_wizard(input_fn=input, print_fn=print) -> int:
    print_fn("\n🧙 Audio bot — ပြင်ဆင်မှု wizard")
    print_fn("=" * 62)

    current = read_env()
    updates: dict[str, str] = {}

    # ---- ① BOT_TOKEN
    print_fn("\n① Telegram BOT_TOKEN")
    print_fn("   @BotFather → /newbot → token ကို copy လုပ်ပါ")
    existing = current.get("BOT_TOKEN", "")
    if existing:
        ok, detail = validate_bot_token(existing)
        print_fn(f"   လက်ရှိ token: {mask(existing)} → {OK if ok else FAIL} {detail}")
    token = input_fn("   BOT_TOKEN (Enter = လက်ရှိအတိုင်း / ကျော်ရန် -): ").strip()
    if token and token != "-":
        ok, detail = validate_bot_token(token)
        print_fn(f"   {OK if ok else FAIL} {detail}")
        if ok:
            updates["BOT_TOKEN"] = token
        else:
            print_fn("   ⚠️ မှားနေတဲ့ token ကို မသိမ်းလိုက်ပါ")

    # ---- ② GEMINI_API_KEY
    print_fn("\n② GEMINI_API_KEY (ဇာတ်လမ်း ၂၀,၀၀၀+ စာလုံး / SEO / ပုံ prompt)")
    print_fn("   https://aistudio.google.com/apikey → Create API key")
    existing = current.get("GEMINI_API_KEY", "")
    if existing:
        ok, detail = validate_gemini_key(existing)
        print_fn(f"   လက်ရှိ key: {mask(existing)} → {OK if ok else FAIL} {detail}")
    key = input_fn("   GEMINI_API_KEY (Enter = လက်ရှိအတိုင်း / ကျော်ရန် -): ").strip()
    if key and key != "-":
        ok, detail = validate_gemini_key(key)
        print_fn(f"   {OK if ok else FAIL} {detail}")
        if ok:
            updates["GEMINI_API_KEY"] = key
        else:
            print_fn("   ⚠️ မှားနေတဲ့ key ကို မသိမ်းလိုက်ပါ")

    # ---- ③ voice over
    print_fn("\n③ အသံ (voice over) — ဘယ်နည်းနဲ့ ထွက်မလဲ?")
    print_fn("   1) edge-tts  — အခမဲ့၊ key မလို၊ မြန်မာ neural voice (အကြံပြု)")
    print_fn("   2) f5-myanmar-tts — ကိုယ်ပိုင်/offline မြန်မာ TTS (TTS_COMMAND လို)")
    print_fn("   3) ElevenLabs — Charon deep voice (API key လို)")
    choice = input_fn("   ရွေးချယ် [1/2/3] (Enter = 1): ").strip() or "1"

    if choice == "2":
        command = input_fn(
            '   TTS_COMMAND (Enter = လက်ရှိ / ဥပမာ f5-tts_infer --gen_text_file {text_file} --output {output}): '
        ).strip()
        if command:
            updates["TTS_COMMAND"] = command
        updates["TTS_PROVIDER"] = "local"
    elif choice == "3":
        eleven_key = input_fn("   ELEVENLABS_API_KEY: ").strip()
        if eleven_key:
            updates["ELEVENLABS_API_KEY"] = eleven_key
        voice = input_fn("   voice နာမည် (Enter = Charon): ").strip()
        updates["ELEVENLABS_VOICE_NAME"] = voice or "Charon"
        updates["TTS_PROVIDER"] = "elevenlabs"
    else:
        updates["TTS_PROVIDER"] = "auto"
        try:
            importlib.import_module("edge_tts")
            print_fn(f"   {OK} edge-tts ထည့်ပြီးသား — မြန်မာ voice အဆင်သင့်")
        except Exception:
            print_fn(f"   {WARN} edge-tts မရှိသေးပါ — ဒီ command ကို run ပါ: pip install edge-tts")

    # ---- ④ save
    if updates:
        path = write_env(updates)
        print_fn(f"\n{OK} .env သိမ်းပြီး: {path.resolve()}")
        for key in updates:
            print_fn(f"   • {key} = {mask(updates[key]) if 'KEY' in key or 'TOKEN' in key else updates[key]}")
    else:
        print_fn("\n(ပြောင်းလဲမှု မရှိ — .env ကို မထိပါ)")

    # ---- ⑤ next steps
    values = read_env()
    print_fn("\n" + "=" * 62)
    print_fn("နောက်တစ်ဆင့်")
    if not values.get("BOT_TOKEN"):
        print_fn(f"{FAIL} BOT_TOKEN မရှိသေးပါ → python main.py setup ကို ပြန် run")
    if not Path("client_secret.json").exists():
        print_fn(f"{WARN} client_secret.json မရှိ → YouTube တကယ်တင်လိုမှ လို")
        print_fn("   လမ်းညွှန်: docs/YOUTUBE_AUTH_MM.md")
    else:
        print_fn(f"{OK} client_secret.json ရှိ → python main.py auth (တစ်ခါ)")

    print_fn("\nစမ်းသပ်ရန် (YouTube မတင်ဘဲ):")
    print_fn("   python main.py produce --dry-run --chars 3000 --scenes 1")
    print_fn("တကယ် run ရန်:")
    print_fn("   python bot.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_wizard())
