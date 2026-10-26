"""Thumbnail: ① prompt ဖန်တီး → ② base ပုံ → ③ PIL နဲ့ စာသားထပ်ခြင်း။"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import config
from models.story import StoryMetadata
from services import image_service, llm
from utils.textkit import clamp_text, normalize_whitespace

logger = logging.getLogger(__name__)

_MYANMAR = re.compile(r"[\u1000-\u109F\uAA60-\uAA7F]")
_MYANMAR_FONT_HINTS = ("padauk", "myanmar", "pyidaungsu", "mymyanmar", "notosansmyanmar")
_FONT_SUFFIXES = (".ttf", ".otf", ".ttc")

_SYSTEM_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)

_THUMB_STYLE_HINTS = (
    "cinematic 16:9 YouTube thumbnail background, dramatic lighting, high contrast, "
    "rich colors, shallow depth of field, centered subject, clean negative space on the "
    "lower third for text, no text, no letters, no watermark, ultra detailed, 4k"
)


@dataclass
class ThumbnailResult:
    prompt: str
    base_image_path: Path
    thumbnail_path: Path


# ------------------------------------------------------------------ fonts
def _font_dirs() -> list[Path]:
    candidates = [Path(os.getenv("THUMBNAIL_FONT_DIR", "")), config.FONTS_DIR,
                  Path("/usr/share/fonts"), Path.home() / ".fonts"]
    seen: list[Path] = []
    for path in candidates:
        if str(path) and path not in seen:
            seen.append(path)
    return seen


def resolve_font_path(preferred: str | Path | None = None, text: str = "") -> Path | None:
    """မြန်မာစာသားအတွက် မြန်မာ glyph ပါတဲ့ font ကို ဦးစားပေး ရှာတယ်။"""
    explicit = [preferred, os.getenv("THUMBNAIL_FONT")]
    for item in explicit:
        if item:
            path = Path(item).expanduser()
            if path.is_file():
                return path

    found: list[Path] = []
    for directory in _font_dirs():
        if not directory.is_dir():
            continue
        for suffix in _FONT_SUFFIXES:
            found.extend(directory.rglob(f"*{suffix}"))
        if found:
            break

    wants_myanmar = bool(_MYANMAR.search(text or ""))
    if wants_myanmar:
        myanmar_fonts = [
            path for path in found
            if any(hint in path.name.lower().replace(" ", "").replace("-", "") for hint in _MYANMAR_FONT_HINTS)
        ]
        if myanmar_fonts:
            # bold ကို ဦးစားပေး (thumbnail စာသား ထင်ရှားရန်)
            myanmar_fonts.sort(key=lambda p: ("bold" not in p.name.lower(), p.name))
            return myanmar_fonts[0]
        if found:
            logger.warning(
                "မြန်မာ glyph ပါတဲ့ font မတွေ့ပါ — assets/fonts/ ထဲမှာ Padauk/Noto Sans Myanmar "
                "ထည့်ပါ (မဟုတ်ရင် စာလုံးတွေ လေပ်နေနိုင်တယ်)။ လက်ရှိ font: %s",
                found[0].name,
            )

    for candidate in _SYSTEM_FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path
    return found[0] if found else None


# ------------------------------------------------------------------ ① prompt
def generate_thumbnail_prompt(metadata: StoryMetadata, *, style_hint: str | None = None) -> str:
    style_hint = style_hint or _THUMB_STYLE_HINTS
    if llm.available():
        prompt = f"""YouTube thumbnail အတွက် အင်္ဂလိပ်လို ပုံဖန်တီးရေး prompt တစ်ကြောင်း ရေးပါ။
ဇာတ်လမ်း: {metadata.title}
အမျိုးအစား: {metadata.genre}
အနှစ်ချုပ်: {clamp_text(metadata.summary, 400)}
ဇာတ်ကောင်များ: {", ".join(metadata.characters[:5])}

လိုအပ်ချက်: 16:9၊ ဆွဲဆောင်မှုရှိ၊ လှုပ်ရှားမှုရှိ၊ စာသားမပါ၊ watermark မပါ၊ အောက်ခြေ 1/3 မှာ စာထည့်ဖို့ နေရာချန်ထား။
Prompt စာသားတစ်ကြောင်းတည်းသာ ပြန်ပါ။"""
        try:
            text = llm.generate_text(prompt, temperature=0.9, max_output_tokens=300)
            text = normalize_whitespace(text).strip('" ')
            if text:
                return f"{text}, {style_hint}"
        except llm.LLMUnavailable as exc:
            logger.info("thumbnail prompt LLM မရပါ: %s", exc)

    subject = metadata.logline or metadata.summary or metadata.title
    genre = metadata.genre or "story"
    return (
        f"{genre} story key visual, {clamp_text(subject, 160)}, "
        f"main character silhouette in a dramatic scene, {style_hint}"
    )


# ------------------------------------------------------------------ ③ PIL text overlay
def _scrim(size: tuple[int, int], start_ratio: float = 0.40):
    """အောက်ခြေမှာ မှောင်တဲ့ gradient — စာသား ဖတ်ရလွယ်စေရန်။"""
    from PIL import Image

    width, height = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    start = int(height * start_ratio)
    for y in range(start, height):
        t = (y - start) / max(1, height - start)
        alpha = int(215 * (t ** 1.35))
        line = Image.new("RGBA", (width, 1), (6, 8, 14, alpha))
        overlay.paste(line, (0, y))
    return overlay


def compose_thumbnail(
    base_image_path: str | Path,
    title: str,
    output_path: str | Path,
    *,
    subtitle: str | None = None,
    badge: str | None = None,
    font_path: str | Path | None = None,
    size: tuple[int, int] | None = None,
    accent: str = "#FFD400",
    max_lines: int = 3,
) -> Path:
    """Base ပုံပေါ်မှာ ခေါင်းစဉ်စာသား (နဲ့ subtitle/badge) ကို ထပ်ရေးတယ်။

    မြန်မာစာသားအတွက် text shaping (raqm/uharfbuzz) ကို အလိုအလျောက် သုံးတယ်။
    """
    from PIL import Image, ImageOps

    from utils.textrender import make_painter, wrap_text

    size = size or config.THUMBNAIL_SIZE
    width, height = size
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base = Image.open(base_image_path).convert("RGB")
    base = ImageOps.fit(base, size, method=Image.LANCZOS, centering=(0.5, 0.45))

    # အနည်းငယ် မှောင်ချ + အောက်ခြေ gradient
    dark = Image.new("RGB", size, (0, 0, 0))
    base = Image.blend(base, dark, 0.10).convert("RGBA")
    base = Image.alpha_composite(base, _scrim(size)).convert("RGB")

    margin = int(width * 0.05)
    max_text_width = width - 2 * margin

    title_text = normalize_whitespace(title)
    subtitle_text = normalize_whitespace(subtitle or "")
    resolved_font = resolve_font_path(font_path, text=f"{title_text}{subtitle_text}{badge or ''}")

    # ---- ခေါင်းစဉ် အရွယ်အစားကို max_lines အတွင်း ဝင်အောင် လျှော့
    title_px = int(height * 0.112)
    title_painter = None
    lines: list[str] = []
    while title_px > 28:
        stroke = max(2, title_px // 18)
        title_painter = make_painter(
            resolved_font, title_px, title_text,
            stroke_width=stroke, stroke_fill="#0B0D12",
        )
        # stroke နဲ့ glyph side-bearing အတွက် နေရာချန်တယ်
        wrap_width = max_text_width - 2 * stroke - int(title_px * 0.12)
        lines = wrap_text(title_text, title_painter.measure, wrap_width)
        if len(lines) <= max_lines:
            break
        title_px -= 4

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        if not last.endswith("…"):
            lines[-1] = last[:-1] + "…" if len(last) > 1 else last + "…"

    line_height = title_painter.line_height
    title_block = line_height * len(lines)

    # ---- subtitle
    sub_painter = None
    sub_lines: list[str] = []
    if subtitle_text:
        sub_px = max(22, int(title_px * 0.42))
        sub_painter = make_painter(
            resolved_font, sub_px, subtitle_text,
            fill="#EAEAF0", stroke_width=max(1, sub_px // 20), stroke_fill="#0B0D12",
        )
        sub_lines = wrap_text(subtitle_text, sub_painter.measure, max_text_width)[:2]
    sub_block = (sub_painter.line_height * 1.15 * len(sub_lines)) if sub_painter else 0

    # ---- အောက်ခြေကနေ အပေါ်သို့ တွက်ပြီး နေရာချ
    total_height = title_block + sub_block
    start_y = height - margin - total_height
    start_y = max(start_y, int(height * 0.28)) if total_height < height * 0.6 else int(height * 0.28)

    # accent bar
    from PIL import ImageDraw

    draw = ImageDraw.Draw(base)
    bar_height = max(6, int(height * 0.012))
    gap = int(bar_height * 2.2)
    draw.rounded_rectangle(
        [margin, start_y - gap - bar_height, margin + int(width * 0.09), start_y - gap],
        radius=bar_height // 2, fill=accent,
    )

    y = float(start_y)
    for line in lines:
        title_painter.draw(base, margin, y, line)
        y += line_height

    if sub_painter and sub_lines:
        y += int(line_height * 0.12)
        for line in sub_lines:
            sub_painter.draw(base, margin, y, line)
            y += sub_painter.line_height * 1.15

    # ---- badge (genre / language) — ဘယ်ဘက်အပေါ်
    if badge:
        badge_text = clamp_text(badge, 28)
        badge_px = max(20, int(height * 0.045))
        badge_painter = make_painter(resolved_font, badge_px, badge_text, fill="#111111")
        text_w = badge_painter.measure(badge_text)
        pad_x, pad_y = int(height * 0.028), int(height * 0.016)
        box_top = int(height * 0.055)
        box = [margin, box_top,
               margin + int(text_w) + pad_x * 2,
               box_top + int(badge_painter.line_height) + pad_y * 2]
        draw.rounded_rectangle(box, radius=int(height * 0.018), fill=accent)
        badge_painter.draw(base, box[0] + pad_x, box_top + pad_y, badge_text)

    _save_within_limit(base, output_path)
    return output_path


def _save_within_limit(image, output_path: Path) -> Path:
    """JPEG အနေနဲ့ သိမ်း၊ 2MB ကျော်ရင် quality ပြန်ချ။"""
    if output_path.suffix.lower() == ".png":
        image.save(output_path, format="PNG", optimize=True)
    else:
        for quality in (92, 88, 82, 75, 68):
            image.save(output_path, format="JPEG", quality=quality, optimize=True, progressive=True)
            if output_path.stat().st_size <= config.THUMBNAIL_MAX_BYTES:
                break
    size = output_path.stat().st_size
    if size > config.THUMBNAIL_MAX_BYTES:
        raise ValueError(f"thumbnail ဖိုင် ကြီးလွန်းနေတယ် ({size} bytes) — YouTube က 2MB ပဲ လက်ခံတယ်")
    logger.info("thumbnail သိမ်းပြီး: %s (%.1f KB)", output_path, size / 1024)
    return output_path


# ------------------------------------------------------------------ all-in-one
def create_thumbnail(
    metadata: StoryMetadata,
    work_dir: str | Path,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    badge: str | None = None,
    prompt: str | None = None,
    base_image_path: str | Path | None = None,
    image_generator=image_service.generate_scene_image,
) -> ThumbnailResult:
    """prompt → base ပုံ → စာသားထပ် → ThumbnailResult။"""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    prompt = prompt or generate_thumbnail_prompt(metadata)
    base_path = Path(base_image_path) if base_image_path else work_dir / "thumbnail_base.jpg"
    if not base_path.exists() or base_path.stat().st_size == 0:
        image_generator(
            prompt,
            base_path,
            width=config.THUMBNAIL_SIZE[0],
            height=config.THUMBNAIL_SIZE[1],
        )

    title = title or metadata.title
    subtitle = subtitle if subtitle is not None else clamp_text(
        metadata.logline or metadata.summary, 70
    )
    badge = badge if badge is not None else (metadata.genre or "ဇာတ်လမ်း")
    thumb_path = compose_thumbnail(
        base_path,
        title,
        work_dir / "thumbnail.jpg",
        subtitle=subtitle,
        badge=badge,
    )
    return ThumbnailResult(prompt=prompt, base_image_path=base_path, thumbnail_path=thumb_path)
