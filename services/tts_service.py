"""Voice over — အခန်းတစ်ခန်းစီကို အသံထွက်ပြီး တစ်ဖိုင်တည်း ပေါင်းပေးတယ်။

Provider ၂ မျိုး:
  • **elevenlabs** — Charon စတဲ့ deep voice (အင်္ဂလိပ်/ဘာသာစကားများ)
  • **local**      — မြန်မာ TTS (f5-myanmar-tts စတဲ့ CLI) `TTS_COMMAND` template နဲ့

`.env` ရဲ့ `TTS_PROVIDER` = auto | elevenlabs | local
  auto → မြန်မာစာသားဆိုရင် local ကို ဦးစားပေး၊ အင်္ဂလိပ်ဆိုရင် ElevenLabs
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


def resolve_provider(language: str | None = None) -> str:
    """ဘယ် provider ကို သုံးမလဲ ဆုံးဖြတ်တယ်။"""
    choice = (config.TTS_PROVIDER or "auto").lower()
    if choice in {"elevenlabs", "local"}:
        return choice
    is_myanmar = (language or "my").startswith("my")
    if is_myanmar:
        if local_available():
            return "local"
        if elevenlabs_available():
            logger.warning(
                "မြန်မာ TTS မရှိပါ — ElevenLabs (%s) နဲ့ ထွက်မယ်။ မြန်မာစာအတွက် "
                "eleven_multilingual_v2 ကို သုံးပါ။", config.ELEVENLABS_VOICE_NAME,
            )
            return "elevenlabs"
        return "local"
    if elevenlabs_available():
        return "elevenlabs"
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
            "မြန်မာ TTS engine မသတ်မှတ်ထားပါ — `.env` မှာ TTS_COMMAND သတ်မှတ်ပါ။\n"
            'ဥပမာ: TTS_COMMAND="f5-tts_infer --gen_text_file {text_file} --output {output}"'
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
    provider = provider or resolve_provider(language or detect_language(text))
    if provider == "elevenlabs":
        return _run_elevenlabs(text, output_path)
    return _run_local_tts(text, output_path)


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
    provider = provider or resolve_provider(language)
    suffix = ".mp3" if provider == "elevenlabs" else ".wav"

    base = Path(work_dir) if work_dir else (
        Path(os.getenv("TEMP_DIR", str(config.TEMP_DIR))) / story.story_id
    )
    audio_dir = base / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    chapter_info: list[dict] = []
    paths: list[Path] = []
    total = len(story.chapters)
    for i, chapter in enumerate(story.chapters, start=1):
        out = audio_dir / f"chapter_{chapter.index:02d}{suffix}"
        if not out.exists() or out.stat().st_size == 0:
            if progress:
                progress(f"🎙️ အသံထွက် {i}/{total} ({provider})…")
            synthesize(chapter.text, out, language=language, provider=provider)
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
    "MediaError",
    "TTSError",
    "detect_language",
    "elevenlabs_available",
    "estimate_duration",
    "generate_voice",
    "local_available",
    "resolve_provider",
    "split_text",
    "synthesize",
]
