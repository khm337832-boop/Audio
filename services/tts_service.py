"""Voice over — အခန်းတစ်ခန်းစီကို အသံထွက်ပြီး တစ်ဖိုင်တည်း ပေါင်းပေးတယ်။

Provider ၄ မျိုး:
  • **local**      — မြန်မာ TTS CLI (f5-myanmar-tts စသဖြင့်) `TTS_COMMAND` template နဲ့
  • **edge**       — Microsoft Edge TTS (key မလို၊ အခမဲ့၊ `my-MM-NilarNeural`) ← မြန်မာအတွက် default
  • **gtts**       — Google Translate TTS (key မလို၊ အခမဲ့၊ ရိုးရှင်း)
  • **elevenlabs** — Charon စတဲ့ deep voice (API key လိုတယ်)

`.env` ရဲ့ `TTS_PROVIDER` = auto | edge | gtts | local | elevenlabs
  auto → မြန်မာစာသား: local → edge → gtts → elevenlabs
         အင်္ဂလိပ်စာသား: elevenlabs → edge → gtts → local
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Callable

import config
from models.story import Story
from services.media import MediaError, ffmpeg_binary, probe_duration  # noqa: F401  (re-export)

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]

MYANMAR_RE = re.compile(r"[\u1000-\u109F\uAA60-\uAA7F]")
_SENTENCE_SPLIT = re.compile(r"(?<=[။.!?])\s+")


class TTSError(RuntimeError):
    pass


# ===================================================================== provider
def detect_language(text: str, fallback: str = "my") -> str:
    sample = (text or "")[:4000]
    myanmar = len(MYANMAR_RE.findall(sample))
    latin = len(re.findall(r"[A-Za-z]", sample))
    if myanmar == 0 and latin > 20:
        return "en"
    return fallback if myanmar else ("en" if latin > myanmar else fallback)


def local_available() -> bool:
    if config.TTS_COMMAND:
        return True
    return importlib.util.find_spec("f5_myanmar_tts") is not None


def elevenlabs_available() -> bool:
    return bool(config.ELEVENLABS_API_KEY)


def edge_available() -> bool:
    return importlib.util.find_spec("edge_tts") is not None


def gtts_available() -> bool:
    return importlib.util.find_spec("gtts") is not None


def available_providers() -> list[str]:
    """စက်မှာ တကယ် အလုပ်လုပ်နိုင်တဲ့ provider များ။"""
    found: list[str] = []
    if local_available():
        found.append("local")
    if edge_available():
        found.append("edge")
    if gtts_available():
        found.append("gtts")
    if elevenlabs_available():
        found.append("elevenlabs")
    return found


def resolve_provider(language: str | None = None) -> str:
    """ဘယ် provider ကို သုံးမလဲ ဆုံးဖြတ်တယ်။"""
    choice = (config.TTS_PROVIDER or "auto").lower()
    if choice in {"elevenlabs", "local", "edge", "gtts"}:
        return choice

    is_myanmar = (language or "my").startswith("my")
    if is_myanmar:
        # အရည်အသွေး အစဉ်လိုက်: fine-tuned local → edge (neural) → gtts → elevenlabs
        for candidate, ok in (
            ("local", local_available()),
            ("edge", edge_available()),
            ("gtts", gtts_available()),
            ("elevenlabs", elevenlabs_available()),
        ):
            if ok:
                if candidate == "elevenlabs":
                    logger.warning(
                        "မြန်မာ TTS မရှိပါ — ElevenLabs (%s) နဲ့ ထွက်မယ်။ "
                        "အခမဲ့ မြန်မာအသံအတွက် `pip install edge-tts` လုပ်ပါ။",
                        config.ELEVENLABS_VOICE_NAME,
                    )
                return candidate
        return "local"  # ဘာမှမရှိ — error မက်ဆေ့ချ်နဲ့ လမ်းညွှန်ပြမယ်

    for candidate, ok in (
        ("elevenlabs", elevenlabs_available()),
        ("edge", edge_available()),
        ("gtts", gtts_available()),
        ("local", local_available()),
    ):
        if ok:
            return candidate
    return "local"


# ===================================================================== helpers
def estimate_duration(text: str, chars_per_second: float = 13.0) -> float:
    """ffprobe မရှိရင် ခန့်မှန်းချိန် (မြန်မာ ဖတ်နှုန်း ~၁၃ စာလုံး/စက္ကန့်)။"""
    return max(2.0, len(text or "") / max(1.0, chars_per_second))


def split_text(text: str, limit: int) -> list[str]:
    """စာသားကို `limit` အောက် အပိုင်းများအဖြစ် ဝါကျအလိုက် ဖြတ်တယ်။"""
    text = (text or "").strip()
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > limit:  # ဝါကျတစ်ခုတည်း ရှည်လွန်း
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(sentence), limit):
                chunks.append(sentence[i: i + limit])
            continue
        if len(current) + len(sentence) + 1 <= limit:
            current = f"{current} {sentence}".strip()
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return [c for c in chunks if c]


def _concat_audio(paths: list[Path], output_path: Path) -> Path:
    import shutil

    if len(paths) == 1:
        if paths[0] != output_path:
            shutil.copyfile(paths[0], output_path)
        return output_path
    ffmpeg = ffmpeg_binary()
    if not ffmpeg:
        raise TTSError("အသံပိုင်းများ ပေါင်းရန် ffmpeg လိုတယ် — `apt install ffmpeg` (သို့) `pip install imageio-ffmpeg`")

    list_file = output_path.with_suffix(".audio.txt")
    list_file.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in paths), "utf-8"
    )
    try:
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
             "-c:a", "libmp3lame" if output_path.suffix == ".mp3" else "pcm_s16le",
             str(output_path)],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise TTSError(f"အသံဖိုင်များ ပေါင်းမရပါ: {exc.stderr[-400:] if exc.stderr else exc}") from exc
    finally:
        list_file.unlink(missing_ok=True)
    return output_path


# ===================================================================== local
def _run_local_tts(text: str, output_path: Path) -> Path:
    template = config.TTS_COMMAND
    if not template:
        raise TTSError(
            "TTS engine မသတ်မှတ်ထားပါ။ ရွေးချယ်နည်း ၂ မျိုး —\n"
            "  ① အခမဲ့ (အကြံပြု): pip install edge-tts  → မြန်မာ neural voice (key မလို)\n"
            "  ② ကိုယ်ပိုင် TTS: .env မှာ TTS_COMMAND သတ်မှတ်ပါ\n"
            '     ဥပမာ: TTS_COMMAND="f5-tts_infer --gen_text_file {text_file} --output {output}"'
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text_file = output_path.with_suffix(".txt")
    text_file.write_text(text, encoding="utf-8")

    command = template.format(
        text_file=str(text_file), output=str(output_path), text=shlex.quote(text)
    )
    logger.info("local TTS: %s", command[:160])
    proc = subprocess.run(shlex.split(command), capture_output=True, text=True)
    if proc.returncode != 0:
        raise TTSError(f"TTS မအောင်မြင်ပါ:\n{proc.stderr[-600:]}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise TTSError(f"TTS က ဖိုင် မထုတ်ပေးပါ: {output_path}")
    return output_path


# ===================================================================== elevenlabs
_VOICE_CACHE: dict[str, str] = {}


def _elevenlabs_voice_id() -> str:
    if config.ELEVENLABS_VOICE_ID:
        return config.ELEVENLABS_VOICE_ID
    name = config.ELEVENLABS_VOICE_NAME
    if name in _VOICE_CACHE:
        return _VOICE_CACHE[name]

    import requests

    response = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        timeout=30,
    )
    if response.status_code != 200:
        raise TTSError(f"ElevenLabs voices ယူမရပါ ({response.status_code}): {response.text[:200]}")
    for voice in response.json().get("voices", []):
        if str(voice.get("name", "")).lower() == name.lower():
            _VOICE_CACHE[name] = voice["voice_id"]
            return voice["voice_id"]
    available = ", ".join(v.get("name", "?") for v in response.json().get("voices", [])[:12])
    raise TTSError(
        f"ElevenLabs မှာ '{name}' voice မတွေ့ပါ။ ရှိတဲ့ voice များ: {available} … "
        "(.env မှာ ELEVENLABS_VOICE_ID တိုက်ရိုက် ထည့်လည်း ရတယ်)"
    )


def _elevenlabs_chunk(text: str, output_path: Path, voice_id: str) -> Path:
    import requests

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = {
        "text": text,
        "model_id": config.ELEVENLABS_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0},
    }
    last_error = ""
    for attempt in range(3):
        try:
            response = requests.post(
                url,
                headers={
                    "xi-api-key": config.ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json=payload,
                timeout=180,
            )
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2 + attempt * 3)
            continue
        if response.status_code == 200 and response.content:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)
            return output_path
        if response.status_code in {429, 500, 502, 503, 504}:
            last_error = f"{response.status_code} {response.text[:200]}"
            time.sleep(3 + attempt * 5)
            continue
        raise TTSError(f"ElevenLabs မအောင်မြင်ပါ ({response.status_code}): {response.text[:300]}")
    raise TTSError(f"ElevenLabs မအောင်မြင်ပါ (retry ကုန်သွားတယ်): {last_error}")


def _run_elevenlabs(text: str, output_path: Path) -> Path:
    voice_id = _elevenlabs_voice_id()
    pieces = split_text(text, config.TTS_CHUNK_CHARS)
    if not pieces:
        raise TTSError("အသံထွက်ရန် စာသား မရှိပါ")

    tmp_dir = output_path.parent / f".{output_path.stem}_parts"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    try:
        for i, piece in enumerate(pieces):
            part = tmp_dir / f"part_{i:03d}.mp3"
            if not part.exists():
                _elevenlabs_chunk(piece, part, voice_id)
            parts.append(part)
        return _concat_audio(parts, output_path)
    finally:
        for part in parts:
            part.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


# ===================================================================== edge (key မလို)
EDGE_VOICES = {
    "my": ["my-MM-NilarNeural", "my-MM-ThihaNeural"],
    "en": ["en-US-AndrewNeural", "en-US-AriaNeural"],
}


def _edge_voice(language: str) -> str:
    if config.EDGE_TTS_VOICE:
        return config.EDGE_TTS_VOICE
    voices = EDGE_VOICES.get((language or "my")[:2], EDGE_VOICES["en"])
    return voices[0]


def _edge_chunk(text: str, output_path: Path, voice: str) -> Path:
    import asyncio

    import edge_tts

    async def _save() -> None:
        communicate = edge_tts.Communicate(
            text, voice,
            rate=config.EDGE_TTS_RATE,
            volume=config.EDGE_TTS_VOLUME,
        )
        await communicate.save(str(output_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for attempt in range(3):
        try:
            asyncio.run(_save())
        except Exception as exc:  # network/websocket
            last_error = str(exc)
            time.sleep(2 + attempt * 3)
            continue
        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path
        last_error = "ဖိုင် ဗလာ ထွက်တယ်"
    raise TTSError(
        f"Edge TTS မအောင်မြင်ပါ: {last_error}\n"
        "(အင်တာနက် ချိတ်ဆက်မှု စစ်ပါ — speech.platform.bing.com ကို ရောက်ရမယ်)"
    )


def _run_edge(text: str, output_path: Path, language: str) -> Path:
    voice = _edge_voice(language)
    pieces = split_text(text, 3000)
    if not pieces:
        raise TTSError("အသံထွက်ရန် စာသား မရှိပါ")

    tmp_dir = output_path.parent / f".{output_path.stem}_edge"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    try:
        for i, piece in enumerate(pieces):
            part = tmp_dir / f"part_{i:03d}.mp3"
            if not part.exists() or part.stat().st_size == 0:
                _edge_chunk(piece, part, voice)
            parts.append(part)
        return _concat_audio(parts, output_path)
    finally:
        for part in parts:
            part.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


# ===================================================================== gTTS (key မလို)
_GTTS_LANG = {"my": "my", "en": "en"}


def _run_gtts(text: str, output_path: Path, language: str) -> Path:
    from gtts import gTTS

    lang = _GTTS_LANG.get((language or "my")[:2], "my")
    pieces = split_text(text, 180)  # gTTS က စာလုံးနည်းနည်းမှ ပိုမှန်
    if not pieces:
        raise TTSError("အသံထွက်ရန် စာသား မရှိပါ")

    tmp_dir = output_path.parent / f".{output_path.stem}_gtts"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    try:
        for i, piece in enumerate(pieces):
            part = tmp_dir / f"part_{i:03d}.mp3"
            ok = False
            for attempt in range(3):
                try:
                    gTTS(text=piece, lang=lang, slow=False).save(str(part))
                    ok = part.exists() and part.stat().st_size > 0
                except Exception as exc:
                    logger.warning("gTTS အပိုင်း %s မရပါ (%s)", i, exc)
                    time.sleep(1 + attempt * 2)
                if ok:
                    break
            if not ok:
                raise TTSError("gTTS မအောင်မြင်ပါ — အင်တာနက် ချိတ်ဆက်မှု စစ်ပါ")
            parts.append(part)
        return _concat_audio(parts, output_path)
    finally:
        for part in parts:
            part.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


# ===================================================================== public
def synthesize(
    text: str,
    output_path: str | Path,
    *,
    language: str | None = None,
    provider: str | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    language = language or detect_language(text)
    provider = provider or resolve_provider(language)
    if provider == "elevenlabs":
        return _run_elevenlabs(text, output_path)
    if provider == "edge":
        return _run_edge(text, output_path, language)
    if provider == "gtts":
        return _run_gtts(text, output_path, language)
    return _run_local_tts(text, output_path)


def provider_chain(language: str | None = None) -> list[str]:
    """ပထမ ရွေးထားတဲ့ provider + အရန် provider များ (ရှိတာသာ)။"""
    primary = resolve_provider(language)
    chain = [primary]
    for candidate in available_providers():
        if candidate not in chain:
            chain.append(candidate)
    return chain


def generate_voice(
    story: Story,
    *,
    provider: str | None = None,
    progress: ProgressFn | None = None,
    work_dir: str | Path | None = None,
) -> tuple[Path, list[dict]]:
    """အခန်းအားလုံးကို အသံထွက်ပြီး (full_audio, chapter_info) ပြန်ပေးတယ်။"""
    if not story.chapters:
        raise TTSError("ဇာတ်လမ်းမှာ အခန်း မရှိပါ")

    language = story.language or detect_language(story.full_text)
    chain = [provider] + [p for p in provider_chain(language) if p != provider] if provider \
        else provider_chain(language)
    provider = chain[0]
    suffix = ".wav" if provider == "local" else ".mp3"

    base = Path(work_dir) if work_dir else (
        Path(os.getenv("TEMP_DIR", str(config.TEMP_DIR))) / story.story_id
    )
    audio_dir = base / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    chapter_info: list[dict] = []
    paths: list[Path] = []
    total = len(story.chapters)
    errors: list[str] = []

    for i, chapter in enumerate(story.chapters, start=1):
        suffix = ".wav" if provider == "local" else ".mp3"
        out = audio_dir / f"chapter_{chapter.index:02d}{suffix}"
        if not out.exists() or out.stat().st_size == 0:
            if progress:
                progress(f"🎙️ အသံထွက် {i}/{total} ({provider})…")
            last_error: Exception | None = None
            for candidate in chain:
                suffix = ".wav" if candidate == "local" else ".mp3"
                target = audio_dir / f"chapter_{chapter.index:02d}{suffix}"
                try:
                    synthesize(chapter.text, target, language=language, provider=candidate)
                except TTSError as exc:
                    last_error = exc
                    errors.append(f"{candidate}: {exc}")
                    logger.warning("provider '%s' မရပါ (%s) — နောက်တစ်ခုကို စမ်းမယ်", candidate, exc)
                    continue
                if candidate != provider:
                    logger.info("provider '%s' → '%s' ကို ပြောင်းသုံးမယ်", provider, candidate)
                    provider = candidate  # ကျန်အခန်းများအတွက် မှတ်ထား
                out = target
                last_error = None
                break
            if last_error is not None:
                raise TTSError(
                    "အသံထွက် မအောင်မြင်ပါ — provider အားလုံး မရပါ:\n"
                    + "\n".join(errors[-4:])
                    + "\n\n💡 အလွယ်ဆုံး: pip install edge-tts (အခမဲ့၊ key မလို)"
                )
        duration = probe_duration(out) or estimate_duration(chapter.text)
        chapter.duration = duration
        chapter.audio_path = str(out)
        paths.append(out)
        chapter_info.append(
            {"path": out, "duration": duration, "title": chapter.title, "provider": provider}
        )
        logger.info("အသံ ထွက်ပြီး: %s (%.1fs)", out.name, duration)

    full_audio = _concat_audio(paths, audio_dir / f"full{suffix}")
    return full_audio, chapter_info


__all__ = [
    "EDGE_VOICES",
    "MediaError",
    "TTSError",
    "available_providers",
    "detect_language",
    "edge_available",
    "elevenlabs_available",
    "gtts_available",
    "estimate_duration",
    "generate_voice",
    "local_available",
    "resolve_provider",
    "split_text",
    "synthesize",
]
