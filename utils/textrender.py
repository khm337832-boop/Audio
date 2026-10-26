"""စာသား ရေးဆွဲခြင်း — မြန်မာ/အာရဗီ စတဲ့ complex script များအတွက် text shaping ပါဝင်တဲ့ painter များ။

Backend သုံးမျိုး (အကောင်းဆုံးကို အလိုအလျောက် ရွေးတယ်):
  1. ``RaqmPainter``   — Pillow + libraqm (HarfBuzz shaping)  ← အကောင်းဆုံး
  2. ``ShapedPainter`` — uharfbuzz + freetype-py (wheel နှစ်ခုသာ လိုတယ်)
  3. ``BasicPainter``  — Pillow basic layout (မြန်မာစာလုံး လေပ်နိုင်တယ်; သတိပေးချက် ထုတ်တယ်)

မြန်မာစာသားကို basic layout နဲ့ ရေးရင် ဗျည်းနဲ့ သရ/ဗျည်းတွဲတွေ ကွဲထွက်ပြီး
“မြစ်” ကို “မြ စ ်” လို မြင်ရနိုင်တယ်။ ဒါကြောင့် shaping ရှိတဲ့ backend ကို ဦးစားပေးတယ်။
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

MYANMAR_RE = re.compile(r"[\u1000-\u109F\uAA60-\uAA7F]")
COMPLEX_RE = re.compile(r"[\u1000-\u109F\uAA60-\uAA7F\u0600-\u06FF\u0E00-\u0E7F\u0900-\u097F]")

_FT_CACHE: dict[tuple[str, int], tuple] = {}


# --------------------------------------------------------------------- probes
def raqm_available() -> bool:
    try:
        from PIL import features

        return bool(features.check("raqm"))
    except Exception:  # pragma: no cover
        return False


def shaping_available() -> bool:
    try:
        import freetype
        import uharfbuzz

        return bool(freetype and uharfbuzz)
    except Exception:
        return False


def needs_shaping(text: str) -> bool:
    return bool(COMPLEX_RE.search(text or ""))


# --------------------------------------------------------------------- painters
class BasePainter:
    """Painter အားလုံးရဲ့ interface။"""

    name = "base"

    def __init__(self, size: int, fill="#FFFFFF", stroke_width: int = 0, stroke_fill="#000000"):
        self.size = int(size)
        self.fill = fill
        self.stroke_width = int(stroke_width)
        self.stroke_fill = stroke_fill

    @property
    def ascent(self) -> float:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def descent(self) -> float:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def line_height(self) -> float:
        return (self.ascent + self.descent) * 1.16

    def measure(self, text: str) -> float:  # pragma: no cover - interface
        raise NotImplementedError

    def draw(self, image, x: float, y: float, text: str) -> None:  # pragma: no cover
        raise NotImplementedError


class RaqmPainter(BasePainter):
    """Pillow ကို raqm layout နဲ့ သုံး (မြန်မာ အပါအဝင် shaping မှန်ကန်)။"""

    name = "raqm"

    def __init__(self, font_path: str | Path | None, size: int, fill="#FFFFFF",
                 stroke_width: int = 0, stroke_fill="#000000"):
        super().__init__(size, fill, stroke_width, stroke_fill)
        from PIL import ImageFont

        self._font_fallback = ImageFont.load_default(size=self.size)
        self.font = self._font_fallback
        if font_path:
            try:
                self.font = ImageFont.truetype(
                    str(font_path), self.size, layout_engine=ImageFont.Layout.RAQM
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("raqm font ဖွင့်မရပါ (%s): %s", font_path, exc)
        self._ascent, self._descent = self.font.getmetrics()

    @property
    def ascent(self) -> float:
        return float(self._ascent)

    @property
    def descent(self) -> float:
        return float(self._descent)

    def measure(self, text: str) -> float:
        return float(self.font.getlength(text))

    def draw(self, image, x: float, y: float, text: str) -> None:
        from PIL import ImageDraw

        draw = ImageDraw.Draw(image)
        draw.text(
            (x, y), text, font=self.font, fill=self.fill,
            stroke_width=self.stroke_width, stroke_fill=self.stroke_fill,
        )


class ShapedPainter(BasePainter):
    """uharfbuzz (shaping) + freetype-py (raster) နဲ့ စာသားရေးတယ်။"""

    name = "shaped"

    def __init__(self, font_path: str | Path, size: int, fill="#FFFFFF",
                 stroke_width: int = 0, stroke_fill="#000000"):
        super().__init__(size, fill, stroke_width, stroke_fill)
        if not font_path:
            raise RuntimeError("ShapedPainter အတွက် font ဖိုင် လိုအပ်")
        self.font_path = str(font_path)
        self._hb_font, self._ft_face, self._upem = self._load(self.font_path, self.size)

    # ---- font cache
    @staticmethod
    def _load(font_path: str, size: int):
        key = (font_path, size)
        if key in _FT_CACHE:
            return _FT_CACHE[key]

        import freetype
        import uharfbuzz as hb

        with open(font_path, "rb") as handle:
            blob = hb.Blob(handle.read())
        hb_face = hb.Face(blob)
        hb_font = hb.Font(hb_face)
        upem = hb_face.upem or 1000
        hb_font.scale = (upem, upem)

        ft_face = freetype.Face(font_path)
        ft_face.set_pixel_sizes(0, size)
        _FT_CACHE[key] = (hb_font, ft_face, upem)
        return _FT_CACHE[key]

    @property
    def ascent(self) -> float:
        return float(self._ft_face.size.ascender >> 6)

    @property
    def descent(self) -> float:
        return float(-(self._ft_face.size.descender >> 6))

    @property
    def _scale(self) -> float:
        return self.size / self._upem

    def _shape(self, text: str):
        import uharfbuzz as hb

        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self._hb_font, buf, {"kerning": True, "liga": True})
        return list(zip(buf.glyph_infos, buf.glyph_positions))

    def measure(self, text: str) -> float:
        if not text:
            return 0.0
        total = sum(pos.x_advance for _, pos in self._shape(text))
        return total * self._scale

    def _line_mask(self, text: str):
        """တစ်ကြောင်းစာ alpha mask နဲ့ (dx, dy) offset ကို ပြန်ပေးတယ်။"""
        from PIL import Image

        import freetype

        scale = self._scale
        pen_x = 0.0
        glyphs: list[tuple[int, float, float]] = []
        for info, pos in self._shape(text):
            gid = info.codepoint
            gx = pen_x + pos.x_offset * scale
            gy = -pos.y_offset * scale
            glyphs.append((gid, gx, gy))
            pen_x += pos.x_advance * scale

        placed = []
        min_x = min_y = None
        max_x = max_y = None
        for gid, gx, gy in glyphs:
            try:
                self._ft_face.load_glyph(gid, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
            except Exception:
                continue
            slot = self._ft_face.glyph
            bitmap = slot.bitmap
            left = slot.bitmap_left + gx
            top = slot.bitmap_top + gy          # baseline မှ အပေါ်သို့ အကွာအဝေး
            width, rows = bitmap.width, bitmap.rows
            if width == 0 or rows == 0:
                continue
            stride = abs(int(bitmap.pitch)) or width
            raw = bytes(bitmap.buffer)
            if len(raw) < stride * rows:        # buffer မပြည့်ရင် ဖြည့်
                raw = raw.ljust(stride * rows, b"\x00")
            glyph_bytes = b"".join(raw[r * stride: r * stride + width] for r in range(rows))
            placed.append((glyph_bytes, left, top, width, rows))
            min_x = left if min_x is None else min(min_x, left)
            max_x = left + width if max_x is None else max(max_x, left + width)
            min_y = -top if min_y is None else min(min_y, -top)
            max_y = -top + rows if max_y is None else max(max_y, -top + rows)

        if not placed:
            return Image.new("L", (max(1, int(pen_x)), max(1, self.size)), 0), 0, 0

        width = max(1, int(round(max_x - min_x)))
        height = max(1, int(round(max_y - min_y)))
        mask = Image.new("L", (width, height), 0)
        for glyph_bytes, left, top, w, h in placed:
            glyph_img = Image.frombytes("L", (w, h), glyph_bytes)
            mask.paste(
                glyph_img,
                (int(round(left - min_x)), int(round(-top - min_y))),
                glyph_img,
            )
        return mask, float(min_x), float(min_y)

    def draw(self, image, x: float, y: float, text: str) -> None:
        from PIL import Image, ImageColor

        if not text:
            return
        mask, dx, dy = self._line_mask(text)
        baseline = y + self.ascent
        target_x = int(round(x + dx))
        target_y = int(round(baseline + dy))

        if self.stroke_width > 0:
            from PIL import ImageFilter

            stroke_mask = mask.filter(ImageFilter.MaxFilter(self.stroke_width * 2 + 1))
            stroke_layer = Image.new("RGBA", stroke_mask.size, ImageColor.getrgb(self.stroke_fill) + (255,))
            image.paste(stroke_layer, (target_x, target_y), stroke_mask)

        fill_layer = Image.new("RGBA", mask.size, ImageColor.getrgb(self.fill) + (255,))
        image.paste(fill_layer, (target_x, target_y), mask)


class BasicPainter(BasePainter):
    """Pillow basic layout — shaping မပါ။ နောက်ဆုံး fallback။"""

    name = "basic"

    def __init__(self, font_path: str | Path | None, size: int, fill="#FFFFFF",
                 stroke_width: int = 0, stroke_fill="#000000"):
        super().__init__(size, fill, stroke_width, stroke_fill)
        from PIL import ImageFont

        self.font = None
        if font_path:
            try:
                self.font = ImageFont.truetype(str(font_path), self.size)
            except Exception:
                self.font = None
        if self.font is None:
            try:
                self.font = ImageFont.load_default(size=self.size)
            except Exception:  # pragma: no cover
                self.font = ImageFont.load_default()
        self._ascent, self._descent = self.font.getmetrics()

    @property
    def ascent(self) -> float:
        return float(self._ascent)

    @property
    def descent(self) -> float:
        return float(self._descent)

    def measure(self, text: str) -> float:
        try:
            return float(self.font.getlength(text))
        except Exception:  # pragma: no cover
            return float(len(text) * self.size * 0.6)

    def draw(self, image, x: float, y: float, text: str) -> None:
        from PIL import ImageDraw

        draw = ImageDraw.Draw(image)
        draw.text(
            (x, y), text, font=self.font, fill=self.fill,
            stroke_width=self.stroke_width, stroke_fill=self.stroke_fill,
        )


# --------------------------------------------------------------------- factory
def make_painter(
    font_path: str | Path | None,
    size: int,
    text: str = "",
    *,
    fill="#FFFFFF",
    stroke_width: int = 0,
    stroke_fill="#000000",
    force_backend: str | None = None,
) -> BasePainter:
    """စာသားနဲ့ ပတ်ဝန်းကျင်အရ သင့်တော်တဲ့ painter ကို ရွေးပေးတယ်။"""
    size = max(8, int(size))
    kwargs = dict(fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)

    if force_backend == "shaped":
        return ShapedPainter(font_path, size, **kwargs)
    if force_backend == "basic":
        return BasicPainter(font_path, size, **kwargs)
    if force_backend == "raqm":
        return RaqmPainter(font_path, size, **kwargs)

    if raqm_available():
        return RaqmPainter(font_path, size, **kwargs)

    if font_path and shaping_available():
        try:
            return ShapedPainter(font_path, size, **kwargs)
        except Exception as exc:  # pragma: no cover
            logger.warning("shaped painter မရပါ: %s", exc)

    if needs_shaping(text):
        logger.warning(
            "libraqm / uharfbuzz မရှိပါ — မြန်မာစာသားကို basic layout နဲ့ ရေးနေတယ်၊ "
            "စာလုံးတွေ လေပ်နိုင်တယ်။ ဖြေရှင်းချက်: `pip install uharfbuzz freetype-py` "
            "(သို့) Pillow ကို libraqm နဲ့ တည်ဆောက်ပါ။"
        )
    return BasicPainter(font_path, size, **kwargs)


def wrap_text(text: str, measure, max_width: float) -> list[str]:
    """Space မပါတဲ့ ဘာသာစကား (မြန်မာ/ဂျပန်) ကိုပါ ဖြတ်နိုင်တဲ့ word wrap။"""
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}".strip()
            if measure(candidate) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            if measure(word) > max_width:
                broken = _break_long_word(word, measure, max_width)
                lines.extend(broken[:-1])
                current = broken[-1] if broken else ""
            else:
                current = word
        if current:
            lines.append(current)
    return lines


def _break_long_word(word: str, measure, max_width: float) -> list[str]:
    chunks: list[str] = []
    current = ""
    for char in word:
        candidate = current + char
        if measure(candidate) <= max_width or not current:
            current = candidate
        else:
            chunks.append(current)
            current = char
    if current:
        chunks.append(current)
    return chunks or [word]
