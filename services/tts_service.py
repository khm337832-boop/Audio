"""မြန်မာ TTS — အခန်းတစ်ခန်းစီ အသံထွက်ပြီး တစ်ဖိုင်တည်း ပေါင်းပေးတယ်။

TTS engine ကို ပြင်ပမှာ ချိတ်ထားတယ် (default: `f5-myanmar-tts`)။
`TTS_COMMAND` env မှာ shell template ပေးရင် အဲဒါကို သုံးမယ် —
ဥပမာ: `TTS_COMMAND="f5-tts_infer --ref_audio ref.wav --gen_text_file {text_file} --output {output}"`
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path

from models.story import Story
from services.media import probe_duration

logger = logging.getLogger(__name__)


class TTSError(RuntimeError):
    pass


def _run_tts_command(text: str, output_path: Path, work_dir: Path) -> Path:
    template = os.getenv("TTS_COMMAND", "").strip()
    if not template:
        raise TTSError(
            "TTS engine မသတ်မှတ်ထားပါ — `pip install f5-myanmar-tts` လုပ်ပြီး "
            "TTS_COMMAND (သို့) TTS_ENGINE ကို .env မှာ သတ်မှတ်ပါ"
        )

    text_file = work_dir / (output_path.stem + ".txt")
    text_file.parent.mkdir(parents=True, exist_ok=True)
    text_file.write_text(text, encoding="utf-8")

    command = template.format(
        text_file=str(text_file),
        output=str(output_path),
        text=shlex.quote(text),
    )
    logger.info("TTS: %s", command[:160])
    proc = subprocess.run(shlex.split(command), capture_output=True, text=True)
    if proc.returncode != 0:
        raise TTSError(f"TTS မအောင်မြင်ပါ:\n{proc.stderr[-800:]}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise TTSError(f"TTS က ဖိုင် မထုတ်ပေးပါ: {output_path}")
    return output_path


def synthesize(text: str, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return _run_tts_command(text, output_path, output_path.parent)


def _concat_audio_files(paths: list[Path], output_path: Path) -> Path:
    """ffmpeg ရှိရင် တစ်ဖိုင်တည်း ပေါင်းမယ်၊ မရှိရင် ပထမဖိုင်ကို ပြန်ပေးမယ်။"""
    import shutil

    if not shutil.which("ffmpeg") or len(paths) < 2:
        return paths[0]
    list_file = output_path.with_suffix(".audio.txt")
    list_file.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in paths), "utf-8"
    )
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
             "-c:a", "copy", str(output_path)],
            check=True, capture_output=True,
        )
        return output_path
    except subprocess.CalledProcessError as exc:
        raise TTSError(f"အသံဖိုင်များ ပေါင်းမရပါ: {exc}") from exc
    finally:
        list_file.unlink(missing_ok=True)


def generate_voice(story: Story) -> tuple[Path, list[dict]]:
    """အခန်းများကို အသံထွက်ပြီး (full_audio, chapter_info) ပြန်ပေးတယ်။

    `chapter_info` = [{"path": Path, "duration": float, "title": str}, ...]
    chapter.duration ကို ဖြည့်ပေးတယ် (နောက်ပိုင်း timestamp အတွက်)။
    """
    if not story.chapters:
        raise TTSError("ဇာတ်လမ်းမှာ အခန်း မရှိပါ")

    work_dir = Path(os.getenv("TEMP_DIR", "temp")) / story.story_id / "audio"
    work_dir.mkdir(parents=True, exist_ok=True)

    chapter_info: list[dict] = []
    paths: list[Path] = []
    for chapter in story.chapters:
        out = work_dir / f"chapter_{chapter.index:02d}.wav"
        if not out.exists():
            synthesize(chapter.text, out)
        duration = probe_duration(out)
        chapter.duration = duration
        chapter.audio_path = str(out)
        paths.append(out)
        chapter_info.append({"path": out, "duration": duration, "title": chapter.title})
        logger.info("အသံ ထွက်ပြီး: %s (%.1fs)", out.name, duration)

    full_audio = _concat_audio_files(paths, work_dir / "full.wav")
    return full_audio, chapter_info
