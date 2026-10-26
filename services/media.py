"""ffmpeg ကို သုံးပြီး clip ပေါင်းခြင်း / အသံနဲ့ ပေါင်းခြင်း (workflow ရဲ့ အဆင့် ၀)။"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class MediaError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _require_ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise MediaError("ffmpeg မတွေ့ပါ — `apt install ffmpeg` (သို့) PATH ထဲမှာ ထည့်ပါ")
    return binary


def _run(args: list[str], *, timeout: int = 3600) -> None:
    logger.debug("ffmpeg: %s", " ".join(args))
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(f"ffmpeg မအောင်မြင်ပါ:\n{proc.stderr[-1200:]}")


def image_to_motion_video(
    image_path: str | Path,
    output_path: str | Path,
    duration: float,
    *,
    size: tuple[int, int] = (1280, 720),
    fps: int = 30,
    audio_path: str | Path | None = None,
) -> Path:
    """ပုံတစ်ပုံကို အချိန်သတ်မှတ်ချက်အတိုင်း (နူးညံ့တဲ့ zoom နဲ့) ဗီဒီယို clip ဖန်တီးတယ်။"""
    ffmpeg = _require_ffmpeg()
    duration = max(0.5, float(duration))
    width, height = size
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,fps={fps},format=yuv420p"
    ).format(fps=fps)

    args = [ffmpeg, "-y", "-loop", "1", "-i", str(image_path)]
    if audio_path:
        args += ["-i", str(audio_path)]
    args += [
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-movflags", "+faststart",
    ]
    if audio_path:
        args += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
    args += [str(output_path)]
    _run(args)
    return output_path


def concat_videos(clips: list[str | Path], output_path: str | Path) -> Path:
    """Clip များကို အစဉ်လိုက် ပေါင်းတယ် (encode parameter တူရမယ်)။"""
    if not clips:
        raise MediaError("ပေါင်းစည်းရန် clip မရှိပါ")
    ffmpeg = _require_ffmpeg()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    list_file = output_path.with_suffix(".concat.txt")
    list_file.write_text(
        "".join(f"file '{Path(c).resolve().as_posix()}'\n" for c in clips), "utf-8"
    )
    try:
        _run([
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", "-movflags", "+faststart", str(output_path),
        ])
    except MediaError:
        logger.warning("concat demuxer မရပါ — filter နဲ့ ပြန်ကြိုးစားမယ်")
        inputs: list[str] = []
        for clip in clips:
            inputs += ["-i", str(clip)]
        filter_complex = "".join(f"[{i}:v]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[v]"
        _run([
            ffmpeg, "-y", *inputs, "-filter_complex", filter_complex,
            "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path),
        ])
    finally:
        list_file.unlink(missing_ok=True)
    return output_path


def combine_video_audio(
    video_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
    *,
    shortest: bool = True,
) -> Path:
    """ဗီဒီယိုနဲ့ အသံကို ပေါင်းတယ် (ဗီဒီယိုကို ပြန်မချုံ့ဘူး)။"""
    ffmpeg = _require_ffmpeg()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        ffmpeg, "-y", "-i", str(video_path), "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
    ]
    if shortest:
        args += ["-shortest"]
    args += ["-movflags", "+faststart", str(output_path)]
    _run(args)
    return output_path


def build_final_video(
    clips: list[str | Path],
    audio_path: str | Path,
    output_path: str | Path,
    *,
    work_dir: str | Path | None = None,
) -> Path:
    """clips → concat → mux audio → final video (workflow က ဒီဖိုင်ကို လက်ခံတယ်)။"""
    work_dir = Path(work_dir) if work_dir else Path(output_path).parent
    concat_path = work_dir / "video_noaudio.mp4"
    concat_videos(clips, concat_path)
    return combine_video_audio(concat_path, audio_path, output_path)


def probe_duration(path: str | Path) -> float:
    """ffprobe နဲ့ ကြာချိန် (စက္ကန့်) ယူတယ် — ffprobe မရှိရင် 0.0။"""
    binary = shutil.which("ffprobe")
    if not binary:
        return 0.0
    proc = subprocess.run(
        [binary, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0
